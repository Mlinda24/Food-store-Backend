import requests
import uuid
import hmac
import hashlib
import json
import logging
from decimal import Decimal
from django.conf import settings
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.http import HttpResponse
from django.db import transaction as db_transaction
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes as drf_permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from orders.models import Order
from .models import Payment, WebhookLog
from .serializers import (
    PaymentSerializer,
    InitiatePaymentSerializer,
    VerifyPaymentSerializer,
    PaymentStatusSerializer,
)
from restaurants.models import Restaurant, RestaurantWallet, WalletTransaction

logger = logging.getLogger(__name__)

PAYCHANGU_OPERATOR_MAP = {
    'mpamba': 'tnm',
    'airtel_money': 'airtel',
}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_restaurant_for_order(order) -> Restaurant:
    try:
        restaurant = order.restaurant
        if isinstance(restaurant, Restaurant):
            return restaurant
    except AttributeError:
        pass
    return Restaurant.objects.select_related('wallet').get(id=order.restaurant_id)


def _mark_payment_completed(payment, transaction_id=None, raw_data=None) -> bool:
    if payment.status == 'completed':
        logger.info(f'Payment {payment.reference} already completed — skipping')
        return False

    with db_transaction.atomic():
        payment = Payment.objects.select_for_update().get(pk=payment.pk)
        if payment.status == 'completed':
            return False

        total_amount = Decimal(str(payment.amount))
        platform_fee_percent = Decimal('10.00')
        platform_fee = (total_amount * platform_fee_percent) / Decimal('100')
        restaurant_amount = total_amount - platform_fee

        payment.status = 'completed'
        if transaction_id:
            payment.transaction_id = transaction_id
        if raw_data:
            payment.payment_details = raw_data
        payment.paid_at = payment.paid_at or timezone.now()
        payment.platform_fee_percent = platform_fee_percent
        payment.platform_fee = platform_fee
        payment.restaurant_amount = restaurant_amount
        payment.pending_restaurant_amount = restaurant_amount
        payment.distributed_to_wallets = False
        payment.save()

        order = payment.order
        order.payment_status = 'paid'
        order.save()

        logger.info(
            f'Payment completed: order #{order.id}, '
            f'MK{restaurant_amount:,.2f} held pending restaurant confirmation'
        )

    try:
        from notifications.services import NotificationService
        NotificationService.send_notification(
            user=order.customer,
            notification_type='payment',
            title='Payment Successful',
            message=(
                f'Your payment of MK{payment.amount:,.2f} for Order #{order.id} '
                f'was successful. Waiting for restaurant to accept.'
            ),
            data={
                'order_id': str(order.id),
                'transaction_id': str(transaction_id or ''),
                'amount': str(payment.amount),
            },
            send_email=True,
            send_sms=False,
            priority='high',
        )
    except Exception as e:
        logger.error(f'Customer notification failed (non-fatal): {e}')

    return True


def _verify_with_paychangu(paychangu_tx_ref):
    if not paychangu_tx_ref:
        return None, None, None
    headers = {
        'Authorization': f'Bearer {settings.PAYCHANGU_SECRET_KEY}',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }
    try:
        response = requests.get(
            f'{settings.PAYCHANGU_BASE_URL}/payment/verify/{paychangu_tx_ref}',
            headers=headers,
            timeout=15,
        )
        if response.status_code == 200:
            data = response.json()
            inner = data.get('data', data)
            remote_status = inner.get('status', '')
            transaction_id = inner.get('transaction_id') or inner.get('id')
            return remote_status, transaction_id, data
        logger.warning(f'PayChangu verify returned {response.status_code}: {response.text}')
    except requests.RequestException as e:
        logger.error(f'PayChangu verify request failed: {e}')
    return None, None, None


