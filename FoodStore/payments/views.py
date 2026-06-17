# payments/views.py - COMPLETE UPDATED VERSION

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

    # INITIATE PAYMENT
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
        phone = serializer.validated_data['phone_number']

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
            phone_number=phone,
            status='pending',
        )

        # Build PayChangu payload
        operator = PAYCHANGU_OPERATOR_MAP[method]
        paychangu_data = {
            'amount': str(order.total_price),
            'currency': 'MWK',
            'email': request.user.email or f"user{order.customer_id}@foodstore.com",
            'first_name': getattr(request.user, 'first_name', '') or 'Customer',
            'last_name': getattr(request.user, 'last_name', '') or 'User',
            'reference': reference,
            'phone_number': phone,
            'mobile_money_operator': operator,
            'callback_url': f"{settings.WEBHOOK_BASE_URL}/api/payments/webhook/",
            'return_url': f"{settings.WEBHOOK_BASE_URL}/payment/status/?reference={reference}",
            'cancel_url': f"{settings.WEBHOOK_BASE_URL}/payment/status/?reference={reference}&cancelled=true",
        }

        headers = {
            'Authorization': f'Bearer {settings.PAYCHANGU_SECRET_KEY}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }

        logger.info(
            f"Initiating PayChangu payment: reference={reference}, "
            f"method={method}, operator={operator}, amount={order.total_price}"
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

    # WEBHOOK
    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    @method_decorator(csrf_exempt)
    def webhook(self, request):
        """PayChangu webhook endpoint for payment callbacks"""
        print("\n" + "=" * 60)
        print("WEBHOOK RECEIVED FROM PAYCHANGU")
        print("=" * 60)

        raw_body = request.body

        # Verify HMAC signature
        signature = (
            request.headers.get('X-Webhook-Signature')
            or request.headers.get('X-Paychangu-Signature')
        )
        print(f"Received signature: {signature}")

        if settings.PAYCHANGU_WEBHOOK_SECRET and signature:
            expected_signature = hmac.new(
                key=settings.PAYCHANGU_WEBHOOK_SECRET.encode('utf-8'),
                msg=raw_body,
                digestmod=hashlib.sha256,
            ).hexdigest()

            print(f"Expected signature: {expected_signature}")

            if not hmac.compare_digest(signature, expected_signature):
                logger.warning("Webhook rejected: invalid signature")
                WebhookLog.objects.create(
                    reference='invalid_signature',
                    payload={'error': 'Invalid signature', 'headers': dict(request.headers)},
                )
                return Response({'error': 'Invalid signature'}, status=status.HTTP_401_UNAUTHORIZED)

            print("Signature verified successfully")

        # Parse body
        try:
            data = json.loads(raw_body.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            data = request.data

        print(f"Webhook payload: {json.dumps(data, indent=2)}")

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
        print(f"Webhook logged: ID={webhook_log.id}, reference={reference}, status={payment_status}")

        if reference:
            try:
                payment = Payment.objects.get(reference=reference)
                print(f"Found payment: ID={payment.id}, Order={payment.order.id}")

                if payment_status in ('completed', 'successful'):
                    payment.status = 'completed'
                    payment.transaction_id = transaction_id
                    payment.payment_details = data
                    payment.save()

                    order = payment.order
                    order.status = 'confirmed'
                    order.payment_status = 'paid'
                    order.paid_at = timezone.now()
                    order.save()

                    logger.info(f"Payment completed: reference={reference}, order={order.id}")
                    print(f"Payment completed. Order #{order.id} status -> confirmed")

                    # ========== NEW: Create escrow for the payment ==========
                    try:
                        from .services.escrow_service import EscrowService
                        EscrowService.create_escrow(order, payment)
                        print(f"Escrow created for Order #{order.id}")
                    except Exception as escrow_err:
                        logger.error(f"Failed to create escrow: {escrow_err}")
                        print(f"Error creating escrow: {escrow_err}")

                    try:
                        from .services.wallet_service import WalletDistributionService
                        # Create wallet for customer if not exists
                        WalletDistributionService.get_or_create_wallet(
                            user=order.customer, 
                            user_type='customer'
                        )
                        print(f"Wallet initialized for customer {order.customer.username}")
                    except Exception as wallet_err:
                        logger.error(f"Failed to initialize customer wallet: {wallet_err}")

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
                    logger.info(f"Payment failed: reference={reference}")
                    print(f"Payment failed for Order #{payment.order.id}")

                elif payment_status in ('pending', 'processing'):
                    payment.status = 'processing'
                    payment.payment_details = data
                    payment.save()
                    print(f"Payment still processing for Order #{payment.order.id}")

                else:
                    logger.warning(f"Unknown payment status from webhook: {payment_status}")
                    print(f"Unknown status '{payment_status}' — no action taken")

            except Payment.DoesNotExist:
                logger.warning(f"Webhook received for unknown reference: {reference}")
                webhook_log.reference = f"{reference}_not_found"
                webhook_log.save()
                print(f"Payment not found for reference: {reference}")
        else:
            logger.warning("Webhook received with no reference field")
            print("No reference found in webhook data")

        print("=" * 60 + "\n")
        return Response({'status': 'ok', 'message': 'Webhook received'}, status=status.HTTP_200_OK)

    # VERIFY
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

                    # Create escrow if not exists
                    try:
                        from .services.escrow_service import EscrowService
                        if not hasattr(order, 'escrow'):
                            EscrowService.create_escrow(order, payment)
                    except Exception as escrow_err:
                        logger.error(f"Failed to create escrow on verify: {escrow_err}")

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

    # DISTRIBUTE PAYMENT TO WALLETS (NEW ENDPOINT)
    @action(detail=False, methods=['post'])
    def distribute(self, request):
        """
        Manually distribute payment to wallets after delivery.
        Normally this happens automatically, but this endpoint allows manual trigger.
        """
        reference = request.data.get('reference')
        if not reference:
            return Response(
                {'error': 'reference is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            payment = Payment.objects.get(reference=reference)
        except Payment.DoesNotExist:
            return Response({'error': 'Payment not found'}, status=status.HTTP_404_NOT_FOUND)

        # Check permissions
        order = payment.order
        if order.customer != request.user and not request.user.is_staff:
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

        # Check if already distributed
        if payment.distributed_to_wallets:
            return Response(
                {'message': 'Payment already distributed', 'distributed_at': payment.distributed_at},
                status=status.HTTP_200_OK
            )

        # Check if order is delivered
        if order.status != 'delivered':
            return Response(
                {'error': f'Order not delivered yet. Current status: {order.status}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Distribute to wallets
        from .services.wallet_service import WalletDistributionService
        
        with db_transaction.atomic():
            success = WalletDistributionService.distribute_to_wallets(payment)
            
            if success:
                return Response(
                    {
                        'success': True,
                        'message': 'Payment distributed to wallets successfully',
                        'reference': reference,
                        'distributed_at': payment.distributed_at
                    },
                    status=status.HTTP_200_OK
                )
            else:
                return Response(
                    {'error': 'Distribution failed. Check logs for details.'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

    # GET WALLET BALANCE (NEW ENDPOINT)
    @action(detail=False, methods=['get'])
    def wallet_balance(self, request):
        """Get current user's wallet balance"""
        from orders.models import Wallet
        
        try:
            wallet = Wallet.objects.get(user=request.user)
            return Response({
                'balance': str(wallet.balance),
                'formatted_balance': f"MK{wallet.balance:,.2f}",
                'user_type': wallet.user_type,
                'total_earned': str(wallet.total_earned),
                'total_withdrawn': str(wallet.total_withdrawn),
                'currency': wallet.currency
            })
        except Wallet.DoesNotExist:
            # Create wallet if doesn't exist
            wallet = Wallet.objects.create(
                user=request.user,
                user_type='customer',
                balance=Decimal('0')
            )
            return Response({
                'balance': '0.00',
                'formatted_balance': 'MK0.00',
                'user_type': 'customer',
                'total_earned': '0.00',
                'total_withdrawn': '0.00',
                'currency': 'MWK'
            })

    # GET TRANSACTION HISTORY (NEW ENDPOINT)
    @action(detail=False, methods=['get'])
    def transactions(self, request):
        """Get user's transaction history"""
        from orders.models import Transaction
        
        transactions = Transaction.objects.filter(
            user=request.user
        ).order_by('-created_at')[:50]  # Last 50 transactions
        
        data = []
        for tx in transactions:
            data.append({
                'transaction_id': tx.transaction_id,
                'amount': str(tx.amount),
                'formatted_amount': f"MK{tx.amount:,.2f}",
                'type': tx.transaction_type,
                'status': tx.status,
                'description': tx.description,
                'created_at': tx.created_at.isoformat(),
                'order_id': tx.order.id if tx.order else None
            })
        
        return Response({
            'transactions': data,
            'total_count': transactions.count()
        })

    # REQUEST WITHDRAWAL (NEW ENDPOINT)
    @action(detail=False, methods=['post'])
    def withdraw(self, request):
        """Request withdrawal from wallet to mobile money"""
        from orders.models import Wallet, WithdrawalRequest
        
        amount = request.data.get('amount')
        phone_number = request.data.get('phone_number')
        provider = request.data.get('provider', 'mpamba')  # mpamba or airtel_money
        
        if not amount or not phone_number:
            return Response(
                {'error': 'amount and phone_number are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            amount = Decimal(str(amount))
        except:
            return Response(
                {'error': 'Invalid amount'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get user's wallet
        try:
            wallet = Wallet.objects.get(user=request.user)
        except Wallet.DoesNotExist:
            return Response(
                {'error': 'No wallet found for this user'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check sufficient balance
        if wallet.balance < amount:
            return Response(
                {'error': f'Insufficient balance. Available: MK{wallet.balance:,.2f}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check minimum withdrawal
        min_withdrawal = Decimal('1000.00')
        if amount < min_withdrawal:
            return Response(
                {'error': f'Minimum withdrawal amount is MK{min_withdrawal:,.2f}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create withdrawal request
        withdrawal = WithdrawalRequest.objects.create(
            user=request.user,
            amount=amount,
            phone_number=phone_number,
            provider=provider,
            status='pending'
        )
        
        # Optionally: Deduct from wallet immediately or wait for processing
        # We'll deduct immediately to prevent double spending
        wallet.balance -= amount
        wallet.total_withdrawn += amount
        wallet.save()
        
        # Create transaction record
        from orders.models import Transaction
        Transaction.objects.create(
            transaction_id=f"WTH-{uuid.uuid4().hex[:12].upper()}",
            order=None,
            user=request.user,
            amount=amount,
            transaction_type='withdrawal',
            status='pending',
            reference=withdrawal.reference if hasattr(withdrawal, 'reference') else None,
            description=f'Withdrawal request to {phone_number} via {provider}',
            balance_before=wallet.balance + amount,
            balance_after=wallet.balance
        )
        
        # TODO: Integrate with PayChangu withdrawal API here
        # For now, just log it
        logger.info(f"Withdrawal requested: User={request.user.id}, Amount={amount}, Phone={phone_number}")
        
        return Response({
            'success': True,
            'message': 'Withdrawal request submitted successfully',
            'withdrawal_id': withdrawal.id,
            'amount': str(amount),
            'formatted_amount': f"MK{amount:,.2f}",
            'status': 'pending',
            'note': 'Your request is being processed. Funds will be sent to your mobile money within 24 hours.'
        })

    # STATUS
    @action(detail=True, methods=['get'])
    def status(self, request, pk=None):
        payment = self.get_object(pk)
        if not payment:
            return Response({'error': 'Payment not found'}, status=status.HTTP_404_NOT_FOUND)

        if payment.order.customer != request.user and not request.user.is_staff:
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

        serializer = PaymentStatusSerializer(payment)
        return Response(serializer.data)

    # STATUS BY REFERENCE
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

    # MY PAYMENTS
    @action(detail=False, methods=['get'])
    def my_payments(self, request):
        payments = Payment.objects.filter(
            order__customer=request.user
        ).order_by('-created_at')
        serializer = PaymentSerializer(payments, many=True)
        return Response(serializer.data)

    # LIST / RETRIEVE
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