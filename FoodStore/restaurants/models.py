from django.db import models
from django.conf import settings
import uuid  # Add this import

class Restaurant(models.Model):
    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='restaurant'
    )

    name = models.CharField(max_length=255)

    description = models.TextField(
        blank=True,
        default=''
    )

    address = models.TextField()

    phone = models.CharField(
        max_length=20,
        blank=True,
        default=''
    )

    image = models.ImageField(
        upload_to='restaurants/',
        blank=True,
        null=True
    )

    is_open = models.BooleanField(default=True)

    rating = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=0
    )

    delivery_time = models.IntegerField(
        default=30,
        help_text="Average delivery time in minutes"
    )

    delivery_fee = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=2.99
    )

    min_order_amount = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=10.00
    )

    # Location fields
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True
    )

    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True
    )

    # Delivery settings
    base_delivery_fee = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=1000.00,
        help_text="Base delivery fee"
    )

    fee_per_km = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=500.00,
        help_text="Fee per kilometer"
    )

    free_delivery_radius = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=0.00,
        help_text="Radius in km where delivery is free"
    )

    max_delivery_radius = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=10.00,
        help_text="Maximum delivery radius in km"
    )

    # Tiered delivery fees
    tier_1_fee = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=1000.00,
        help_text="Fee for tier 1 (0-2km)"
    )

    tier_2_fee = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=2000.00,
        help_text="Fee for tier 2 (2-5km)"
    )

    tier_3_fee = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=3000.00,
        help_text="Fee for tier 3 (5-8km)"
    )

    tier_4_fee = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=4000.00,
        help_text="Fee for tier 4 (8-12km)"
    )

    tier_5_fee = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=5000.00,
        help_text="Fee for tier 5 (12-15km)"
    )

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['-created']


class RestaurantWallet(models.Model):
    restaurant = models.OneToOneField(
        Restaurant,
        on_delete=models.CASCADE,
        related_name='wallet'
    )
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_earned = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_withdrawn = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.restaurant.name} Wallet"


class WalletTransaction(models.Model):
    TRANSACTION_TYPES = (
        ('credit', 'Credit'),
        ('debit', 'Debit'),
    )
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('successful', 'Successful'),
        ('failed', 'Failed'),
    )
    
    wallet = models.ForeignKey(
        RestaurantWallet,
        on_delete=models.CASCADE,
        related_name='transactions'
    )
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reference = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    description = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.wallet.restaurant.name} - {self.amount}"


class Category(models.Model):
    restaurant = models.ForeignKey(
        Restaurant,
        on_delete=models.CASCADE,
        related_name='categories'
    )
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

    class Meta:
        unique_together = ['restaurant', 'name']


class MenuItem(models.Model):
    restaurant = models.ForeignKey(
        Restaurant,
        on_delete=models.CASCADE,
        related_name='menu_items'
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='items'
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    price = models.DecimalField(max_digits=10, decimal_places=2)
    image = models.ImageField(upload_to='menu/', blank=True, null=True)
    is_available = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']