from django.core.mail import send_mail, EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.utils.html import strip_tags
from .models import EmailLog, SMSLog, Notification
import logging

logger = logging.getLogger(__name__)

class EmailService:
    """Handle email notifications"""
    
    @staticmethod
    def send_email(recipient, subject, template_name, context, notification_type='general'):
        """
        Send HTML email using templates
        """
        try:
            # Render HTML template
            html_content = render_to_string(f'notifications/emails/{template_name}.html', context)
            text_content = strip_tags(html_content)
            
            # Create email
            email = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[recipient]
            )
            email.attach_alternative(html_content, "text/html")
            
            # Send email
            email.send(fail_silently=False)
            
            # Log success
            EmailLog.objects.create(
                recipient=recipient,
                subject=subject,
                body=text_content,
                notification_type=notification_type,
                status='sent',
                sent_at=timezone.now()
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email to {recipient}: {str(e)}")
            
            # Log failure
            EmailLog.objects.create(
                recipient=recipient,
                subject=subject,
                body=str(context),
                notification_type=notification_type,
                status='failed',
                error_message=str(e)
            )
            return False
    
    @staticmethod
    def send_order_confirmation(user, order_data):
        """Send order confirmation email"""
        context = {
            'user': user,
            'order': order_data,
            'site_url': settings.SITE_URL,
        }
        return EmailService.send_email(
            recipient=user.email,
            subject=f"Order Confirmation - #{order_data.get('id')}",
            template_name='order_confirmation',
            context=context,
            notification_type='order_confirmation'
        )
    
    @staticmethod
    def send_order_status_update(user, order_data, old_status, new_status):
        """Send order status update email"""
        context = {
            'user': user,
            'order': order_data,
            'old_status': old_status,
            'new_status': new_status,
            'site_url': settings.SITE_URL,
        }
        return EmailService.send_email(
            recipient=user.email,
            subject=f"Order Status Update - #{order_data.get('id')}",
            template_name='order_status_update',
            context=context,
            notification_type='order_status_update'
        )
    
    @staticmethod
    def send_payment_confirmation(user, payment_data):
        """Send payment confirmation email"""
        context = {
            'user': user,
            'payment': payment_data,
            'site_url': settings.SITE_URL,
        }
        return EmailService.send_email(
            recipient=user.email,
            subject=f"Payment Confirmation - {payment_data.get('transaction_id', '')}",
            template_name='payment_confirmation',
            context=context,
            notification_type='payment_confirmation'
        )


class SMSService:
    """Handle SMS notifications (using Africa's Talking or Twilio)"""
    
    @staticmethod
    def send_sms(phone_number, message, notification_type='general'):
        """
        Send SMS message
        Note: Configure your SMS provider (Twilio, Africa's Talking, etc.)
        """
        try:
            # Example using Twilio (you need to install twilio package)
            # from twilio.rest import Client
            # client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            # message = client.messages.create(
            #     body=message,
            #     from_=settings.TWILIO_PHONE_NUMBER,
            #     to=phone_number
            # )
            
            # For now, log the SMS (replace with actual provider)
            logger.info(f"SMS to {phone_number}: {message[:50]}...")
            
            # Log success
            SMSLog.objects.create(
                phone_number=phone_number,
                message=message,
                notification_type=notification_type,
                status='sent',
                sent_at=timezone.now()
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to send SMS to {phone_number}: {str(e)}")
            
            # Log failure
            SMSLog.objects.create(
                phone_number=phone_number,
                message=message,
                notification_type=notification_type,
                status='failed',
                error_message=str(e)
            )
            return False
    
    @staticmethod
    def send_order_status_sms(user, order_data, status):
        """Send order status SMS"""
        message = f"Your order #{order_data.get('id')} is now {status}. Track at {settings.SITE_URL}/orders/"
        
        if user.phone:
            return SMSService.send_sms(
                phone_number=user.phone,
                message=message,
                notification_type='order_status'
            )
        return False


class NotificationService:
    """Main notification service that orchestrates all channels"""
    
    @staticmethod
    def create_notification(user, notification_type, title, message, data=None, priority='medium'):
        """
        Create in-app notification
        """
        from .models import Notification
        
        notification = Notification.objects.create(
            user=user,
            type=notification_type,
            priority=priority,
            title=title,
            message=message,
            data=data or {}
        )
        
        return notification
    
    @staticmethod
    def send_notification(user, notification_type, title, message, data=None, send_email=True, send_sms=False, priority='medium'):
        """
        Send notification through multiple channels based on user preferences
        """
        # Get user preferences
        from .models import NotificationPreference
        try:
            preferences = user.notification_preferences
        except NotificationPreference.DoesNotExist:
            # Create default preferences if not exists
            preferences = NotificationPreference.objects.create(user=user)
        
        # Create in-app notification
        notification = NotificationService.create_notification(
            user=user,
            notification_type=notification_type,
            title=title,
            message=message,
            data=data,
            priority=priority
        )
        
        # Send email if enabled and requested
        if send_email and preferences.email_enabled:
            # Determine which email template to use
            if notification_type == 'order':
                EmailService.send_order_confirmation(user, data)
            elif notification_type == 'payment':
                EmailService.send_payment_confirmation(user, data)
            else:
                # Generic email
                EmailService.send_email(
                    recipient=user.email,
                    subject=title,
                    template_name='generic_notification',
                    context={'title': title, 'message': message, 'data': data},
                    notification_type=notification_type
                )
        
        # Send SMS if enabled and requested
        if send_sms and preferences.sms_enabled and user.phone:
            SMSService.send_sms(
                phone_number=user.phone,
                message=f"{title}: {message[:100]}",
                notification_type=notification_type
            )
        
        return notification

from django.utils import timezone