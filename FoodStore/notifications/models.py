from django.db import models
from django.conf import settings
from django.utils import timezone

class Notification(models.Model):
    """
    Notification model for user alerts and updates
    """
    class Type(models.TextChoices):
        ORDER = 'order', 'Order Update'
        PAYMENT = 'payment', 'Payment Status'
        PROMOTION = 'promotion', 'Promotion'
        SYSTEM = 'system', 'System Alert'
        REMINDER = 'reminder', 'Reminder'
    
    class Priority(models.TextChoices):
        LOW = 'low', 'Low'
        MEDIUM = 'medium', 'Medium'
        HIGH = 'high', 'High'
        URGENT = 'urgent', 'Urgent'
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='notifications'
    )
    type = models.CharField(max_length=20, choices=Type.choices, default=Type.SYSTEM)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    title = models.CharField(max_length=255)
    message = models.TextField()
    data = models.JSONField(default=dict, help_text="Additional data like order_id, restaurant_id, etc.")
    
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['user', 'is_read']),
            models.Index(fields=['type', 'created_at']),
        ]
    
    def mark_as_read(self):
        """Mark notification as read"""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])
    
    def __str__(self):
        return f"{self.user.username} - {self.title[:50]}"


class NotificationPreference(models.Model):
    """
    User preferences for notifications
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='notification_preferences'
    )
    
    # Channel preferences
    email_enabled = models.BooleanField(default=True)
    sms_enabled = models.BooleanField(default=False)
    push_enabled = models.BooleanField(default=True)
    in_app_enabled = models.BooleanField(default=True)
    
    # Type preferences
    order_updates = models.BooleanField(default=True)
    payment_alerts = models.BooleanField(default=True)
    promotions = models.BooleanField(default=False)
    system_alerts = models.BooleanField(default=True)
    
    # Digest settings
    email_digest = models.BooleanField(default=False)  # Send daily/weekly digest instead of real-time
    digest_frequency = models.CharField(
        max_length=10, 
        choices=[('daily', 'Daily'), ('weekly', 'Weekly')], 
        blank=True, 
        null=True
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Preferences for {self.user.username}"


class EmailLog(models.Model):
    """
    Log of all sent emails for tracking and debugging
    """
    class Status(models.TextChoices):
        SENT = 'sent', 'Sent'
        FAILED = 'failed', 'Failed'
        PENDING = 'pending', 'Pending'
    
    recipient = models.EmailField()
    subject = models.CharField(max_length=255)
    body = models.TextField()
    notification_type = models.CharField(max_length=50)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    error_message = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']


class SMSLog(models.Model):
    """
    Log of all sent SMS messages
    """
    class Status(models.TextChoices):
        SENT = 'sent', 'Sent'
        FAILED = 'failed', 'Failed'
        PENDING = 'pending', 'Pending'
    
    phone_number = models.CharField(max_length=20)
    message = models.TextField()
    notification_type = models.CharField(max_length=50)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    provider_response = models.JSONField(default=dict)
    error_message = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']