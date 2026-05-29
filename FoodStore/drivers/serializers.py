from rest_framework import serializers
from .models import DriverProfile, DeliveryAssignment
from orders.models import Order

class DriverProfileSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source='user.username', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    
    class Meta:
        model = DriverProfile
        fields = [
            'id', 'name', 'email', 'phone_number', 'vehicle_type',
            'vehicle_registration', 'status', 'is_available',
            'total_deliveries', 'total_earnings', 'current_balance', 'rating',
            'current_latitude', 'current_longitude'
        ]


class DeliveryAssignmentSerializer(serializers.ModelSerializer):
    driver_name = serializers.CharField(source='driver.user.username', read_only=True)
    order_id = serializers.IntegerField(source='order.id', read_only=True)
    customer_name = serializers.CharField(source='order.customer.username', read_only=True)
    customer_phone = serializers.CharField(source='order.customer.phone', read_only=True)
    delivery_address = serializers.CharField(source='order.delivery_address', read_only=True)
    restaurant_name = serializers.CharField(source='order.restaurant.name', read_only=True)
    total_amount = serializers.DecimalField(source='order.total_price', read_only=True, max_digits=10, decimal_places=2)
    
    class Meta:
        model = DeliveryAssignment
        fields = [
            'id', 'order_id', 'driver_name', 'status', 'delivery_fee',
            'customer_name', 'customer_phone', 'delivery_address',
            'restaurant_name', 'total_amount', 'accepted_at', 'picked_up_at',
            'delivered_at', 'created_at'
        ]


class AvailableOrderSerializer(serializers.ModelSerializer):
    restaurant_name = serializers.CharField(source='restaurant.name', read_only=True)
    restaurant_address = serializers.CharField(source='restaurant.address', read_only=True)
    delivery_fee = serializers.DecimalField(max_digits=10, decimal_places=2, default=2000.00)
    
    class Meta:
        model = Order
        fields = [
            'id', 'restaurant_name', 'restaurant_address', 'delivery_address',
            'total_price', 'delivery_fee', 'created'
        ]