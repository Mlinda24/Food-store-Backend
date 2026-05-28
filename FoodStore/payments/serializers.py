from rest_framework import serializers
from .models import Payment, WebhookLog
from orders.models import Order


class PaymentSerializer(serializers.ModelSerializer):
    """Serializer for Payment model - Enhanced with wallet details"""
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
    order_customer_email = serializers.EmailField(
        source='order.customer.email',
        read_only=True
    )
    order_customer_phone = serializers.CharField(
        source='order.customer.phone',
        read_only=True
    )
    restaurant_name = serializers.CharField(
        source='order.restaurant.name',
        read_only=True
    )
    formatted_amount = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    method_display = serializers.CharField(source='get_method_display', read_only=True)
    
    # Wallet and distribution fields
    distributed_status = serializers.SerializerMethodField()
    platform_fee_formatted = serializers.SerializerMethodField()
    restaurant_amount_formatted = serializers.SerializerMethodField()
    driver_amount_formatted = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = [
            'id',
            'order',
            'order_total',
            'order_customer_name',
            'order_customer_email',
            'order_customer_phone',
            'restaurant_name',
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
            'updated_at',
            'paid_at',
            # Wallet distribution fields
            'distributed_to_wallets',
            'distributed_at',
            'distributed_status',
            'platform_fee',
            'platform_fee_formatted',
            'restaurant_amount',
            'restaurant_amount_formatted',
            'driver_amount',
            'driver_amount_formatted',
            # Refund fields
            'refunded_amount',
            'refund_reason',
            'refunded_at',
        ]
        read_only_fields = [
            'id',
            'transaction_id',
            'reference',
            'payment_details',
            'created_at',
            'updated_at',
            'paid_at',
            'distributed_at',
        ]

    def get_formatted_amount(self, obj):
        return f"MK{obj.amount:,.2f}"
    
    def get_distributed_status(self, obj):
        if obj.distributed_to_wallets:
            return "✓ Distributed"
        return "Pending"
    
    def get_platform_fee_formatted(self, obj):
        return f"MK{obj.platform_fee:,.2f}"
    
    def get_restaurant_amount_formatted(self, obj):
        return f"MK{obj.restaurant_amount:,.2f}"
    
    def get_driver_amount_formatted(self, obj):
        return f"MK{obj.driver_amount:,.2f}"


class PaymentDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for single payment view - Enhanced with wallet details"""
    order = serializers.SerializerMethodField()
    formatted_amount = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    method_display = serializers.CharField(source='get_method_display', read_only=True)
    
    # Enhanced fields
    order_customer_name = serializers.CharField(source='order.customer.username', read_only=True)
    order_customer_email = serializers.EmailField(source='order.customer.email', read_only=True)
    order_customer_phone = serializers.CharField(source='order.customer.phone', read_only=True)
    restaurant_name = serializers.CharField(source='order.restaurant.name', read_only=True)
    order_items_count = serializers.IntegerField(source='order.items.count', read_only=True)
    
    # Wallet distribution
    distributed_status = serializers.SerializerMethodField()
    platform_fee_formatted = serializers.SerializerMethodField()
    restaurant_amount_formatted = serializers.SerializerMethodField()
    driver_amount_formatted = serializers.SerializerMethodField()
    
    # Time fields
    time_to_distribute = serializers.SerializerMethodField()
    payment_completion_time = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = [
            'id',
            'order',
            'order_customer_name',
            'order_customer_email',
            'order_customer_phone',
            'restaurant_name',
            'order_items_count',
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
            'updated_at',
            'paid_at',
            # Wallet distribution
            'distributed_to_wallets',
            'distributed_at',
            'distributed_status',
            'platform_fee',
            'platform_fee_formatted',
            'restaurant_amount',
            'restaurant_amount_formatted',
            'driver_amount',
            'driver_amount_formatted',
            # Refund
            'refunded_amount',
            'refund_reason',
            'refunded_at',
            # Time analysis
            'time_to_distribute',
            'payment_completion_time',
        ]
        read_only_fields = '__all__'

    def get_order(self, obj):
        from orders.serializers import OrderSerializer
        order_data = OrderSerializer(obj.order).data
        # Add additional order info
        order_data['items_count'] = obj.order.items.count()
        order_data['customer_location'] = {
            'latitude': obj.order.customer_latitude if hasattr(obj.order, 'customer_latitude') else None,
            'longitude': obj.order.customer_longitude if hasattr(obj.order, 'customer_longitude') else None,
        }
        return order_data

    def get_formatted_amount(self, obj):
        return f"MK{obj.amount:,.2f}"
    
    def get_distributed_status(self, obj):
        if obj.distributed_to_wallets:
            return "✓ Distributed"
        return "⏳ Pending Distribution"
    
    def get_platform_fee_formatted(self, obj):
        return f"MK{obj.platform_fee:,.2f}"
    
    def get_restaurant_amount_formatted(self, obj):
        return f"MK{obj.restaurant_amount:,.2f}"
    
    def get_driver_amount_formatted(self, obj):
        return f"MK{obj.driver_amount:,.2f}"
    
    def get_time_to_distribute(self, obj):
        if obj.distributed_at and obj.paid_at:
            delta = obj.distributed_at - obj.paid_at
            minutes = int(delta.total_seconds() / 60)
            if minutes < 60:
                return f"{minutes} minutes"
            hours = minutes / 60
            return f"{hours:.1f} hours"
        return "Not distributed"
    
    def get_payment_completion_time(self, obj):
        if obj.paid_at and obj.created_at:
            delta = obj.paid_at - obj.created_at
            minutes = int(delta.total_seconds() / 60)
            if minutes < 60:
                return f"{minutes} minutes"
            hours = minutes / 60
            return f"{hours:.1f} hours"
        return "Not completed"


class InitiatePaymentSerializer(serializers.Serializer):
    """Serializer for initiating a payment - Updated to support paychangu"""
    order_id = serializers.IntegerField(
        required=True,
        help_text="ID of the order to pay for"
    )
    method = serializers.ChoiceField(
        choices=['mpamba', 'airtel_money', 'cash_on_delivery', 'paychangu'],
        required=True,
        help_text="Payment method: mpamba, airtel_money, cash_on_delivery, or paychangu"
    )
    phone_number = serializers.CharField(
        max_length=20,
        required=False,
        allow_blank=True,
        allow_null=True,
        help_text="Phone number for mobile money payment (required for mpamba/airtel_money)"
    )

    def validate_order_id(self, value):
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
        method = self.initial_data.get('method')
        
        # Phone number is only required for mpamba and airtel_money
        if method in ['mpamba', 'airtel_money']:
            if not value or value.strip() == '':
                raise serializers.ValidationError("Phone number is required for mobile money payment")
            if not value.isdigit():
                raise serializers.ValidationError("Phone number must contain only digits")
            if len(value) not in (9, 10):
                raise serializers.ValidationError("Phone number must be 9 or 10 digits")
        
        return value


class VerifyPaymentSerializer(serializers.Serializer):
    """Serializer for verifying a payment"""
    reference = serializers.CharField(
        required=True,
        max_length=100,
        help_text="Payment reference to verify"
    )

    def validate_reference(self, value):
        try:
            payment = Payment.objects.get(reference=value)
            request = self.context.get('request')
            if request and request.user != payment.order.customer and not request.user.is_staff:
                raise serializers.ValidationError("You can only verify your own payments")
        except Payment.DoesNotExist:
            raise serializers.ValidationError(f"Payment with reference {value} does not exist")
        return value


class PaymentStatusSerializer(serializers.Serializer):
    """Serializer for payment status response - Enhanced with wallet info"""
    reference = serializers.CharField()
    status = serializers.CharField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    message = serializers.CharField(required=False)

    def to_representation(self, instance):
        return {
            'reference': instance.reference,
            'status': instance.status,
            'status_display': instance.get_status_display(),
            'amount': str(instance.amount),
            'formatted_amount': f"MK{instance.amount:,.2f}",
            'method': instance.method,
            'method_display': instance.get_method_display(),
            'message': f"Payment is {instance.status}",
            # Add wallet info if payment is completed
            'wallet_info': {
                'distributed': instance.distributed_to_wallets,
                'restaurant_amount': str(instance.restaurant_amount) if instance.restaurant_amount else "0",
                'platform_fee': str(instance.platform_fee) if instance.platform_fee else "0",
            } if instance.status == 'completed' else None
        }


class WebhookLogSerializer(serializers.ModelSerializer):
    """Serializer for WebhookLog model - Enhanced with processing status"""
    formatted_received_at = serializers.SerializerMethodField()
    event_type_display = serializers.SerializerMethodField()
    payload_summary = serializers.SerializerMethodField()

    class Meta:
        model = WebhookLog
        fields = [
            'id', 
            'reference', 
            'event_type',
            'event_type_display',
            'payload', 
            'payload_summary',
            'processed', 
            'received_at', 
            'formatted_received_at'
        ]
        read_only_fields = '__all__'

    def get_formatted_received_at(self, obj):
        return obj.received_at.strftime("%Y-%m-%d %H:%M:%S")
    
    def get_event_type_display(self, obj):
        if obj.event_type:
            return obj.event_type
        return "Unknown"
    
    def get_payload_summary(self, obj):
        """Return a summary of the payload for quick viewing"""
        if isinstance(obj.payload, dict):
            summary = {}
            if 'status' in obj.payload:
                summary['status'] = obj.payload['status']
            if 'data' in obj.payload and isinstance(obj.payload['data'], dict):
                if 'reference' in obj.payload['data']:
                    summary['reference'] = obj.payload['data']['reference']
                if 'amount' in obj.payload['data']:
                    summary['amount'] = obj.payload['data']['amount']
            return summary
        return None


class PaymentSummarySerializer(serializers.Serializer):
    """Serializer for payment summary/statistics - Enhanced with wallet metrics"""
    total_payments = serializers.IntegerField()
    total_amount = serializers.DecimalField(max_digits=15, decimal_places=2)
    completed_payments = serializers.IntegerField()
    pending_payments = serializers.IntegerField()
    failed_payments = serializers.IntegerField()
    payments_by_method = serializers.DictField()
    
    # Enhanced wallet metrics
    total_platform_fees = serializers.DecimalField(max_digits=15, decimal_places=2)
    total_restaurant_payouts = serializers.DecimalField(max_digits=15, decimal_places=2)
    total_driver_payouts = serializers.DecimalField(max_digits=15, decimal_places=2)
    average_platform_fee_percentage = serializers.DecimalField(max_digits=5, decimal_places=2)
    wallet_distribution_rate = serializers.DecimalField(max_digits=5, decimal_places=2)

    def to_representation(self, instance):
        return {
            'total_payments': instance['total_payments'],
            'total_amount': str(instance['total_amount']),
            'formatted_total_amount': f"MK{instance['total_amount']:,.2f}",
            'completed_payments': instance['completed_payments'],
            'pending_payments': instance['pending_payments'],
            'failed_payments': instance['failed_payments'],
            'payments_by_method': instance['payments_by_method'],
            # Enhanced wallet metrics
            'total_platform_fees': str(instance['total_platform_fees']),
            'formatted_total_platform_fees': f"MK{instance['total_platform_fees']:,.2f}",
            'total_restaurant_payouts': str(instance['total_restaurant_payouts']),
            'formatted_total_restaurant_payouts': f"MK{instance['total_restaurant_payouts']:,.2f}",
            'total_driver_payouts': str(instance['total_driver_payouts']),
            'formatted_total_driver_payouts': f"MK{instance['total_driver_payouts']:,.2f}",
            'average_platform_fee_percentage': str(instance['average_platform_fee_percentage']),
            'wallet_distribution_rate': str(instance['wallet_distribution_rate']),
        }


class WalletTransactionSerializer(serializers.Serializer):
    """Serializer for wallet transactions"""
    transaction_id = serializers.CharField()
    order_id = serializers.IntegerField()
    restaurant_name = serializers.CharField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    formatted_amount = serializers.SerializerMethodField()
    transaction_type = serializers.ChoiceField(choices=['credit', 'debit'])
    status = serializers.CharField()
    description = serializers.CharField()
    created_at = serializers.DateTimeField()
    
    def get_formatted_amount(self, obj):
        return f"MK{obj['amount']:,.2f}"


class RestaurantWalletSerializer(serializers.Serializer):
    """Serializer for restaurant wallet details"""
    restaurant_id = serializers.IntegerField()
    restaurant_name = serializers.CharField()
    balance = serializers.DecimalField(max_digits=12, decimal_places=2)
    formatted_balance = serializers.SerializerMethodField()
    total_earned = serializers.DecimalField(max_digits=12, decimal_places=2)
    formatted_total_earned = serializers.SerializerMethodField()
    total_withdrawn = serializers.DecimalField(max_digits=12, decimal_places=2)
    formatted_total_withdrawn = serializers.SerializerMethodField()
    pending_withdrawals = serializers.IntegerField()
    recent_transactions = WalletTransactionSerializer(many=True)
    
    def get_formatted_balance(self, obj):
        return f"MK{obj['balance']:,.2f}"
    
    def get_formatted_total_earned(self, obj):
        return f"MK{obj['total_earned']:,.2f}"
    
    def get_formatted_total_withdrawn(self, obj):
        return f"MK{obj['total_withdrawn']:,.2f}"