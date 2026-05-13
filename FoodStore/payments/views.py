import requests
import uuid
from django.conf import settings
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from orders.models import Order
from .models import Payment
from .serializers import PaymentSerializer

class PaymentViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['post'])
    def initiate(self, request):
        order_id = request.data.get('order_id')
        method = request.data.get('method', 'mpesa')
        phone = request.data.get('phone_number', '')
        
        try:
            order = Order.objects.get(id=order_id, customer=request.user)
        except Order.DoesNotExist:
            return Response({'error': 'Order not found'}, status=404)
        
        reference = f"FOOD-{order.id}-{uuid.uuid4().hex[:6].upper()}"
        
        payment = Payment.objects.create(
            order=order,
            amount=order.total_price,
            method=method,
            reference=reference,
            phone_number=phone,
            status='pending'
        )
        
        # Mock response for testing (replace with actual PayChangu call)
        return Response({
            'payment_id': payment.id,
            'reference': reference,
            'checkout_url': f'/payment/checkout/{reference}/',
            'amount': str(order.total_price),
            'status': 'pending'
        })
    
    @action(detail=False, methods=['post'])
    def webhook(self, request):
        """Webhook endpoint for payment callbacks"""
        print("Webhook received:", request.data)
        # Process webhook here
        return Response({'status': 'ok'})