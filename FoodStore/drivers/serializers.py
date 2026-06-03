from rest_framework import serializers
from .models import DriverProfile, DeliveryAssignment
from orders.models import Order

class DriverProfileSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source='user.username', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    display_name = serializers.SerializerMethodField()
    
    class Meta:
        model = DriverProfile
        fields = [
            'id', 'user', 'name', 'email', 'display_name', 'phone_number', 
            'alternative_phone', 'vehicle_type', 'vehicle_registration', 
            'vehicle_model', 'vehicle_color', 'license_number', 'license_expiry_date',
            'is_verified', 'status', 'is_available', 'current_latitude', 
            'current_longitude', 'total_deliveries', 'total_earnings', 
            'current_balance', 'rating', 'created_at', 'updated_at'
        ]
        read_only_fields = ['total_deliveries', 'total_earnings', 'current_balance', 'rating', 'created_at', 'updated_at']
    
    def get_display_name(self, obj):
        return obj.user.get_full_name() or obj.user.username


class DeliveryAssignmentSerializer(serializers.ModelSerializer):
    driver_name = serializers.CharField(source='driver.user.username', read_only=True)
    driver_phone = serializers.CharField(source='driver.phone_number', read_only=True)
    order_id = serializers.IntegerField(source='order.id', read_only=True)
    customer_name = serializers.CharField(source='order.customer.username', read_only=True)
    customer_phone = serializers.CharField(source='order.customer.phone', read_only=True)
    delivery_address = serializers.CharField(source='order.delivery_address', read_only=True)
    
    # Handle restaurant_name safely - if no ForeignKey, use restaurant_id
    restaurant_name = serializers.SerializerMethodField()
    restaurant_address = serializers.SerializerMethodField()
    total_amount = serializers.DecimalField(source='order.total_price', read_only=True, max_digits=10, decimal_places=2)
    
    class Meta:
        model = DeliveryAssignment
        fields = [
            'id', 'order_id', 'driver', 'driver_name', 'driver_phone', 'status', 
            'delivery_fee', 'customer_name', 'customer_phone', 'delivery_address',
            'restaurant_name', 'restaurant_address', 'total_amount', 
            'accepted_at', 'picked_up_at', 'delivered_at', 'created_at'
        ]
        read_only_fields = ['created_at']
    
    def get_restaurant_name(self, obj):
        try:
            if hasattr(obj.order, 'restaurant') and obj.order.restaurant:
                return obj.order.restaurant.name
        except:
            pass
        return f"Restaurant #{obj.order.restaurant_id}" if obj.order.restaurant_id else "Restaurant"
    
    def get_restaurant_address(self, obj):
        try:
            if hasattr(obj.order, 'restaurant') and obj.order.restaurant:
                return obj.order.restaurant.address
        except:
            pass
        return "Address not available"


class AvailableOrderSerializer(serializers.ModelSerializer):
    restaurant_name = serializers.SerializerMethodField()
    restaurant_address = serializers.SerializerMethodField()
    delivery_fee = serializers.DecimalField(max_digits=10, decimal_places=2, default=2000.00)
    formatted_total = serializers.SerializerMethodField()
    customer_name = serializers.SerializerMethodField()
    customer_phone = serializers.SerializerMethodField()
    
    class Meta:
        model = Order
        fields = [
            'id', 'restaurant', 'restaurant_name', 'restaurant_address', 
            'delivery_address', 'total_price', 'formatted_total', 'delivery_fee', 
            'created', 'special_instructions', 'customer_name', 'customer_phone'
        ]
    
    def get_restaurant_name(self, obj):
        try:
            if hasattr(obj, 'restaurant') and obj.restaurant:
                return obj.restaurant.name
        except:
            pass
        return f"Restaurant #{obj.restaurant_id}" if hasattr(obj, 'restaurant_id') and obj.restaurant_id else "Restaurant"
    
    def get_restaurant_address(self, obj):
        try:
            if hasattr(obj, 'restaurant') and obj.restaurant:
                return obj.restaurant.address
        except:
            pass
        return "Address not available"
    
    def get_formatted_total(self, obj):
        return f"MK{obj.total_price:,.2f}"
    
    def get_customer_name(self, obj):
        return obj.customer.username if obj.customer else "Customer"
    
    def get_customer_phone(self, obj):
        return obj.customer.phone if obj.customer and hasattr(obj.customer, 'phone') else ""