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

# Import wallet models
from restaurants.models import RestaurantWallet, WalletTransaction

logger = logging.getLogger(__name__)

# Maps our internal method name to the operator string PayChangu expects
PAYCHANGU_OPERATOR_MAP = {
    'mpamba': 'tnm',
    'airtel_money': 'airtel',
}


class PaymentViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        try:
            return Payment.objects.get(pk=pk)
        except Payment.DoesNotExist:
            return None

    # ------------------------------------------------------------------
    # INITIATE PAYMENT
    # ------------------------------------------------------------------
    @action(detail=False, methods=['post'])
    def initiate(self, request):
        """Initiate a mobile money payment with PayChangu"""
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

        # Check if already paid
        if hasattr(order, 'payment'):
            existing_payment = order.payment
            if existing_payment.status == 'completed':
                return Response(
                    {
                        'error': 'Order already paid',
                        'payment_status': existing_payment.status,
                        'reference': existing_payment.reference,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Generate unique reference
        reference = f"FOOD-{order.id}-{uuid.uuid4().hex[:8].upper()}"

        # Create payment record
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

        # Build PayChangu payload
        operator = PAYCHANGU_OPERATOR_MAP.get(method)
        paychangu_data = {
            'amount': str(order.total_price),
            'currency': 'MWK',
            'email': request.user.email or f"user{order.customer_id}@foodstore.com",
            'first_name': getattr(request.user, 'first_name', '') or 'Customer',
            'last_name': getattr(request.user, 'last_name', '') or 'User',
            'reference': reference,
            'callback_url': f"{settings.WEBHOOK_BASE_URL}/api/payments/webhook/",
            'return_url': f"{settings.WEBHOOK_BASE_URL}/payment/status/?reference={reference}",
            'cancel_url': f"{settings.WEBHOOK_BASE_URL}/payment/status/?reference={reference}&cancelled=true",
        }

        # Only add phone and operator if method is mpamba or airtel_money
        if method in ['mpamba', 'airtel_money']:
            paychangu_data['phone_number'] = phone
            paychangu_data['mobile_money_operator'] = operator

        headers = {
            'Authorization': f'Bearer {settings.PAYCHANGU_SECRET_KEY}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }

        logger.info(
            f"Initiating PayChangu payment: reference={reference}, "
            f"method={method}, amount={order.total_price}"
        )

        try:
            response = requests.post(
                f"{settings.PAYCHANGU_BASE_URL}/payment",
                json=paychangu_data,
                headers=headers,
                timeout=30,
            )

            logger.info(f"PayChangu response status: {response.status_code}")
            logger.info(f"PayChangu response body: {response.text}")

            if response.status_code in (200, 201):
                response_data = response.json()
                data = response_data.get('data', response_data)

                payment.transaction_id = data.get('tx_ref') or data.get('transaction_id')
                payment.payment_details = response_data
                payment.status = 'processing'
                payment.save()

                checkout_url = (
                    data.get('checkout_url')
                    or data.get('link')
                    or response_data.get('checkout_url')
                )

                return Response(
                    {
                        'payment_id': payment.id,
                        'reference': reference,
                        'checkout_url': checkout_url,
                        'amount': str(order.total_price),
                        'formatted_amount': f"MK{order.total_price:,.2f}",
                        'currency': 'MWK',
                        'method': method,
                        'status': payment.status,
                        'message': 'Payment initiated. Redirect the user to checkout_url to complete payment.',
                    },
                    status=status.HTTP_200_OK,
                )
            else:
                payment.status = 'failed'
                payment.payment_details = {
                    'error': response.text,
                    'status_code': response.status_code,
                }
                payment.save()

                logger.error(
                    f"PayChangu initiation failed: {response.status_code} - {response.text}"
                )

                return Response(
                    {
                        'error': 'Payment initiation failed',
                        'details': response.text,
                        'status_code': response.status_code,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        except requests.RequestException as e:
            payment.status = 'failed'
            payment.payment_details = {'error': str(e)}
            payment.save()

            logger.error(f"PayChangu request exception: {e}")

            return Response(
                {'error': 'Payment service unavailable', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # ------------------------------------------------------------------
    # SIMPLE PAYMENT INITIATION
    # ------------------------------------------------------------------
    @action(detail=False, methods=['post'])
    def initiate_simple(self, request):
        """
        Simplified payment initiation for PayChangu.
        Requires a real order_id (integer) for an existing order.
        """
        logger.info("=== INITIATING SIMPLE PAYMENT ===")

        raw_order_id = request.data.get('order_id')

        if raw_order_id is None or str(raw_order_id).strip() == '':
            return Response(
                {'error': 'order_id is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

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
            return Response(
                {'error': f'Order {order_id} not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        logger.info(f"Order #{order.id} found — total: MK{order.total_price}")

        if hasattr(order, 'payment') and order.payment.status == 'completed':
            return Response(
                {
                    'error': 'Order already paid',
                    'payment_status': order.payment.status,
                    'reference': order.payment.reference,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        existing_payment = None
        if hasattr(order, 'payment') and order.payment.status == 'pending':
            existing_payment = order.payment
            reference = existing_payment.reference
            logger.info(f"Reusing existing pending payment reference: {reference}")
        else:
            reference = f"FOOD-{order.id}-{uuid.uuid4().hex[:8].upper()}"
            existing_payment = Payment.objects.create(
                order=order,
                amount=order.total_price,
                method='paychangu',
                reference=reference,
                phone_number='',
                status='pending',
                subtotal_amount=order.total_price,
                delivery_fee=getattr(order, 'delivery_fee', 2000.0),
            )
            logger.info(f"Created payment record #{existing_payment.id}, reference={reference}")

        payment = existing_payment

        paychangu_data = {
            'amount': str(order.total_price),
            'currency': 'MWK',
            'email': request.user.email or f"user{order.customer_id}@foodstore.com",
            'first_name': getattr(request.user, 'first_name', '') or 'Customer',
            'last_name': getattr(request.user, 'last_name', '') or 'User',
            'reference': reference,
            'callback_url': f"{settings.WEBHOOK_BASE_URL}/api/payments/webhook/",
            'return_url': f"{settings.WEBHOOK_BASE_URL}/payment/status/?reference={reference}",
            'cancel_url': f"{settings.WEBHOOK_BASE_URL}/payment/status/?reference={reference}&cancelled=true",
        }

        headers = {
            'Authorization': f'Bearer {settings.PAYCHANGU_SECRET_KEY}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }

        logger.info(f"Sending to PayChangu: {json.dumps(paychangu_data)}")

        try:
            response = requests.post(
                f"{settings.PAYCHANGU_BASE_URL}/payment",
                json=paychangu_data,
                headers=headers,
                timeout=30,
            )

            logger.info(f"PayChangu response: {response.status_code} — {response.text}")

            if response.status_code in (200, 201):
                response_data = response.json()
                data = response_data.get('data', response_data)

                payment.transaction_id = data.get('tx_ref') or data.get('transaction_id')
                payment.payment_details = response_data
                payment.status = 'processing'
                payment.save()

                checkout_url = (
                    data.get('checkout_url')
                    or data.get('link')
                    or response_data.get('checkout_url')
                )

                logger.info(f"Payment initiated. Checkout URL: {checkout_url}")

                return Response(
                    {
                        'payment_id': payment.id,
                        'reference': reference,
                        'checkout_url': checkout_url,
                        'amount': str(order.total_price),
                        'formatted_amount': f"MK{order.total_price:,.2f}",
                        'currency': 'MWK',
                        'method': 'paychangu',
                        'status': payment.status,
                        'message': 'Payment initiated. Redirect user to checkout_url.',
                    },
                    status=status.HTTP_200_OK,
                )
            else:
                payment.status = 'failed'
                payment.payment_details = {
                    'error': response.text,
                    'status_code': response.status_code,
                }
                payment.save()

                logger.error(f"PayChangu rejected: {response.status_code} — {response.text}")

                return Response(
                    {
                        'error': 'Payment initiation failed',
                        'details': response.text,
                        'status_code': response.status_code,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        except requests.RequestException as e:
            payment.status = 'failed'
            payment.payment_details = {'error': str(e)}
            payment.save()

            logger.error(f"PayChangu request exception: {e}")

            return Response(
                {'error': 'Payment service unavailable', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # ------------------------------------------------------------------
    # WEBHOOK - CRITICAL FOR PRODUCTION
    # ------------------------------------------------------------------
    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    @method_decorator(csrf_exempt)
    def webhook(self, request):
        """PayChangu webhook endpoint for payment callbacks - Updates wallet"""
        logger.info("=== WEBHOOK RECEIVED FROM PAYCHANGU ===")

        raw_body = request.body

        # Verify HMAC signature
        signature = (
            request.headers.get('X-Webhook-Signature')
            or request.headers.get('X-Paychangu-Signature')
        )
        logger.info(f"Received signature: {signature}")

        if settings.PAYCHANGU_WEBHOOK_SECRET and signature:
            expected_signature = hmac.new(
                key=settings.PAYCHANGU_WEBHOOK_SECRET.encode('utf-8'),
                msg=raw_body,
                digestmod=hashlib.sha256,
            ).hexdigest()

            logger.info(f"Expected signature: {expected_signature}")

            if not hmac.compare_digest(signature, expected_signature):
                logger.warning("Webhook rejected: invalid signature")
                WebhookLog.objects.create(
                    reference='invalid_signature',
                    payload={'error': 'Invalid signature', 'headers': dict(request.headers)},
                )
                return Response({'error': 'Invalid signature'}, status=status.HTTP_401_UNAUTHORIZED)

            logger.info("Signature verified successfully")

        # Parse body
        try:
            data = json.loads(raw_body.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            data = request.data

        logger.info(f"Webhook payload: {json.dumps(data, indent=2)}")

        event_data = data.get('data', data)

        reference = (
            event_data.get('reference')
            or event_data.get('tx_ref')
            or data.get('reference')
            or data.get('tx_ref')
        )
        payment_status = event_data.get('status') or data.get('status')
        transaction_id = (
            event_data.get('transaction_id')
            or event_data.get('id')
            or data.get('transaction_id')
        )

        webhook_log = WebhookLog.objects.create(
            reference=reference or 'unknown',
            payload=data,
        )
        logger.info(f"Webhook logged: ID={webhook_log.id}, reference={reference}, status={payment_status}")

        if reference:
            try:
                payment = Payment.objects.get(reference=reference)
                logger.info(f"Found payment: ID={payment.id}, Order={payment.order.id}")

                if payment_status in ('completed', 'successful'):
                    with db_transaction.atomic():
                        if payment.distributed_to_wallets:
                            logger.info("Payment already distributed, skipping...")
                            return Response({'message': 'Already processed'})

                        # Update payment status
                        payment.status = 'completed'
                        payment.transaction_id = transaction_id
                        payment.payment_details = data
                        payment.paid_at = timezone.now()

                        order = payment.order

                        # Calculate amounts
                        total_amount = Decimal(str(payment.amount))
                        platform_fee_percent = Decimal('10.00')
                        platform_fee = (total_amount * platform_fee_percent) / Decimal('100')
                        restaurant_amount = total_amount - platform_fee

                        payment.platform_fee_percent = platform_fee_percent
                        payment.platform_fee = platform_fee
                        payment.restaurant_amount = restaurant_amount
                        payment.distributed_to_wallets = True
                        payment.distributed_at = timezone.now()
                        payment.save()

                        # Update order status
                        order.status = 'confirmed'
                        order.payment_status = 'paid'
                        order.paid_at = timezone.now()
                        order.save()

                        # CRITICAL: Update restaurant wallet
                        restaurant = order.restaurant
                        logger.info(f"Crediting wallet for restaurant: {restaurant.name}")

                        wallet, created = RestaurantWallet.objects.get_or_create(restaurant=restaurant)
                        if created:
                            logger.info(f"Created new wallet for {restaurant.name}")

                        wallet.balance += restaurant_amount
                        wallet.total_earned += restaurant_amount
                        wallet.save()

                        logger.info(
                            f"Wallet credited: added MK{restaurant_amount:,.2f}, "
                            f"new balance MK{wallet.balance:,.2f}"
                        )

                        # Create wallet transaction record
                        wallet_transaction = WalletTransaction.objects.create(
                            wallet=wallet,
                            transaction_type='credit',
                            amount=restaurant_amount,
                            status='successful',
                            description=f'Payment from Order #{order.id} - {order.customer.username}',
                        )
                        logger.info(f"Wallet transaction created: {wallet_transaction.reference}")

                        logger.info(
                            f"Payment completed and wallet credited: "
                            f"reference={reference}, order={order.id}"
                        )

                        # Send notification
                        try:
                            from notifications.services import NotificationService
                            NotificationService.send_notification(
                                user=order.customer,
                                notification_type='payment',
                                title='Payment Successful',
                                message=(
                                    f'Your payment of MK{payment.amount:,.2f} '
                                    f'for Order #{order.id} was successful.'
                                ),
                                data={
                                    'id': str(order.id),
                                    'transaction_id': str(transaction_id or ''),
                                    'amount': str(payment.amount),
                                },
                                send_email=True,
                                send_sms=False,
                                priority='high',
                            )
                        except Exception as notif_err:
                            logger.error(f"Notification failed (non-fatal): {notif_err}")

                elif payment_status == 'failed':
                    payment.status = 'failed'
                    payment.payment_details = data
                    payment.save()
                    logger.warning(f"Payment failed: reference={reference}")

                elif payment_status in ('pending', 'processing'):
                    payment.status = 'processing'
                    payment.payment_details = data
                    payment.save()
                    logger.info(f"Payment still processing for Order #{payment.order.id}")

                else:
                    logger.warning(f"Unknown payment status from webhook: {payment_status}")

            except Payment.DoesNotExist:
                logger.warning(f"Webhook received for unknown reference: {reference}")
                webhook_log.reference = f"{reference}_not_found"
                webhook_log.save()
            except Exception as e:
                logger.error(f"Webhook processing error: {e}", exc_info=True)
        else:
            logger.warning("Webhook received with no reference field")

        return Response({'status': 'ok', 'message': 'Webhook received'}, status=status.HTTP_200_OK)

    # ------------------------------------------------------------------
    # CHECK AND UPDATE WALLET (SYNC ENDPOINT)
    # ------------------------------------------------------------------
    @action(detail=False, methods=['get'])
    def check_and_update_wallet(self, request):
        """Force check and update wallet for an order"""
        order_id = request.query_params.get('order_id')
        
        if not order_id:
            return Response({'error': 'order_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            payment = Payment.objects.get(order_id=order_id)
            order = payment.order
            
            # Check if user has permission
            if payment.order.customer != request.user and not request.user.is_staff:
                return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
            
            # If already distributed, return current state
            if payment.distributed_to_wallets:
                wallet = RestaurantWallet.objects.get(restaurant=order.restaurant)
                return Response({
                    'already_updated': True,
                    'wallet_balance': float(wallet.balance),
                    'payment_status': payment.status,
                    'order_id': order.id
                })
            
            # If payment is completed but wallet not updated
            if payment.status == 'completed' and not payment.distributed_to_wallets:
                total_amount = Decimal(str(payment.amount))
                platform_fee_percent = Decimal('10.00')
                platform_fee = (total_amount * platform_fee_percent) / Decimal('100')
                restaurant_amount = total_amount - platform_fee
                
                restaurant = order.restaurant
                wallet, _ = RestaurantWallet.objects.get_or_create(restaurant=restaurant)
                
                wallet.balance += restaurant_amount
                wallet.total_earned += restaurant_amount
                wallet.save()
                
                payment.distributed_to_wallets = True
                payment.restaurant_amount = restaurant_amount
                payment.platform_fee = platform_fee
                payment.distributed_at = timezone.now()
                payment.save()
                
                WalletTransaction.objects.create(
                    wallet=wallet,
                    transaction_type='credit',
                    amount=restaurant_amount,
                    status='successful',
                    description=f'Payment from Order #{order.id} (manual sync)'
                )
                
                logger.info(f"Wallet synced for Order #{order.id}: added MK{restaurant_amount:,.2f}")
                
                return Response({
                    'updated': True,
                    'wallet_balance': float(wallet.balance),
                    'restaurant_amount': float(restaurant_amount),
                    'platform_fee': float(platform_fee),
                    'order_id': order.id
                })
            
            return Response({
                'updated': False,
                'payment_status': payment.status,
                'distributed': payment.distributed_to_wallets,
                'order_id': order.id,
                'message': f'Payment status is {payment.status}, cannot update wallet'
            })
            
        except Payment.DoesNotExist:
            return Response({'error': 'Payment not found'}, status=status.HTTP_404_NOT_FOUND)
        except RestaurantWallet.DoesNotExist:
            return Response({'error': 'Wallet not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Wallet sync error: {e}")
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # ------------------------------------------------------------------
    # MANUAL PAYMENT CONFIRMATION FOR TESTING
    # ------------------------------------------------------------------
    @action(detail=False, methods=['post'])
    def test_confirm_payment(self, request):
        """
        Manually confirm a payment for testing (bypass webhook).
        This should be used for testing only and removed in production.
        """
        order_id = request.data.get('order_id')
        reference = request.data.get('reference')
        
        if not order_id and not reference:
            return Response({'error': 'order_id or reference required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            if order_id:
                payment = Payment.objects.get(order_id=order_id)
            else:
                payment = Payment.objects.get(reference=reference)
            
            # Check if user has permission
            if payment.order.customer != request.user and not request.user.is_staff:
                return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
            
            # Mark as completed
            payment.status = 'completed'
            payment.transaction_id = f"MANUAL_{uuid.uuid4().hex[:8]}"
            payment.paid_at = timezone.now()
            payment.save()
            
            # Update order
            order = payment.order
            order.status = 'confirmed'
            order.payment_status = 'paid'
            order.paid_at = timezone.now()
            order.save()
            
            # Update restaurant wallet
            total_amount = Decimal(str(payment.amount))
            platform_fee_percent = Decimal('10.00')
            platform_fee = (total_amount * platform_fee_percent) / Decimal('100')
            restaurant_amount = total_amount - platform_fee
            
            restaurant = order.restaurant
            wallet, created = RestaurantWallet.objects.get_or_create(restaurant=restaurant)
            
            wallet.balance += restaurant_amount
            wallet.total_earned += restaurant_amount
            wallet.save()
            
            WalletTransaction.objects.create(
                wallet=wallet,
                transaction_type='credit',
                amount=restaurant_amount,
                status='successful',
                description=f'Manual payment confirmation for Order #{order.id}'
            )
            
            logger.info(f"Manual payment confirmation: Order #{order.id}, Restaurant: {restaurant.name}")
            
            return Response({
                'status': 'completed',
                'message': 'Payment confirmed manually',
                'order_id': order.id,
                'wallet_balance': float(wallet.balance),
                'restaurant_amount': float(restaurant_amount)
            })
            
        except Payment.DoesNotExist:
            return Response({'error': 'Payment not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Manual confirmation error: {e}")
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # ------------------------------------------------------------------
    # VERIFY
    # ------------------------------------------------------------------
    @action(detail=False, methods=['post'])
    def verify(self, request):
        """Verify payment status with PayChangu"""
        serializer = VerifyPaymentSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        reference = serializer.validated_data['reference']

        try:
            payment = Payment.objects.get(reference=reference)
        except Payment.DoesNotExist:
            return Response({'error': 'Payment not found'}, status=status.HTTP_404_NOT_FOUND)

        headers = {
            'Authorization': f'Bearer {settings.PAYCHANGU_SECRET_KEY}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }

        try:
            response = requests.get(
                f"{settings.PAYCHANGU_BASE_URL}/payment/verify/{reference}",
                headers=headers,
                timeout=30,
            )

            if response.status_code == 200:
                response_data = response.json()
                data = response_data.get('data', response_data)
                remote_status = data.get('status', '')

                if remote_status in ('completed', 'successful'):
                    payment.status = 'completed'
                    payment.transaction_id = data.get('transaction_id') or data.get('id')
                    payment.payment_details = response_data
                    payment.save()

                    order = payment.order
                    order.status = 'confirmed'
                    order.payment_status = 'paid'
                    order.paid_at = timezone.now()
                    order.save()

                    if not payment.distributed_to_wallets:
                        restaurant = order.restaurant
                        wallet, _ = RestaurantWallet.objects.get_or_create(restaurant=restaurant)

                        total_amount = Decimal(str(payment.amount))
                        platform_fee_percent = Decimal('10.00')
                        platform_fee = (total_amount * platform_fee_percent) / Decimal('100')
                        restaurant_amount = total_amount - platform_fee

                        payment.platform_fee = platform_fee
                        payment.restaurant_amount = restaurant_amount
                        payment.distributed_to_wallets = True
                        payment.distributed_at = timezone.now()
                        payment.save()

                        wallet.balance += restaurant_amount
                        wallet.total_earned += restaurant_amount
                        wallet.save()

                        WalletTransaction.objects.create(
                            wallet=wallet,
                            transaction_type='credit',
                            amount=restaurant_amount,
                            status='successful',
                            description=f'Payment from Order #{order.id} via verification',
                        )

                    return Response(
                        {
                            'status': 'completed',
                            'message': 'Payment verified successfully',
                            'reference': reference,
                            'amount': str(payment.amount),
                            'formatted_amount': f"MK{payment.amount:,.2f}",
                        },
                        status=status.HTTP_200_OK,
                    )

                elif remote_status == 'failed':
                    payment.status = 'failed'
                    payment.payment_details = response_data
                    payment.save()
                    return Response(
                        {'status': 'failed', 'message': 'Payment failed', 'reference': reference},
                        status=status.HTTP_200_OK,
                    )

                else:
                    return Response(
                        {
                            'status': payment.status,
                            'message': 'Payment pending verification',
                            'reference': reference,
                        },
                        status=status.HTTP_200_OK,
                    )
            else:
                logger.warning(f"PayChangu verify returned {response.status_code}: {response.text}")
                return Response(
                    {
                        'status': payment.status,
                        'message': 'Unable to verify with PayChangu',
                        'reference': reference,
                    },
                    status=status.HTTP_200_OK,
                )

        except requests.RequestException as e:
            logger.error(f"PayChangu verify exception: {e}")
            return Response(
                {
                    'status': payment.status,
                    'message': 'Verification service unavailable',
                    'details': str(e),
                    'reference': reference,
                },
                status=status.HTTP_200_OK,
            )

    # ------------------------------------------------------------------
    # STATUS BY REFERENCE
    # ------------------------------------------------------------------
    @action(detail=False, methods=['get'])
    def status_by_reference(self, request):
        reference = request.query_params.get('reference')
        if not reference:
            return Response(
                {'error': 'reference query param required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            payment = Payment.objects.get(reference=reference)
        except Payment.DoesNotExist:
            return Response({'error': 'Payment not found'}, status=status.HTTP_404_NOT_FOUND)

        if payment.order.customer != request.user and not request.user.is_staff:
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

        return Response(
            {
                'reference': payment.reference,
                'status': payment.status,
                'status_display': payment.get_status_display(),
                'amount': str(payment.amount),
                'formatted_amount': f"MK{payment.amount:,.2f}",
                'method': payment.method,
                'method_display': payment.get_method_display(),
                'order_id': payment.order.id,
                'transaction_id': payment.transaction_id,
                'distributed_to_wallets': payment.distributed_to_wallets,
                'distributed_at': payment.distributed_at,
            }
        )

    # ------------------------------------------------------------------
    # MY PAYMENTS
    # ------------------------------------------------------------------
    @action(detail=False, methods=['get'])
    def my_payments(self, request):
        payments = Payment.objects.filter(
            order__customer=request.user
        ).order_by('-created_at')
        serializer = PaymentSerializer(payments, many=True)
        return Response(serializer.data)

    # ------------------------------------------------------------------
    # LIST / RETRIEVE
    # ------------------------------------------------------------------
    def list(self, request):
        if request.user.is_staff:
            payments = Payment.objects.all()
        else:
            payments = Payment.objects.filter(order__customer=request.user)

        payments = payments.order_by('-created_at')
        serializer = PaymentSerializer(payments, many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        payment = self.get_object(pk)
        if not payment:
            return Response({'error': 'Payment not found'}, status=status.HTTP_404_NOT_FOUND)

        if payment.order.customer != request.user and not request.user.is_staff:
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

        serializer = PaymentSerializer(payment)
        return Response(serializer.data)