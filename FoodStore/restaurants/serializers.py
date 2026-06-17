from rest_framework import serializers
from .models import Restaurant, Category, MenuItem

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'restaurant']
        read_only_fields = ['id', 'restaurant']


class MenuItemSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True, allow_null=True)
    restaurant_name = serializers.CharField(source='restaurant.name', read_only=True)
    
    class Meta:
        model = MenuItem
        fields = ['id', 'restaurant', 'restaurant_name', 'name', 'description', 'price', 
                  'image', 'is_available', 'category', 'category_name', 'created']
        read_only_fields = ['id', 'restaurant', 'restaurant_name', 'category_name', 'created']
    
    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("Price must be greater than 0")
        return value
    
    def validate_name(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Name is required")
        return value.strip()


class MenuItemPublicSerializer(serializers.ModelSerializer):
    restaurant_name = serializers.CharField(source='restaurant.name', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True, allow_null=True)
    
    class Meta:
        model = MenuItem
        fields = ['id', 'name', 'description', 'price', 'image', 'is_available', 
                  'restaurant', 'restaurant_name', 'category', 'category_name']


class RestaurantSerializer(serializers.ModelSerializer):
    menu_items = MenuItemSerializer(many=True, read_only=True)
    categories = CategorySerializer(many=True, read_only=True)
    owner_name = serializers.CharField(source='owner.username', read_only=True)
    
    class Meta:
        model = Restaurant
        fields = ['id', 'owner', 'owner_name', 'name', 'description', 'address', 'phone', 
                  'image', 'is_open', 'rating', 'delivery_time', 'delivery_fee', 
                  'min_order_amount', 'categories', 'menu_items', 'created']
        read_only_fields = ['id', 'owner', 'owner_name', 'created']


class RestaurantListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Restaurant
        fields = ['id', 'name', 'address', 'phone', 'image', 'is_open', 'rating', 'delivery_time']