def _credit_wallet_on_order_confirmation(order) -> bool:
    try:
        payment = Payment.objects.get(order=order)

        if payment.status not in ('completed', 'processing', 'pending'):
            logger.warning(
                f'Order #{order.id}: payment status is {payment.status!r} — cannot credit wallet'
            )
            return False

        # If payment not yet completed, try to verify with PayChangu first
        if payment.status in ('processing', 'pending') and payment.transaction_id:
            remote_status, tx_id, raw_data = _verify_with_paychangu(payment.transaction_id)
            if remote_status in ('completed', 'successful', 'success'):
                _mark_payment_completed(payment, tx_id, raw_data)
                payment.refresh_from_db()
            else:
                logger.warning(
                    f'Order #{order.id}: PayChangu says payment is {remote_status!r} — skipping wallet credit'
                )
                return False

        if payment.status != 'completed':
            logger.warning(
                f'Order #{order.id}: payment still not completed after verify — skipping'
            )
            return False

        if payment.distributed_to_wallets:
            logger.info(f'Order #{order.id}: wallet already credited — skipping')
            return True

        with db_transaction.atomic():
            payment = Payment.objects.select_for_update().get(pk=payment.pk)
            if payment.distributed_to_wallets:
                return True

            restaurant = _get_restaurant_for_order(order)
            wallet, _ = RestaurantWallet.objects.get_or_create(restaurant=restaurant)

            restaurant_amount = payment.pending_restaurant_amount
            if not restaurant_amount or restaurant_amount <= 0:
                total_amount = Decimal(str(payment.amount))
                platform_fee = (total_amount * Decimal('10.00')) / Decimal('100')
                restaurant_amount = total_amount - platform_fee

            wallet.balance += restaurant_amount
            wallet.total_earned += restaurant_amount
            wallet.save(update_fields=['balance', 'total_earned'])

            WalletTransaction.objects.create(
                wallet=wallet,
                transaction_type='credit',
                amount=restaurant_amount,
                status='successful',
                description=(
                    f'Order #{order.id} accepted — payment from '
                    f'{order.customer.username} (MK{restaurant_amount:,.2f})'
                ),
            )

            payment.distributed_to_wallets = True
            payment.distributed_at = timezone.now()
            payment.save(update_fields=['distributed_to_wallets', 'distributed_at'])

        logger.info(
            f'✅ Wallet credited for order #{order.id}: '
            f'MK{restaurant_amount:,.2f} → {restaurant.name}'
        )

        try:
            from notifications.services import NotificationService
            NotificationService.send_notification(
                user=restaurant.owner,
                notification_type='wallet',
                title='Wallet Credited',
                message=(
                    f'Order #{order.id} accepted. '
                    f'MK{restaurant_amount:,.2f} credited to your wallet.'
                ),
                data={'order_id': str(order.id), 'amount': str(restaurant_amount)},
                send_email=True,
                send_sms=False,
                priority='high',
            )
        except Exception as e:
            logger.error(f'Wallet notification failed (non-fatal): {e}')

        return True

    except Payment.DoesNotExist:
        logger.warning(f'Order #{order.id}: no payment record found')
        return False
    except Exception as e:
        logger.error(f'Error crediting wallet for order #{order.id}: {e}', exc_info=True)
        return False


def _get_wallet_for_order(order) -> RestaurantWallet:
    restaurant = _get_restaurant_for_order(order)
    wallet, _ = RestaurantWallet.objects.get_or_create(restaurant=restaurant)
    return wallet


# ─── Payment Callback (Browser Redirect) ──────────────────────────────────────

