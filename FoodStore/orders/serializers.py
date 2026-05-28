from rest_framework import serializers
from .models import Cart, CartItem, Order, OrderItem


class CartItemSerializer(serializers.ModelSerializer):
    total = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = CartItem
        fields = [
            'id', 'cart', 'menu_item_id', 'menu_item_name', 'menu_item_price',
            'quantity', 'customization', 'special_instructions', 'total', 'added_at',
        ]
        read_only_fields = ['id', 'cart', 'added_at', 'total']


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    total_items = serializers.SerializerMethodField()
    total_price = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = [
            'id', 'user', 'restaurant_id', 'restaurant_name', 'items',
            'total_items', 'total_price', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']

    def get_total_items(self, obj):
        return obj.items.count()

    def get_total_price(self, obj):
        return sum(item.menu_item_price * item.quantity for item in obj.items.all())


class OrderItemSerializer(serializers.ModelSerializer):
    total = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = [
            'id', 'order', 'menu_item_id', 'menu_item_name', 'menu_item_price',
            'quantity', 'price', 'customization', 'special_instructions', 'total', 'display_name',
        ]
        read_only_fields = ['id', 'order']

    def get_display_name(self, obj):
        base = obj.menu_item_name
        if obj.customization:
            cust_str = ', '.join([f"{k}: {v}" for k, v in obj.customization.items()])
            return f"{base} ({cust_str})"
        return base


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    customer_name = serializers.SerializerMethodField()
    customer_phone = serializers.SerializerMethodField()
    # Expose payment_status so Flutter can check paid vs unpaid
    payment_status = serializers.CharField(read_only=True)
    paid_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = Order
        fields = [
            'id', 'customer', 'customer_name', 'customer_phone',
            'restaurant_id', 'restaurant_name',
            'status', 'payment_status', 'paid_at',
            'total_price', 'delivery_address',
            'note', 'items', 'created', 'updated_at',
        ]
        read_only_fields = [
            'id', 'customer', 'status', 'payment_status',
            'total_price', 'created', 'updated_at', 'paid_at',
        ]

    def get_customer_name(self, obj):
        if obj.customer:
            return obj.customer.username
        return 'Anonymous'

    def get_customer_phone(self, obj):
        if obj.customer and hasattr(obj.customer, 'phone'):
            return obj.customer.phone
        return ''