from django.db import models
from django.conf import settings
from orders.models import Order

class Payment(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]
    
    METHOD_CHOICES = [
        ('mpamba', 'TNM Mpamba'),
        ('airtel_money', 'Airtel Money'),
        ('paychangu', 'PayChangu'),
    ]
    
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='payment')
    transaction_id = models.CharField(max_length=255, blank=True, null=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default='paychangu')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    reference = models.CharField(max_length=100, unique=True)
    phone_number = models.CharField(max_length=20, blank=True)
    payment_details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Payment breakdown fields
    subtotal_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=2000.0)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    platform_fee_percent = models.DecimalField(max_digits=5, decimal_places=2, default=10.00)

    # Wallet distribution fields
    distributed_to_wallets = models.BooleanField(
        default=False,
        help_text="Whether money has been distributed to wallets"
    )
    
    distributed_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When money was sent to wallets"
    )
    
    platform_fee = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0,
        help_text="Platform fee taken from this payment"
    )
    
    restaurant_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0,
        help_text="Amount going to restaurant"
    )
    
    driver_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0,
        help_text="Amount going to driver"
    )
    
    # Refund fields
    refunded_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0,
        help_text="Amount refunded"
    )
    
    refund_reason = models.TextField(
        blank=True, 
        default='',
        help_text="Reason for refund"
    )
    
    refunded_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When refund was processed"
    )
    
    # Timestamps
    paid_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When payment was completed"
    )
    
    def __str__(self):
        return f"Payment {self.reference} - {self.status}"
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Payment'
        verbose_name_plural = 'Payments'


class WebhookLog(models.Model):
    """Log all incoming webhooks for debugging"""
    reference = models.CharField(max_length=100, blank=True, null=True)
    event_type = models.CharField(max_length=100, blank=True, default='')
    payload = models.JSONField(default=dict)
    processed = models.BooleanField(default=False)
    received_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Webhook {self.reference or 'unknown'} at {self.received_at}"
    
    class Meta:
        ordering = ['-received_at']
        verbose_name = 'Webhook Log'
        verbose_name_plural = 'Webhook Logs'