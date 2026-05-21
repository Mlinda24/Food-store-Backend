# drivers/models.py
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
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
        ('break', 'On Break'),
    ]
    
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='driver_profile'
    )
    
    # Personal Information
    phone_number = models.CharField(max_length=20)
    alternative_phone = models.CharField(max_length=20, blank=True)
    
    # Vehicle Information
    vehicle_type = models.CharField(max_length=20, choices=VEHICLE_CHOICES, default='motorcycle')
    vehicle_registration = models.CharField(max_length=50)
    vehicle_model = models.CharField(max_length=100, blank=True)
    vehicle_color = models.CharField(max_length=50, blank=True)
    
    # License Information
    license_number = models.CharField(max_length=50)
    license_expiry_date = models.DateField()
    
    # Verification
    is_verified = models.BooleanField(default=False)
    verification_documents = models.JSONField(default=dict, blank=True)
    verification_notes = models.TextField(blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_drivers'
    )
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='offline')
    is_available = models.BooleanField(default=False)
    
    # Location Tracking
    current_latitude = models.DecimalField(
        max_digits=9, 
        decimal_places=6, 
        null=True, 
        blank=True
    )
    current_longitude = models.DecimalField(
        max_digits=9, 
        decimal_places=6, 
        null=True, 
        blank=True
    )
    last_location_update = models.DateTimeField(null=True, blank=True)
    
    # Statistics
    total_deliveries = models.IntegerField(default=0)
    total_earnings = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    rating = models.DecimalField(
        max_digits=3, 
        decimal_places=2, 
        default=5.00,
        validators=[MinValueValidator(0), MaxValueValidator(5)]
    )
    total_ratings = models.IntegerField(default=0)
    
    # Documents
    profile_photo = models.ImageField(upload_to='driver_photos/', null=True, blank=True)
    id_card_photo = models.ImageField(upload_to='driver_ids/', null=True, blank=True)
    license_photo = models.ImageField(upload_to='driver_licenses/', null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Driver: {self.user.username} - {self.vehicle_registration}"
    
    @property
    def display_name(self):
        return f"{self.user.get_full_name() or self.user.username}"
    
    @property
    def current_location(self):
        if self.current_latitude and self.current_longitude:
            return {
                'lat': float(self.current_latitude),
                'lng': float(self.current_longitude)
            }
        return None
    
    class Meta:
        verbose_name = 'Driver Profile'
        verbose_name_plural = 'Driver Profiles'


class DeliveryAssignment(models.Model):
    """Assign orders to drivers and track delivery"""
    
    STATUS_CHOICES = [
        ('pending', 'Pending Assignment'),
        ('assigned', 'Assigned - Awaiting Acceptance'),
        ('accepted', 'Accepted - Heading to Restaurant'),
        ('arrived', 'Arrived at Restaurant'),
        ('picked_up', 'Picked Up - Heading to Customer'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
        ('failed', 'Failed'),
    ]
    
    order = models.OneToOneField(
        'orders.Order',
        on_delete=models.CASCADE,
        related_name='delivery_assignment'
    )
    
    driver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='delivery_assignments'
    )
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Location details
    pickup_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    pickup_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    dropoff_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    dropoff_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    
    # Distance and time
    distance_km = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    estimated_time_minutes = models.IntegerField(null=True, blank=True)
    actual_time_minutes = models.IntegerField(null=True, blank=True)
    
    # Payment
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tip_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_earning = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Timestamps
    assigned_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    arrived_at = models.DateTimeField(null=True, blank=True)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    
    # Rejection/Cancellation reason
    rejection_reason = models.TextField(blank=True, default='')
    
    # Customer rating for this delivery
    customer_rating = models.IntegerField(
        null=True, 
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    customer_feedback = models.TextField(blank=True, default='')
    
    def __str__(self):
        return f"Delivery #{self.id} - Order #{self.order.id} - {self.status}"
    
    def calculate_earning(self):
        """Calculate total earnings for this delivery"""
        return self.delivery_fee + self.tip_amount
    
    class Meta:
        verbose_name = 'Delivery Assignment'
        verbose_name_plural = 'Delivery Assignments'
        ordering = ['-assigned_at']


class DriverLocationHistory(models.Model):
    """Track driver location history for audit"""
    
    driver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='location_history'
    )
    
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    
    delivery_assignment = models.ForeignKey(
        DeliveryAssignment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='location_updates'
    )
    
    recorded_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.driver.username} - {self.recorded_at}"
    
    class Meta:
        verbose_name = 'Driver Location History'
        verbose_name_plural = 'Driver Location Histories'
        ordering = ['-recorded_at']


class DriverEarning(models.Model):
    """Track driver earnings per delivery"""
    
    EARNING_TYPE_CHOICES = [
        ('delivery_fee', 'Delivery Fee'),
        ('tip', 'Customer Tip'),
        ('bonus', 'Bonus'),
        ('adjustment', 'Adjustment'),
    ]
    
    driver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='earnings'
    )
    
    delivery_assignment = models.ForeignKey(
        DeliveryAssignment,
        on_delete=models.CASCADE,
        related_name='earnings'
    )
    
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    earning_type = models.CharField(max_length=20, choices=EARNING_TYPE_CHOICES)
    description = models.CharField(max_length=255, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.driver.username} - {self.amount} - {self.earning_type}"
    
    class Meta:
        verbose_name = 'Driver Earning'
        verbose_name_plural = 'Driver Earnings'