from django.db import models
from django.conf import settings
from decimal import Decimal

class DriverProfile(models.Model):
    """Driver profile extending the User model"""
    
    VEHICLE_CHOICES = [
        ('bicycle', 'Bicycle'),
        ('motorcycle', 'Motorcycle'),
        ('car', 'Car'),
        ('scooter', 'Scooter'),
    ]
    
    STATUS_CHOICES = [
        ('offline', 'Offline'),
        ('online', 'Online'),
        ('busy', 'Busy - On Delivery'),
    ]
    
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='driver_profile'
    )
    
    # Personal Information
    phone_number = models.CharField(max_length=20, blank=True, default='')
    alternative_phone = models.CharField(max_length=20, blank=True, default='')
    
    # Vehicle Information
    vehicle_type = models.CharField(max_length=20, choices=VEHICLE_CHOICES, default='motorcycle')
    vehicle_registration = models.CharField(max_length=50, blank=True, default='')
    vehicle_model = models.CharField(max_length=100, blank=True, default='')
    vehicle_color = models.CharField(max_length=50, blank=True, default='')
    
    # License Information
    license_number = models.CharField(max_length=50, blank=True, default='')
    license_expiry_date = models.DateField(null=True, blank=True)
    
    # Verification
    is_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='offline')
    is_available = models.BooleanField(default=False)
    
    # Location Tracking
    current_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    current_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    last_location_update = models.DateTimeField(null=True, blank=True)
    
    # Statistics
    total_deliveries = models.IntegerField(default=0)
    total_earnings = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    current_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=5.00)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Driver: {self.user.username}"
    
    class Meta:
        verbose_name = 'Driver Profile'
        verbose_name_plural = 'Driver Profiles'


class DeliveryAssignment(models.Model):
    """Assign orders to drivers and track delivery"""
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('picked_up', 'Picked Up'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]
    
    order = models.OneToOneField(
        'orders.Order',
        on_delete=models.CASCADE,
        related_name='delivery_assignment'
    )
    
    driver = models.ForeignKey(
        DriverProfile,
        on_delete=models.CASCADE,
        related_name='deliveries'
    )
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=2000.00)
    
    # Timestamps
    accepted_at = models.DateTimeField(null=True, blank=True)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Delivery #{self.id} - Order #{self.order.id}"
    
    class Meta:
        ordering = ['-created_at']