@api_view(['GET'])
@drf_permission_classes([AllowAny])
def payment_callback(request):
    reference = request.GET.get('reference', '')
    cancelled = request.GET.get('cancelled', 'false')

    if cancelled == 'true':
        title = "Payment Cancelled"
        message = "Your payment was cancelled. Please return to the app."
        color = "#e53935"
        icon = "✕"
    else:
        title = "Payment Successful!"
        message = "Your payment was received. Please return to the app to track your order."
        color = "#43a047"
        icon = "✓"

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>{title}</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                background: #f5f5f5;
                display: flex;
                align-items: center;
                justify-content: center;
                min-height: 100vh;
                padding: 20px;
            }}
            .card {{
                background: white;
                border-radius: 16px;
                padding: 48px 32px;
                text-align: center;
                max-width: 400px;
                width: 100%;
                box-shadow: 0 4px 24px rgba(0,0,0,0.1);
            }}
            .icon {{
                width: 72px; height: 72px;
                border-radius: 50%;
                background: {color};
                color: white;
                font-size: 36px;
                display: flex;
                align-items: center;
                justify-content: center;
                margin: 0 auto 24px;
            }}
            h1 {{ font-size: 22px; color: #212121; margin-bottom: 12px; }}
            p {{ font-size: 15px; color: #757575; line-height: 1.5; margin-bottom: 32px; }}
            .ref {{ font-size: 12px; color: #bdbdbd; margin-top: 16px; }}
        </style>
    </head>
    <body>
        <div class="card">
            <div class="icon">{icon}</div>
            <h1>{title}</h1>
            <p>{message}</p>
            <div class="ref">Ref: {reference}</div>
        </div>
    </body>
    </html>
    """
    return HttpResponse(html, content_type='text/html')


# ─── ViewSet ──────────────────────────────────────────────────────────────────

class PaymentViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        try:
            return Payment.objects.get(pk=pk)
        except Payment.DoesNotExist:
            return None

    @action(detail=False, methods=['post'])
    def initiate(self, request):
        serializer = InitiatePaymentSerializer(
            data=request.data, context={'request': request}
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        order_id = serializer.validated_data['order_id']
        method = serializer.validated_data['method']
        phone = serializer.validated_data.get('phone_number', '')

        try:
            order = Order.objects.get(id=order_id, customer=request.user)
        except Order.DoesNotExist:
            return Response({'error': 'Order not found'}, status=status.HTTP_404_NOT_FOUND)

        if hasattr(order, 'payment') and order.payment.status == 'completed':
            return Response(
                {'error': 'Order already paid', 'reference': order.payment.reference},
                status=status.HTTP_400_BAD_REQUEST,
            )

        reference = f'FOOD-{order.id}-{uuid.uuid4().hex[:8].upper()}'
        payment = Payment.objects.create(
            order=order, amount=order.total_price, method=method,
            reference=reference, phone_number=phone or '', status='pending',
            subtotal_amount=order.total_price,
            delivery_fee=getattr(order, 'delivery_fee', 2000.0),
        )

        operator = PAYCHANGU_OPERATOR_MAP.get(method)
        paychangu_data = {
            'amount': str(order.total_price), 'currency': 'MWK',
            'email': request.user.email or f'user{order.customer_id}@foodstore.com',
            'first_name': getattr(request.user, 'first_name', '') or 'Customer',
            'last_name': getattr(request.user, 'last_name', '') or 'User',
            'reference': reference,
            'callback_url': f'{settings.WEBHOOK_BASE_URL}/api/payments/webhook/',
            'return_url': f'{settings.WEBHOOK_BASE_URL}/api/payments/callback/?reference={reference}',
            'cancel_url': f'{settings.WEBHOOK_BASE_URL}/api/payments/callback/?reference={reference}&cancelled=true',
        }
        if method in ('mpamba', 'airtel_money'):
            paychangu_data['phone_number'] = phone
            paychangu_data['mobile_money_operator'] = operator

        headers = {
            'Authorization': f'Bearer {settings.PAYCHANGU_SECRET_KEY}',
            'Content-Type': 'application/json', 'Accept': 'application/json',
        }

        try:
            response = requests.post(
                f'{settings.PAYCHANGU_BASE_URL}/payment',
                json=paychangu_data, headers=headers, timeout=30,
            )
            if response.status_code in (200, 201):
                response_data = response.json()
                data = response_data.get('data', response_data)
                payment.transaction_id = data.get('tx_ref') or data.get('transaction_id')
                payment.payment_details = response_data
                payment.status = 'processing'
                payment.save()
                checkout_url = data.get('checkout_url') or data.get('link')
                return Response({
                    'payment_id': payment.id, 'reference': reference,
                    'checkout_url': checkout_url, 'amount': str(order.total_price),
                    'currency': 'MWK', 'method': method, 'status': payment.status,
                }, status=status.HTTP_200_OK)
            else:
                payment.status = 'failed'
                payment.save()
                return Response(
                    {'error': 'Payment initiation failed', 'details': response.text},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except requests.RequestException as e:
            payment.status = 'failed'
            payment.save()
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'])
    def initiate_simple(self, request):
        logger.info('=== INITIATING SIMPLE PAYMENT ===')

        raw_order_id = request.data.get('order_id')
        if raw_order_id is None or str(raw_order_id).strip() == '':
            return Response({'error': 'order_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            order_id = int(raw_order_id)
        except (ValueError, TypeError):
            return Response(
                {'error': f'Invalid order_id "{raw_order_id}". Must be an integer.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            order = Order.objects.get(id=order_id, customer=request.user)
        except Order.DoesNotExist:
            return Response({'error': f'Order {order_id} not found'}, status=status.HTTP_404_NOT_FOUND)

        if hasattr(order, 'payment') and order.payment.status == 'completed':
            return Response(
                {'error': 'Order already paid', 'reference': order.payment.reference},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if hasattr(order, 'payment') and order.payment.status in ('pending', 'processing'):
            payment = order.payment
            reference = payment.reference
        else:
            reference = f'FOOD-{order.id}-{uuid.uuid4().hex[:8].upper()}'
            payment = Payment.objects.create(
                order=order, amount=order.total_price, method='paychangu',
                reference=reference, phone_number='', status='pending',
                subtotal_amount=order.total_price,
                delivery_fee=getattr(order, 'delivery_fee', 2000.0),
            )

        paychangu_data = {
            'amount': str(order.total_price), 'currency': 'MWK',
            'email': request.user.email or f'user{order.customer_id}@foodstore.com',
            'first_name': getattr(request.user, 'first_name', '') or 'Customer',
            'last_name': getattr(request.user, 'last_name', '') or 'User',
            'reference': reference, 'tx_ref': reference,
            'callback_url': f'{settings.WEBHOOK_BASE_URL}/api/payments/webhook/',
            'return_url': f'{settings.WEBHOOK_BASE_URL}/api/payments/callback/?reference={reference}',
            'cancel_url': f'{settings.WEBHOOK_BASE_URL}/api/payments/callback/?reference={reference}&cancelled=true',
            'custom_data': {
                'order_id': order.id, 'reference': reference, 'user_id': request.user.id,
            }
        }

        headers = {
            'Authorization': f'Bearer {settings.PAYCHANGU_SECRET_KEY}',
            'Content-Type': 'application/json', 'Accept': 'application/json',
        }

        try:
            response = requests.post(
                f'{settings.PAYCHANGU_BASE_URL}/payment',
                json=paychangu_data, headers=headers, timeout=30,
            )
            if response.status_code in (200, 201):
                response_data = response.json()
                data = response_data.get('data', response_data)
                paychangu_tx_ref = data.get('tx_ref') or data.get('reference')
                payment.transaction_id = paychangu_tx_ref
                payment.payment_details = response_data
                payment.status = 'processing'
                payment.save()
                checkout_url = data.get('checkout_url') or data.get('link')
                return Response({
                    'payment_id': payment.id, 'reference': reference,
                    'paychangu_reference': paychangu_tx_ref,
                    'checkout_url': checkout_url, 'amount': str(order.total_price),
                    'currency': 'MWK', 'method': 'paychangu', 'status': payment.status,
                }, status=status.HTTP_200_OK)
            else:
                payment.status = 'failed'
                payment.save()
                return Response(
                    {'error': 'Payment initiation failed', 'details': response.text},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except requests.RequestException as e:
            payment.status = 'failed'
            payment.save()
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'])
    def sync_payment(self, request):
        order_id = request.data.get('order_id')
        if not order_id:
            return Response({'error': 'order_id required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            order = Order.objects.get(id=order_id)
            payment = Payment.objects.get(order=order)
        except Order.DoesNotExist:
            return Response({'error': 'Order not found'}, status=status.HTTP_404_NOT_FOUND)
        except Payment.DoesNotExist:
            return Response({'error': 'Payment not found'}, status=status.HTTP_404_NOT_FOUND)

        if payment.status == 'completed':
            return Response({
                'status': 'completed',
                'order_id': order_id,
                'payment_status': order.payment_status,
            })

        paychangu_ref = payment.transaction_id or payment.reference
        remote_status, transaction_id, raw_data = _verify_with_paychangu(paychangu_ref)

        if remote_status in ('completed', 'successful', 'success'):
            _mark_payment_completed(payment, transaction_id, raw_data)
            payment.refresh_from_db()
            order.refresh_from_db()
            return Response({
                'status': 'completed',
                'message': 'Payment confirmed — awaiting restaurant acceptance',
                'order_id': order_id,
                'payment_status': order.payment_status,
            })

        return Response({
            'status': 'pending',
            'message': 'Payment still pending with PayChangu',
            'remote_status': remote_status,
        })

    @action(detail=False, methods=['get'])
    def status_by_reference(self, request):
        reference = request.query_params.get('reference')
        if not reference:
            return Response({'error': 'reference query param required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            payment = Payment.objects.select_related('order', 'order__customer').get(reference=reference)
        except Payment.DoesNotExist:
            return Response({'error': 'Payment not found'}, status=status.HTTP_404_NOT_FOUND)

        if payment.order.customer != request.user and not request.user.is_staff:
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

        if payment.status in ('processing', 'pending'):
            paychangu_ref = payment.transaction_id
            if paychangu_ref:
                remote_status, transaction_id, raw_data = _verify_with_paychangu(paychangu_ref)
                if remote_status in ('completed', 'successful', 'success'):
                    _mark_payment_completed(payment, transaction_id, raw_data)
                    payment.refresh_from_db()

        return Response({
            'reference': payment.reference,
            'status': payment.status,
            'amount': str(payment.amount),
            'order_id': payment.order.id,
            'order_status': payment.order.status,
            'payment_status': payment.order.payment_status,
            'distributed_to_wallets': payment.distributed_to_wallets,
        })

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    @method_decorator(csrf_exempt)
    def webhook(self, request):
        logger.info('=== WEBHOOK RECEIVED FROM PAYCHANGU ===')
        raw_body = request.body

        signature = (
            request.headers.get('X-Webhook-Signature')
            or request.headers.get('X-Paychangu-Signature')
        )

        if settings.PAYCHANGU_WEBHOOK_SECRET and signature:
            expected_signature = hmac.new(
                key=settings.PAYCHANGU_WEBHOOK_SECRET.encode('utf-8'),
                msg=raw_body,
                digestmod=hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(signature, expected_signature):
                logger.warning('Webhook rejected: invalid signature')
                return Response({'error': 'Invalid signature'}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            data = json.loads(raw_body.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            data = request.data

        logger.info(f'Webhook payload: {json.dumps(data, indent=2)}')

        event_data = data.get('data', data)
        paychangu_reference = event_data.get('reference') or event_data.get('tx_ref')
        custom_data = event_data.get('custom_data', {})
        our_reference = custom_data.get('reference')
        payment_status = event_data.get('status') or data.get('status')
        transaction_id = event_data.get('transaction_id') or data.get('transaction_id') or paychangu_reference

        WebhookLog.objects.create(
            reference=paychangu_reference or our_reference or 'unknown',
            payload=data,
        )

        payment = None
        if paychangu_reference:
            try:
                payment = Payment.objects.select_related('order', 'order__customer').get(
                    transaction_id=paychangu_reference
                )
            except Payment.DoesNotExist:
                pass

        if not payment and our_reference:
            try:
                payment = Payment.objects.select_related('order', 'order__customer').get(
                    reference=our_reference
                )
            except Payment.DoesNotExist:
                pass

        if not payment:
            logger.warning(f'Payment not found for reference: {paychangu_reference}')
            return Response({'status': 'ok'}, status=status.HTTP_200_OK)

        logger.info(f'Found payment #{payment.id}, order #{payment.order.id}, status={payment.status}')

        if payment_status in ('completed', 'successful', 'success', 'paid'):
            _mark_payment_completed(payment, transaction_id, data)
        elif payment_status == 'failed':
            payment.status = 'failed'
            payment.payment_details = data
            payment.save()
        elif payment_status in ('pending', 'processing'):
            payment.status = 'processing'
            payment.payment_details = data
            payment.save()

        return Response({'status': 'ok'}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    @method_decorator(csrf_exempt)
    def withdrawal_webhook(self, request):
        logger.info('=== WITHDRAWAL WEBHOOK RECEIVED ===')
        try:
            data = request.data
            reference = data.get('reference')
            status_webhook = data.get('status')
            if reference:
                try:
                    transaction = WalletTransaction.objects.get(reference=reference)
                    if status_webhook in ('completed', 'successful', 'success'):
                        transaction.status = 'completed'
                        transaction.save()
                    elif status_webhook == 'failed':
                        transaction.status = 'failed'
                        transaction.save()
                except WalletTransaction.DoesNotExist:
                    logger.warning(f'Withdrawal transaction not found: {reference}')
        except Exception as e:
            logger.error(f'Withdrawal webhook error: {e}', exc_info=True)
        return Response({'status': 'ok'}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'])
    def my_payments(self, request):
        payments = Payment.objects.filter(
            order__customer=request.user
        ).select_related('order').order_by('-created_at')
        return Response(PaymentSerializer(payments, many=True).data)

    def list(self, request):
        qs = (
            Payment.objects.all() if request.user.is_staff
            else Payment.objects.filter(order__customer=request.user)
        )
        return Response(PaymentSerializer(
            qs.select_related('order').order_by('-created_at'), many=True
        ).data)

    def retrieve(self, request, pk=None):
        payment = self.get_object(pk)
        if not payment:
            return Response({'error': 'Payment not found'}, status=status.HTTP_404_NOT_FOUND)
        if payment.order.customer != request.user and not request.user.is_staff:
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
        return Response(PaymentSerializer(payment).data)