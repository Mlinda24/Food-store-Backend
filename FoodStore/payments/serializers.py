from rest_framework import serializers
from .models import Payment, WebhookLog
from orders.models import Order


class PaymentSerializer(serializers.ModelSerializer):
    """Serializer for Payment model"""
    order_total = serializers.DecimalField(
        source='order.total_price', 
        read_only=True, 
        max_digits=10, 
        decimal_places=2
    )
    order_customer_name = serializers.CharField(
        source='order.customer.username', 
        read_only=True
    )
    formatted_amount = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    method_display = serializers.CharField(source='get_method_display', read_only=True)
    
    class Meta:
        model = Payment
        fields = [
            'id', 
            'order', 
            'order_total',
            'order_customer_name',
            'transaction_id', 
            'amount',
            'formatted_amount',
            'method',
            'method_display',
            'status',
            'status_display',
            'reference', 
            'phone_number', 
            'payment_details', 
            'created_at',
            'updated_at'
        ]
        read_only_fields = [
            'id', 
            'transaction_id', 
            'reference', 
            'payment_details', 
            'created_at',
            'updated_at'
        ]
    
    def get_formatted_amount(self, obj):
        """Format amount with currency"""
        return f"MK{obj.amount:,.2f}"


class PaymentDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for single payment view"""
    order = serializers.SerializerMethodField()
    formatted_amount = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    method_display = serializers.CharField(source='get_method_display', read_only=True)
    
    class Meta:
        model = Payment
        fields = [
            'id', 
            'order',
            'transaction_id', 
            'amount',
            'formatted_amount',
            'method',
            'method_display',
            'status',
            'status_display',
            'reference', 
            'phone_number', 
            'payment_details', 
            'created_at',
            'updated_at'
        ]
        read_only_fields = '__all__'
    
    def get_order(self, obj):
        """Return order details"""
        from orders.serializers import OrderSerializer
        return OrderSerializer(obj.order).data
    
    def get_formatted_amount(self, obj):
        return f"MK{obj.amount:,.2f}"


class InitiatePaymentSerializer(serializers.Serializer):
    """Serializer for initiating a payment"""
    order_id = serializers.IntegerField(
        required=True,
        help_text="ID of the order to pay for"
    )
    method = serializers.ChoiceField(
        choices=['mpesa', 'airtel_money', 'card'],
        required=True,
        help_text="Payment method: mpesa, airtel_money, or card"
    )
    phone_number = serializers.CharField(
        max_length=20,
        required=False,
        allow_blank=True,
        help_text="Phone number for mobile money payments (e.g., 0999123456)"
    )
    
    def validate_order_id(self, value):
        """Validate that order exists and belongs to the user"""
        try:
            order = Order.objects.get(id=value)
            request = self.context.get('request')
            if request and request.user != order.customer:
                raise serializers.ValidationError("You can only pay for your own orders")
            if order.status == 'delivered':
                raise serializers.ValidationError("This order has already been delivered")
            if hasattr(order, 'payment') and order.payment.status == 'completed':
                raise serializers.ValidationError("This order has already been paid")
        except Order.DoesNotExist:
            raise serializers.ValidationError(f"Order with id {value} does not exist")
        return value
    
    def validate_phone_number(self, value):
        """Validate phone number format for mobile money"""
        method = self.initial_data.get('method')
        if method in ['mpesa', 'airtel_money'] and not value:
            raise serializers.ValidationError(
                f"Phone number is required for {method} payment"
            )
        if value and not value.isdigit():
            raise serializers.ValidationError("Phone number must contain only digits")
        return value


class VerifyPaymentSerializer(serializers.Serializer):
    """Serializer for verifying a payment"""
    reference = serializers.CharField(
        required=True,
        max_length=100,
        help_text="Payment reference to verify"
    )
    
    def validate_reference(self, value):
        """Validate that payment exists"""
        try:
            payment = Payment.objects.get(reference=value)
            request = self.context.get('request')
            if request and request.user != payment.order.customer and not request.user.is_staff:
                raise serializers.ValidationError("You can only verify your own payments")
        except Payment.DoesNotExist:
            raise serializers.ValidationError(f"Payment with reference {value} does not exist")
        return value


class PaymentStatusSerializer(serializers.Serializer):
    """Serializer for payment status response"""
    reference = serializers.CharField()
    status = serializers.CharField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    message = serializers.CharField(required=False)
    
    def to_representation(self, instance):
        """Custom representation for payment status"""
        return {
            'reference': instance.reference,
            'status': instance.status,
            'status_display': instance.get_status_display(),
            'amount': str(instance.amount),
            'formatted_amount': f"MK{instance.amount:,.2f}",
            'method': instance.method,
            'message': f"Payment is {instance.status}"
        }


class WebhookLogSerializer(serializers.ModelSerializer):
    """Serializer for WebhookLog model"""
    formatted_received_at = serializers.SerializerMethodField()
    
    class Meta:
        model = WebhookLog
        fields = ['id', 'reference', 'payload', 'received_at', 'formatted_received_at']
        read_only_fields = '__all__'
    
    def get_formatted_received_at(self, obj):
        return obj.received_at.strftime("%Y-%m-%d %H:%M:%S")


class PaymentSummarySerializer(serializers.Serializer):
    """Serializer for payment summary/statistics"""
    total_payments = serializers.IntegerField()
    total_amount = serializers.DecimalField(max_digits=15, decimal_places=2)
    completed_payments = serializers.IntegerField()
    pending_payments = serializers.IntegerField()
    failed_payments = serializers.IntegerField()
    payments_by_method = serializers.DictField()
    
    def to_representation(self, instance):
        return {
            'total_payments': instance['total_payments'],
            'total_amount': str(instance['total_amount']),
            'formatted_total_amount': f"MK{instance['total_amount']:,.2f}",
            'completed_payments': instance['completed_payments'],
            'pending_payments': instance['pending_payments'],
            'failed_payments': instance['failed_payments'],
            'payments_by_method': instance['payments_by_method']
        }