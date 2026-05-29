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
from django.db import transaction as db_transaction
from rest_framework import viewsets, status
from rest_framework.decorators import action
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
    """
    Safely fetches the Restaurant for an order regardless of whether
    `order.restaurant` is a ForeignKey accessor or just `restaurant_id`.
    """
    try:
        restaurant = order.restaurant
        if isinstance(restaurant, Restaurant):
            return restaurant
    except AttributeError:
        pass

    return Restaurant.objects.select_related('wallet').get(id=order.restaurant_id)


def _distribute_to_wallet(payment, transaction_id=None, raw_data=None) -> bool:
    """
    Marks payment as completed but does NOT credit wallet yet.
    Wallet is only credited when restaurant confirms the order.
    """
    if payment.distributed_to_wallets:
        logger.info(f'Payment {payment.reference} already distributed — skipping')
        return False

    with db_transaction.atomic():
        payment = Payment.objects.select_for_update().get(pk=payment.pk)
        if payment.distributed_to_wallets:
            return False

        order = payment.order
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
        payment.distributed_to_wallets = False  # NOT distributed yet
        payment.distributed_at = None
        payment.save()

        # Only update payment status, NOT order status
        order.payment_status = 'paid'
        order.paid_at = getattr(order, 'paid_at', None) or timezone.now()
        order.save()

        logger.info(
            f'Payment completed: order #{order.id}, '
            f'amount=MK{restaurant_amount:,.2f} pending restaurant confirmation, '
            f'platform_fee=MK{platform_fee:,.2f}'
        )

    # Notification to customer
    try:
        from notifications.services import NotificationService
        NotificationService.send_notification(
            user=order.customer,
            notification_type='payment',
            title='Payment Successful',
            message=f'Your payment of MK{payment.amount:,.2f} for Order #{order.id} was successful. Waiting for restaurant confirmation.',
            data={
                'id': str(order.id),
                'transaction_id': str(transaction_id or ''),
                'amount': str(payment.amount),
            },
            send_email=True,
            send_sms=False,
            priority='high',
        )
    except Exception as e:
        logger.error(f'Notification failed (non-fatal): {e}')

    return True


def _credit_wallet_on_order_confirmation(order):
    """Credit restaurant wallet when order is confirmed by restaurant owner"""
    try:
        from payments.models import Payment
        from restaurants.models import RestaurantWallet, WalletTransaction
        
        payment = Payment.objects.get(order=order)
        
        # Check if payment is completed and not yet distributed
        if payment.status == 'completed' and not payment.distributed_to_wallets:
            restaurant = _get_restaurant_for_order(order)
            wallet, created = RestaurantWallet.objects.get_or_create(restaurant=restaurant)
            
            restaurant_amount = payment.pending_restaurant_amount
            if restaurant_amount == 0:
                total_amount = Decimal(str(payment.amount))
                platform_fee_percent = Decimal('10.00')
                platform_fee = (total_amount * platform_fee_percent) / Decimal('100')
                restaurant_amount = total_amount - platform_fee
            
            # Credit the wallet
            wallet.balance += restaurant_amount
            wallet.total_earned += restaurant_amount
            wallet.save(update_fields=['balance', 'total_earned'])
            
            # Create transaction record
            WalletTransaction.objects.create(
                wallet=wallet,
                transaction_type='credit',
                amount=restaurant_amount,
                status='successful',
                description=f'Payment from Order #{order.id} - {order.customer.username} (confirmed)',
            )
            
            # Mark payment as distributed
            payment.distributed_to_wallets = True
            payment.distributed_at = timezone.now()
            payment.restaurant_amount = restaurant_amount
            payment.save()
            
            logger.info(f'Wallet credited for order #{order.id}: MK{restaurant_amount:,.2f}')
            
            # Send notification to restaurant
            try:
                from notifications.services import NotificationService
                NotificationService.send_notification(
                    user=restaurant.owner,
                    notification_type='order',
                    title='Order Confirmed',
                    message=f'Order #{order.id} confirmed. MK{restaurant_amount:,.2f} credited to your wallet.',
                    data={'order_id': str(order.id), 'amount': str(restaurant_amount)},
                    send_email=True,
                    send_sms=False,
                    priority='high',
                )
            except Exception as e:
                logger.error(f'Notification failed: {e}')
                
            return True
            
    except Exception as e:
        logger.error(f'Error crediting wallet for order #{order.id}: {e}')
    
    return False


def _verify_with_paychangu(paychangu_tx_ref):
    """Calls PayChangu verify API using THEIR tx_ref"""
    if not paychangu_tx_ref:
        logger.warning('_verify_with_paychangu called with empty ref — skipping')
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


