# drivers/serializers.py - COMPLETE FIXED VERSION
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import DriverProfile, DeliveryAssignment, DriverLocationHistory
from orders.models import Order

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'phone', 'role']


class DriverProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    user_id = serializers.IntegerField(write_only=True, required=False)
    display_name = serializers.SerializerMethodField()
    current_location = serializers.SerializerMethodField()
    
    class Meta:
        model = DriverProfile
        fields = [
            'id', 'user', 'user_id', 'display_name', 'phone_number', 'alternative_phone',
            'vehicle_type', 'vehicle_registration', 'vehicle_model', 'vehicle_color',
            'license_number', 'license_expiry_date',
            'is_verified', 'verification_documents', 'verification_notes',
            'status', 'is_available',
            'current_latitude', 'current_longitude', 'current_location',
            'total_deliveries', 'total_earnings', 'rating',
            'profile_photo', 'id_card_photo', 'license_photo',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['total_deliveries', 'total_earnings', 'rating', 'created_at', 'updated_at']
    
    def get_display_name(self, obj):
        return obj.user.get_full_name() or obj.user.username
    
    def get_current_location(self, obj):
        if obj.current_latitude and obj.current_longitude:
            return {
                'lat': float(obj.current_latitude),
                'lng': float(obj.current_longitude)
            }
        return None


class DriverRegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=6)
    phone_number = serializers.CharField(max_length=20)
    vehicle_type = serializers.ChoiceField(choices=DriverProfile.VEHICLE_CHOICES)
    vehicle_registration = serializers.CharField(max_length=50)
    license_number = serializers.CharField(max_length=50)
    license_expiry_date = serializers.DateField()


class DriverLocationSerializer(serializers.Serializer):
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6)


class DriverStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=DriverProfile.STATUS_CHOICES)
    is_available = serializers.BooleanField(required=False)


class DeliveryAssignmentSerializer(serializers.ModelSerializer):
    driver_name = serializers.SerializerMethodField()
    driver_phone = serializers.SerializerMethodField()
    order_items = serializers.SerializerMethodField()
    customer_name = serializers.SerializerMethodField()
    customer_phone = serializers.SerializerMethodField()
    delivery_address = serializers.CharField(source='order.delivery_address', read_only=True)
    restaurant_name = serializers.CharField(source='order.restaurant_name', read_only=True)
    total_price = serializers.DecimalField(source='order.total_price', read_only=True, max_digits=10, decimal_places=2)
    
    class Meta:
        model = DeliveryAssignment
        fields = [
            'id', 'order', 'driver', 'driver_name', 'driver_phone', 'status',
            'pickup_latitude', 'pickup_longitude', 'dropoff_latitude', 'dropoff_longitude',
            'distance_km', 'estimated_time_minutes', 'actual_time_minutes',
            'delivery_fee', 'tip_amount', 'total_earning',
            'assigned_at', 'accepted_at', 'arrived_at', 'picked_up_at', 'delivered_at',
            'order_items', 'customer_name', 'customer_phone', 'delivery_address',
            'restaurant_name', 'total_price', 'rejection_reason', 'customer_rating', 'customer_feedback'
        ]
        read_only_fields = ['assigned_at']
    
    def get_driver_name(self, obj):
        return obj.driver.get_full_name() or obj.driver.username
    
    def get_driver_phone(self, obj):
        return getattr(obj.driver, 'phone', '')
    
    def get_customer_name(self, obj):
        return obj.order.customer.get_full_name() or obj.order.customer.username
    
    def get_customer_phone(self, obj):
        return getattr(obj.order.customer, 'phone', '')
    
    def get_order_items(self, obj):
        from orders.serializers import OrderItemSerializer
        items = obj.order.items.all()
        return OrderItemSerializer(items, many=True).data


class AvailableOrderSerializer(serializers.ModelSerializer):
    restaurant_name = serializers.CharField()
    restaurant_address = serializers.SerializerMethodField()
    distance_from_restaurant = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    estimated_earning = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    
    class Meta:
        model = Order
        fields = [
            'id', 'restaurant_id', 'restaurant_name', 'restaurant_address',
            'total_price', 'delivery_address', 'created',
            'distance_from_restaurant', 'estimated_earning'
        ]
    
    def get_restaurant_address(self, obj):
        try:
            from restaurant.models import Restaurant
            restaurant = Restaurant.objects.get(id=obj.restaurant_id)
            return restaurant.address
        except:
            return "Address not available"


class DriverEarningSummarySerializer(serializers.Serializer):
    today_earnings = serializers.DecimalField(max_digits=10, decimal_places=2)
    week_earnings = serializers.DecimalField(max_digits=10, decimal_places=2)
    month_earnings = serializers.DecimalField(max_digits=10, decimal_places=2)
    total_earnings = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_deliveries = serializers.IntegerField()
    today_deliveries = serializers.IntegerField()
    average_rating = serializers.DecimalField(max_digits=3, decimal_places=2)