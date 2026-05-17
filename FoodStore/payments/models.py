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
    ]
    
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='payment')
    transaction_id = models.CharField(max_length=255, blank=True, null=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default='mpamba')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    reference = models.CharField(max_length=100, unique=True)
    phone_number = models.CharField(max_length=20, blank=True)
    payment_details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Payment {self.reference} - {self.status}"
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Payment'
        verbose_name_plural = 'Payments'


class WebhookLog(models.Model):
    """Log all incoming webhooks for debugging"""
    reference = models.CharField(max_length=100, blank=True, null=True)
    payload = models.JSONField(default=dict)
    received_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Webhook {self.reference or 'unknown'} at {self.received_at}"
    
    class Meta:
        ordering = ['-received_at']
        verbose_name = 'Webhook Log'
        verbose_name_plural = 'Webhook Logs'