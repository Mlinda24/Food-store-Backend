import requests
import uuid
import hmac
import hashlib
import json
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
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
    PaymentStatusSerializer
)


class PaymentViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    
    def get_object(self, pk):
        """Helper to get payment object"""
        try:
            return Payment.objects.get(pk=pk)
        except Payment.DoesNotExist:
            return None
    
    @action(detail=False, methods=['post'])
    def initiate(self, request):
        """Initiate a payment with PayChangu"""
        serializer = InitiatePaymentSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        order_id = serializer.validated_data['order_id']
        method = serializer.validated_data['method']
        phone = serializer.validated_data.get('phone_number', '')
        
        try:
            order = Order.objects.get(id=order_id, customer=request.user)
        except Order.DoesNotExist:
            return Response({'error': 'Order not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Check if payment already exists
        if hasattr(order, 'payment'):
            existing_payment = order.payment
            if existing_payment.status == 'completed':
                return Response({
                    'error': 'Order already paid',
                    'payment_status': existing_payment.status,
                    'reference': existing_payment.reference
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Generate unique reference
        reference = f"FOOD-{order.id}-{uuid.uuid4().hex[:8].upper()}"
        
        # Create payment record
        payment = Payment.objects.create(
            order=order,
            amount=order.total_price,
            method=method,
            reference=reference,
            phone_number=phone,
            status='pending'
        )
        
        # Prepare PayChangu request
        paychangu_data = {
            'amount': str(order.total_price),
            'currency': 'MWK',
            'email': request.user.email or f"user{order.customer_id}@foodstore.com",
            'reference': reference,
            'callback_url': f"{settings.WEBHOOK_BASE_URL}/api/payments/webhook/",
            'return_url': f"{settings.WEBHOOK_BASE_URL}/payment/status/?reference={reference}",
            'method': method,
        }
        
        if phone and method in ['mpesa', 'airtel_money']:
            paychangu_data['phone'] = phone
        
        # PayChangu API headers
        headers = {
            'Authorization': f'Bearer {settings.PAYCHANGU_SECRET_KEY}',
            'Content-Type': 'application/json',
            'x-api-key': settings.PAYCHANGU_PUBLIC_KEY
        }
        
        try:
            # Call PayChangu API
            response = requests.post(
                f"{settings.PAYCHANGU_BASE_URL}/payment/initiate",
                json=paychangu_data,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                response_data = response.json()
                payment.transaction_id = response_data.get('transaction_id')
                payment.payment_details = response_data
                payment.status = 'processing'
                payment.save()
                
                return Response({
                    'payment_id': payment.id,
                    'reference': reference,
                    'checkout_url': response_data.get('checkout_url'),
                    'amount': str(order.total_price),
                    'status': payment.status,
                    'message': 'Payment initiated successfully'
                }, status=status.HTTP_200_OK)
            else:
                payment.status = 'failed'
                payment.payment_details = {'error': response.text}
                payment.save()
                return Response({
                    'error': 'Payment initiation failed',
                    'details': response.text
                }, status=status.HTTP_400_BAD_REQUEST)
                
        except requests.RequestException as e:
            payment.status = 'failed'
            payment.payment_details = {'error': str(e)}
            payment.save()
            return Response({
                'error': 'Payment service unavailable',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    @method_decorator(csrf_exempt)
    def webhook(self, request):
        """PayChangu webhook endpoint for payment callbacks"""
        print("\n" + "="*60)
        print("🔔 WEBHOOK RECEIVED FROM PAYCHANGU")
        print("="*60)
        
        # Log headers for debugging
        print("\n📋 Headers:")
        for key, value in request.headers.items():
            if key.startswith('X-') or key.startswith('HTTP_X'):
                print(f"   {key}: {value}")
        
        # Get signature from header
        signature = request.headers.get('X-Webhook-Signature')
        print(f"\n🔐 Webhook Signature: {signature}")
        
        # Verify webhook signature
        if settings.PAYCHANGU_WEBHOOK_SECRET:
            payload = request.body
            expected_signature = hmac.new(
                settings.PAYCHANGU_WEBHOOK_SECRET.encode('utf-8'),
                payload,
                hashlib.sha256
            ).hexdigest()
            
            print(f"🔑 Expected Signature: {expected_signature}")
            
            if signature and not hmac.compare_digest(signature, expected_signature):
                print("❌ INVALID SIGNATURE - Webhook rejected!")
                
                # Log invalid webhook
                WebhookLog.objects.create(
                    reference='invalid_signature',
                    payload={'error': 'Invalid signature', 'headers': dict(request.headers)}
                )
                return Response({'error': 'Invalid signature'}, status=status.HTTP_401_UNAUTHORIZED)
            
            print("✅ Signature verified successfully!")
        
        # Parse webhook data
        try:
            data = json.loads(request.body.decode('utf-8'))
            print(f"\n📦 Webhook Data:")
            print(json.dumps(data, indent=2))
        except (json.JSONDecodeError, UnicodeDecodeError):
            data = request.data
            print(f"\n📦 Webhook Data: {data}")
        
        reference = data.get('reference')
        status_payment = data.get('status')
        transaction_id = data.get('transaction_id')
        
        # Log webhook
        webhook_log = WebhookLog.objects.create(
            reference=reference or 'unknown',
            payload=data
        )
        print(f"\n📝 Webhook logged: ID={webhook_log.id}")
        
        if reference:
            try:
                payment = Payment.objects.get(reference=reference)
                print(f"\n✅ Found payment: ID={payment.id}, Order={payment.order.id}")
                
                if status_payment == 'completed':
                    payment.status = 'completed'
                    payment.transaction_id = transaction_id
                    payment.payment_details = data
                    payment.save()
                    
                    # Update order status
                    order = payment.order
                    order.status = 'confirmed'
                    order.save()
                    
                    print(f"\n✅✅✅ SUCCESS!")
                    print(f"   Payment completed for Order #{order.id}")
                    print(f"   Order status updated to: confirmed")
                    
                elif status_payment == 'failed':
                    payment.status = 'failed'
                    payment.payment_details = data
                    payment.save()
                    print(f"\n❌ Payment failed for Order #{payment.order.id}")
                    
                elif status_payment == 'pending':
                    payment.status = 'processing'
                    payment.payment_details = data
                    payment.save()
                    print(f"\n⏳ Payment processing for Order #{payment.order.id}")
                    
            except Payment.DoesNotExist:
                print(f"\n❌ Payment not found for reference: {reference}")
                webhook_log.reference = reference + '_not_found'
                webhook_log.save()
        else:
            print("\n⚠️ No reference found in webhook data")
        
        print("\n" + "="*60)
        print("✅ Webhook processed successfully")
        print("="*60 + "\n")
        
        return Response({'status': 'ok', 'message': 'Webhook received'}, status=status.HTTP_200_OK)
    
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
        
        # Call PayChangu to verify
        headers = {
            'Authorization': f'Bearer {settings.PAYCHANGU_SECRET_KEY}',
            'Content-Type': 'application/json'
        }
        
        try:
            response = requests.get(
                f"{settings.PAYCHANGU_BASE_URL}/payment/verify/{reference}",
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                response_data = response.json()
                
                if response_data.get('status') == 'completed':
                    payment.status = 'completed'
                    payment.transaction_id = response_data.get('transaction_id')
                    payment.payment_details = response_data
                    payment.save()
                    
                    # Update order status
                    order = payment.order
                    order.status = 'confirmed'
                    order.save()
                    
                    result = {
                        'status': 'completed',
                        'message': 'Payment verified successfully',
                        'reference': reference,
                        'amount': str(payment.amount)
                    }
                elif response_data.get('status') == 'failed':
                    payment.status = 'failed'
                    payment.payment_details = response_data
                    payment.save()
                    result = {
                        'status': 'failed',
                        'message': 'Payment failed',
                        'reference': reference
                    }
                else:
                    result = {
                        'status': payment.status,
                        'message': 'Payment pending verification',
                        'reference': reference
                    }
                
                return Response(result, status=status.HTTP_200_OK)
            else:
                return Response({
                    'status': payment.status,
                    'message': 'Unable to verify payment status',
                    'reference': reference
                }, status=status.HTTP_200_OK)
                
        except requests.RequestException as e:
            return Response({
                'status': payment.status,
                'message': 'Verification service unavailable',
                'details': str(e),
                'reference': reference
            }, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['get'])
    def status(self, request, pk=None):
        """Get payment status for an order"""
        payment = self.get_object(pk)
        if not payment:
            return Response({'error': 'Payment not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Check if user has permission
        if payment.order.customer != request.user and not request.user.is_staff:
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
        
        serializer = PaymentStatusSerializer(payment)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def my_payments(self, request):
        """Get all payments for the authenticated user"""
        payments = Payment.objects.filter(order__customer=request.user).order_by('-created_at')
        serializer = PaymentSerializer(payments, many=True)
        return Response(serializer.data)
    
    def list(self, request):
        """List all payments (admin only)"""
        if not request.user.is_staff:
            payments = Payment.objects.filter(order__customer=request.user)
        else:
            payments = Payment.objects.all()
        
        payments = payments.order_by('-created_at')
        serializer = PaymentSerializer(payments, many=True)
        return Response(serializer.data)
    
    def retrieve(self, request, pk=None):
        """Get a specific payment"""
        payment = self.get_object(pk)
        if not payment:
            return Response({'error': 'Payment not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Check permission
        if payment.order.customer != request.user and not request.user.is_staff:
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
        
        serializer = PaymentSerializer(payment)
        return Response(serializer.data)