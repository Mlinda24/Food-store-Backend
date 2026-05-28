from rest_framework import serializers
from cloudinary.utils import cloudinary_url
from .models import Restaurant, Category, MenuItem


def _build_image_url(image_field) -> str | None:
    """
    Converts a Django ImageField / CloudinaryField value to a full HTTPS URL.
    Handles three cases:
      1. Already a full https:// URL  → return as-is
      2. A Cloudinary public_id       → build via cloudinary_url()
      3. A local /media/ path         → build Cloudinary URL from the public_id
    """
    if not image_field:
        return None

    raw = str(image_field).strip()
    if not raw:
        return None

    # Case 1 — already a full URL (Cloudinary delivery URL or any https)
    if raw.startswith('http://') or raw.startswith('https://'):
        return raw

    # Case 2 & 3 — strip /media/ prefix if present, then strip extension
    if raw.startswith('/media/'):
        raw = raw[7:]
    elif raw.startswith('media/'):
        raw = raw[6:]

    # Strip file extension to get the Cloudinary public_id
    public_id = raw.rsplit('.', 1)[0] if '.' in raw else raw

    try:
        url, _ = cloudinary_url(public_id, secure=True)
        return url
    except Exception:
        # Fallback: construct URL manually
        import os
        from django.conf import settings
        cloud_name = (
            getattr(settings, 'CLOUDINARY_STORAGE', {}).get('CLOUD_NAME')
            or os.environ.get('CLOUDINARY_CLOUD_NAME', '')
        )
        if cloud_name:
            return f'https://res.cloudinary.com/{cloud_name}/image/upload/{public_id}'
        return None


# ─── Category ────────────────────────────────────────────────────────────────

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'restaurant']
        read_only_fields = ['id', 'restaurant']


# ─── Menu Item (owner — full fields) ─────────────────────────────────────────

class MenuItemSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(
        source='category.name', read_only=True, allow_null=True
    )
    restaurant_name = serializers.CharField(
        source='restaurant.name', read_only=True
    )
    image = serializers.SerializerMethodField()

    class Meta:
        model = MenuItem
        fields = [
            'id', 'restaurant', 'restaurant_name',
            'name', 'description', 'price',
            'image', 'is_available',
            'category', 'category_name', 'created',
        ]
        read_only_fields = ['id', 'restaurant', 'restaurant_name', 'category_name', 'created']

    def get_image(self, obj) -> str | None:
        return _build_image_url(obj.image)

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError('Price must be greater than 0')
        return value

    def validate_name(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError('Name is required')
        return value.strip()


# ─── Menu Item (public — customer-facing) ────────────────────────────────────

class MenuItemPublicSerializer(serializers.ModelSerializer):
    restaurant_name = serializers.CharField(
        source='restaurant.name', read_only=True
    )
    category_name = serializers.CharField(
        source='category.name', read_only=True, allow_null=True
    )
    image = serializers.SerializerMethodField()

    class Meta:
        model = MenuItem
        fields = [
            'id', 'name', 'description', 'price',
            'image', 'is_available',
            'restaurant', 'restaurant_name',
            'category', 'category_name',
        ]

    def get_image(self, obj) -> str | None:
        return _build_image_url(obj.image)


# ─── Restaurant ──────────────────────────────────────────────────────────────

class RestaurantSerializer(serializers.ModelSerializer):
    menu_items = MenuItemSerializer(many=True, read_only=True)
    categories = CategorySerializer(many=True, read_only=True)
    owner_name = serializers.CharField(source='owner.username', read_only=True)
    image = serializers.SerializerMethodField()

    class Meta:
        model = Restaurant
        fields = [
            'id', 'owner', 'owner_name',
            'name', 'description', 'address', 'phone',
            'image', 'is_open', 'rating',
            'delivery_time', 'delivery_fee', 'min_order_amount',
            'latitude', 'longitude',
            'categories', 'menu_items', 'created',
        ]
        read_only_fields = ['id', 'owner', 'owner_name', 'created']

    def get_image(self, obj) -> str | None:
        return _build_image_url(obj.image)


class RestaurantListSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = Restaurant
        fields = ['id', 'name', 'address', 'phone', 'image', 'is_open', 'rating', 'delivery_time']

    def get_image(self, obj) -> str | None:
        return _build_image_url(obj.image)