def _get_wallet_for_order(order) -> RestaurantWallet:
    """Returns the wallet for the restaurant that owns the order."""
    restaurant = _get_restaurant_for_order(order)
    wallet, _ = RestaurantWallet.objects.get_or_create(restaurant=restaurant)
    return wallet


# ─── ViewSet ──────────────────────────────────────────────────────────────────

class PaymentViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        try:
            return Payment.objects.get(pk=pk)
        except Payment.DoesNotExist:
            return None

    # ── INITIATE ──────────────────────────────────────────────────────────────

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
                {
                    'error': 'Order already paid',
                    'payment_status': order.payment.status,
                    'reference': order.payment.reference,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        reference = f'FOOD-{order.id}-{uuid.uuid4().hex[:8].upper()}'
        payment = Payment.objects.create(
            order=order,
            amount=order.total_price,
            method=method,
            reference=reference,
            phone_number=phone or '',
            status='pending',
            subtotal_amount=order.total_price,
            delivery_fee=getattr(order, 'delivery_fee', 2000.0),
        )

        operator = PAYCHANGU_OPERATOR_MAP.get(method)
        paychangu_data = {
            'amount': str(order.total_price),
            'currency': 'MWK',
            'email': request.user.email or f'user{order.customer_id}@foodstore.com',
            'first_name': getattr(request.user, 'first_name', '') or 'Customer',
            'last_name': getattr(request.user, 'last_name', '') or 'User',
            'reference': reference,
            'callback_url': f'{settings.WEBHOOK_BASE_URL}/api/payments/webhook/',
            'return_url': f'{settings.WEBHOOK_BASE_URL}/payment/status/?reference={reference}',
            'cancel_url': f'{settings.WEBHOOK_BASE_URL}/payment/status/?reference={reference}&cancelled=true',
        }
        if method in ('mpamba', 'airtel_money'):
            paychangu_data['phone_number'] = phone
            paychangu_data['mobile_money_operator'] = operator

        headers = {
            'Authorization': f'Bearer {settings.PAYCHANGU_SECRET_KEY}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }

        try:
            response = requests.post(
                f'{settings.PAYCHANGU_BASE_URL}/payment',
                json=paychangu_data,
                headers=headers,
                timeout=30,
            )
            if response.status_code in (200, 201):
                response_data = response.json()
                data = response_data.get('data', response_data)
                payment.transaction_id = data.get('tx_ref') or data.get('transaction_id')
                payment.payment_details = response_data
                payment.status = 'processing'
                payment.save()
                checkout_url = (
                    data.get('checkout_url') or data.get('link') or response_data.get('checkout_url')
                )
                return Response(
                    {
                        'payment_id': payment.id,
                        'reference': reference,
                        'checkout_url': checkout_url,
                        'amount': str(order.total_price),
                        'formatted_amount': f'MK{order.total_price:,.2f}',
                        'currency': 'MWK',
                        'method': method,
                        'status': payment.status,
                        'message': 'Redirect user to checkout_url to complete payment.',
                    },
                    status=status.HTTP_200_OK,
                )
            else:
                payment.status = 'failed'
                payment.payment_details = {'error': response.text, 'status_code': response.status_code}
                payment.save()
                return Response(
                    {'error': 'Payment initiation failed', 'details': response.text},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except requests.RequestException as e:
            payment.status = 'failed'
            payment.payment_details = {'error': str(e)}
            payment.save()
            return Response(
                {'error': 'Payment service unavailable', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # ── INITIATE SIMPLE ───────────────────────────────────────────────────────

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

        logger.info(f'Order #{order.id} found — total: MK{order.total_price}')

        if hasattr(order, 'payment') and order.payment.status == 'completed':
            return Response(
                {
                    'error': 'Order already paid',
                    'payment_status': order.payment.status,
                    'reference': order.payment.reference,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if hasattr(order, 'payment') and order.payment.status in ('pending', 'processing'):
            payment = order.payment
            reference = payment.reference
            logger.info(f'Reusing existing payment reference: {reference}')
        else:
            reference = f'FOOD-{order.id}-{uuid.uuid4().hex[:8].upper()}'
            payment = Payment.objects.create(
                order=order,
                amount=order.total_price,
                method='paychangu',
                reference=reference,
                phone_number='',
                status='pending',
                subtotal_amount=order.total_price,
                delivery_fee=getattr(order, 'delivery_fee', 2000.0),
            )
            logger.info(f'Created payment record #{payment.id}, reference={reference}')

        paychangu_data = {
            'amount': str(order.total_price),
            'currency': 'MWK',
            'email': request.user.email or f'user{order.customer_id}@foodstore.com',
            'first_name': getattr(request.user, 'first_name', '') or 'Customer',
            'last_name': getattr(request.user, 'last_name', '') or 'User',
            'reference': reference,
            'callback_url': f'{settings.WEBHOOK_BASE_URL}/api/payments/webhook/',
            'return_url': f'{settings.WEBHOOK_BASE_URL}/payment/status/?reference={reference}',
            'cancel_url': f'{settings.WEBHOOK_BASE_URL}/payment/status/?reference={reference}&cancelled=true',
        }

        headers = {
            'Authorization': f'Bearer {settings.PAYCHANGU_SECRET_KEY}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }

        logger.info(f'Sending to PayChangu: {json.dumps(paychangu_data)}')

        try:
            response = requests.post(
                f'{settings.PAYCHANGU_BASE_URL}/payment',
                json=paychangu_data,
                headers=headers,
                timeout=30,
            )
            logger.info(f'PayChangu response: {response.status_code} — {response.text}')

            if response.status_code in (200, 201):
                response_data = response.json()
                data = response_data.get('data', response_data)
                payment.transaction_id = data.get('tx_ref') or data.get('transaction_id')
                payment.payment_details = response_data
                payment.status = 'processing'
                payment.save()
                checkout_url = (
                    data.get('checkout_url') or data.get('link') or response_data.get('checkout_url')
                )
                logger.info(f'Payment initiated. Checkout URL: {checkout_url}')
                return Response(
                    {
                        'payment_id': payment.id,
                        'reference': reference,
                        'checkout_url': checkout_url,
                        'amount': str(order.total_price),
                        'formatted_amount': f'MK{order.total_price:,.2f}',
                        'currency': 'MWK',
                        'method': 'paychangu',
                        'status': payment.status,
                        'message': 'Redirect user to checkout_url.',
                    },
                    status=status.HTTP_200_OK,
                )
            else:
                payment.status = 'failed'
                payment.payment_details = {'error': response.text, 'status_code': response.status_code}
                payment.save()
                return Response(
                    {'error': 'Payment initiation failed', 'details': response.text},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except requests.RequestException as e:
            payment.status = 'failed'
            payment.payment_details = {'error': str(e)}
            payment.save()
            return Response(
                {'error': 'Payment service unavailable', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # ── WITHDRAWAL WEBHOOK ────────────────────────────────────────────────────

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    @method_decorator(csrf_exempt)
    def withdrawal_webhook(self, request):
        """Handle withdrawal webhook from PayChangu"""
        logger.info('=== WITHDRAWAL WEBHOOK RECEIVED ===')
        
        try:
            data = request.data
            reference = data.get('reference')
            status_webhook = data.get('status')
            
            logger.info(f'Withdrawal webhook data: {json.dumps(data, indent=2)}')
            
            if reference:
                try:
                    transaction = WalletTransaction.objects.get(reference=reference)
                    logger.info(f'Found withdrawal transaction: {transaction.reference}, current status: {transaction.status}')
                    
                    if status_webhook in ('completed', 'successful', 'success'):
                        transaction.status = 'completed'
                        transaction.metadata = {
                            **(transaction.metadata or {}),
                            'webhook_data': data,
                            'completed_at': timezone.now().isoformat(),
                        }
                        transaction.save()
                        logger.info(f'Withdrawal {reference} completed via webhook')
                        
                    elif status_webhook == 'failed':
                        transaction.status = 'failed'
                        transaction.metadata = {
                            **(transaction.metadata or {}),
                            'webhook_data': data,
                            'failure_reason': data.get('message', 'Unknown'),
                            'failed_at': timezone.now().isoformat(),
                        }
                        transaction.save()
                        
                        # Refund the wallet if transaction was already deducted
                        if transaction.wallet and transaction.status == 'processing':
                            transaction.wallet.balance += transaction.amount
                            transaction.wallet.save()
                            logger.info(f'Refunded wallet for failed withdrawal {reference}')
                            
                except WalletTransaction.DoesNotExist:
                    logger.warning(f'Withdrawal transaction not found for reference: {reference}')
                except Exception as e:
                    logger.error(f'Error processing withdrawal webhook: {e}', exc_info=True)
                    
        except Exception as e:
            logger.error(f'Withdrawal webhook processing error: {e}', exc_info=True)
            
        return Response({'status': 'ok', 'message': 'Webhook received'}, status=status.HTTP_200_OK)

    # ── WEBHOOK ───────────────────────────────────────────────────────────────

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
                WebhookLog.objects.create(
                    reference='invalid_signature',
                    payload={'error': 'Invalid signature', 'headers': dict(request.headers)},
                )
                return Response({'error': 'Invalid signature'}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            data = json.loads(raw_body.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            data = request.data

        logger.info(f'Webhook payload: {json.dumps(data, indent=2)}')

        event_data = data.get('data', data)
        
        reference = (
            event_data.get('reference') or 
            event_data.get('tx_ref') or 
            data.get('reference') or 
            data.get('tx_ref')
        )
        
        payment_status = event_data.get('status') or data.get('status')
        transaction_id = (
            event_data.get('transaction_id') or 
            event_data.get('id') or 
            data.get('transaction_id')
        )

        webhook_log = WebhookLog.objects.create(
            reference=reference or 'unknown',
            payload=data,
        )
        logger.info(f'Webhook logged: ID={webhook_log.id}, reference={reference}, status={payment_status}')

        if reference:
            try:
                try:
                    payment = Payment.objects.select_related('order', 'order__customer').get(
                        reference=reference
                    )
                    logger.info(f'Found payment by reference: {payment.id}')
                except Payment.DoesNotExist:
                    try:
                        payment = Payment.objects.select_related('order', 'order__customer').get(
                            transaction_id=reference
                        )
                        logger.info(f'Found payment by transaction_id: {payment.id}')
                    except Payment.DoesNotExist:
                        logger.warning(f'Payment not found for reference: {reference}')
                        webhook_log.reference = f'{reference}_not_found'
                        webhook_log.save()
                        return Response({'status': 'ok', 'message': 'Reference not found'}, status=200)

                logger.info(f'Found payment: ID={payment.id}, Order={payment.order.id}')

                if payment_status in ('completed', 'successful', 'success'):
                    distributed = _distribute_to_wallet(payment, transaction_id, data)
                    if not distributed:
                        logger.info('Webhook: payment already distributed')
                    else:
                        logger.info('Webhook: payment distributed successfully')
                elif payment_status == 'failed':
                    payment.status = 'failed'
                    payment.payment_details = data
                    payment.save()
                    logger.warning(f'Payment failed: reference={reference}')
                elif payment_status in ('pending', 'processing'):
                    payment.status = 'processing'
                    payment.payment_details = data
                    payment.save()
                else:
                    logger.warning(f'Unknown webhook status: {payment_status}')

            except Exception as e:
                logger.error(f'Webhook processing error: {e}', exc_info=True)
        else:
            logger.warning('Webhook received with no reference')

        return Response({'status': 'ok', 'message': 'Webhook received'}, status=status.HTTP_200_OK)

    # ── STATUS BY REFERENCE ───────────────────────────────────────────────────

    @action(detail=False, methods=['get'])
    def status_by_reference(self, request):
        reference = request.query_params.get('reference')
        if not reference:
            return Response(
                {'error': 'reference query param required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            payment = Payment.objects.select_related('order', 'order__customer').get(
                reference=reference
            )
        except Payment.DoesNotExist:
            return Response({'error': 'Payment not found'}, status=status.HTTP_404_NOT_FOUND)

        if payment.order.customer != request.user and not request.user.is_staff:
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

        if payment.status in ('processing', 'pending') and not payment.distributed_to_wallets:
            paychangu_ref = payment.transaction_id
            if paychangu_ref:
                logger.info(f'Polling status_by_reference for {reference}')
                remote_status, transaction_id, raw_data = _verify_with_paychangu(paychangu_ref)
                if remote_status in ('completed', 'successful', 'success'):
                    logger.info('PayChangu confirms completed — marking payment as completed')
                    _distribute_to_wallet(payment, transaction_id, raw_data)
                    payment.refresh_from_db()

        return Response({
            'reference': payment.reference,
            'status': payment.status,
            'status_display': payment.get_status_display(),
            'amount': str(payment.amount),
            'formatted_amount': f'MK{payment.amount:,.2f}',
            'method': payment.method,
            'method_display': payment.get_method_display(),
            'order_id': payment.order.id,
            'order_status': payment.order.status,
            'payment_status': payment.order.payment_status,
            'distributed_to_wallets': payment.distributed_to_wallets,
        })

    # ── MY PAYMENTS ───────────────────────────────────────────────────────────

    @action(detail=False, methods=['get'])
    def my_payments(self, request):
        payments = Payment.objects.filter(
            order__customer=request.user
        ).select_related('order').order_by('-created_at')
        serializer = PaymentSerializer(payments, many=True)
        return Response(serializer.data)

    def list(self, request):
        qs = (
            Payment.objects.all() if request.user.is_staff
            else Payment.objects.filter(order__customer=request.user)
        )
        serializer = PaymentSerializer(
            qs.select_related('order').order_by('-created_at'), many=True
        )
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        payment = self.get_object(pk)
        if not payment:
            return Response({'error': 'Payment not found'}, status=status.HTTP_404_NOT_FOUND)
        if payment.order.customer != request.user and not request.user.is_staff:
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
        return Response(PaymentSerializer(payment).data)