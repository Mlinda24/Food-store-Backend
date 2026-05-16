from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from .models import (
    Notification, 
    NotificationPreference, 
    EmailLog, 
    SMSLog
)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """
    Admin interface for Notification model
    """
    # List display configuration
    list_display = [
        'id', 
        'user_link', 
        'type_badge', 
        'priority_badge', 
        'title_preview', 
        'is_read_status',
        'created_at_relative'
    ]
    
    # Filters for sidebar
    list_filter = [
        'type', 
        'priority', 
        'is_read', 
        ('created_at', admin.DateFieldListFilter)
    ]
    
    # Search fields
    search_fields = [
        'user__username', 
        'user__email', 
        'title', 
        'message'
    ]
    
    # Read-only fields
    readonly_fields = [
        'id', 
        'created_at', 
        'updated_at', 
        'read_at',
        'message_display'
    ]
    
    # Fieldsets for detail view
    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'user', 'type', 'priority', 'title')
        }),
        ('Content', {
            'fields': ('message_display', 'data'),
            'classes': ('wide',)
        }),
        ('Status', {
            'fields': ('is_read', 'read_at'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    # Default ordering
    ordering = ['-created_at']
    
    # Actions
    actions = ['mark_as_read', 'mark_as_unread', 'delete_selected']
    
    # List view per page
    list_per_page = 50
    
    # Date hierarchy
    date_hierarchy = 'created_at'
    
    # Save as
    save_as = True
    
    def user_link(self, obj):
        """Link to user admin page"""
        url = reverse('admin:accounts_user_change', args=[obj.user.id])
        return format_html('<a href="{}">{}</a>', url, obj.user.username)
    user_link.short_description = 'User'
    user_link.admin_order_field = 'user__username'
    
    def type_badge(self, obj):
        """Colored badge for notification type"""
        colors = {
            'order': '#4CAF50',      # Green
            'payment': '#2196F3',     # Blue
            'promotion': '#FF9800',   # Orange
            'system': '#9E9E9E',      # Gray
            'reminder': '#FFC107',    # Amber
        }
        color = colors.get(obj.type, '#757575')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 12px; font-size: 11px; font-weight: bold;">{}</span>',
            color, obj.type.upper()
        )
    type_badge.short_description = 'Type'
    type_badge.admin_order_field = 'type'
    
    def priority_badge(self, obj):
        """Colored badge for priority level"""
        colors = {
            'low': '#8BC34A',
            'medium': '#FFC107',
            'high': '#FF9800',
            'urgent': '#F44336',
        }
        color = colors.get(obj.priority, '#757575')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 12px; font-size: 11px;">{}</span>',
            color, obj.priority.upper()
        )
    priority_badge.short_description = 'Priority'
    priority_badge.admin_order_field = 'priority'
    
    def title_preview(self, obj):
        """Truncated title for list view"""
        return obj.title[:60] + '...' if len(obj.title) > 60 else obj.title
    title_preview.short_description = 'Title'
    
    def is_read_status(self, obj):
        """Checkmark or X for read status"""
        if obj.is_read:
            return format_html('✅ Yes')
        return format_html('❌ No')
    is_read_status.short_description = 'Read?'
    is_read_status.admin_order_field = 'is_read'
    
    def created_at_relative(self, obj):
        """Human-readable time difference"""
        now = timezone.now()
        diff = now - obj.created_at
        
        if diff.days > 7:
            return obj.created_at.strftime('%Y-%m-%d')
        elif diff.days > 0:
            return format_html('<span title="{}">{} days ago</span>', 
                              obj.created_at.strftime('%Y-%m-%d %H:%M'), diff.days)
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return format_html('<span title="{}">{} hours ago</span>', 
                              obj.created_at.strftime('%Y-%m-%d %H:%M'), hours)
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return format_html('<span title="{}">{} mins ago</span>', 
                              obj.created_at.strftime('%Y-%m-%d %H:%M'), minutes)
        else:
            return format_html('<span title="{}">Just now</span>', 
                              obj.created_at.strftime('%Y-%m-%d %H:%M'))
    created_at_relative.short_description = 'Created'
    created_at_relative.admin_order_field = 'created_at'
    
    def message_display(self, obj):
        """Display message with line breaks"""
        return format_html('<div style="white-space: pre-wrap; max-width: 600px;">{}</div>', 
                          obj.message)
    message_display.short_description = 'Message'
    
    def mark_as_read(self, request, queryset):
        """Action to mark selected notifications as read"""
        updated = queryset.filter(is_read=False).update(is_read=True, read_at=timezone.now())
        self.message_user(request, f'{updated} notifications marked as read.')
    mark_as_read.short_description = 'Mark selected as read'
    
    def mark_as_unread(self, request, queryset):
        """Action to mark selected notifications as unread"""
        updated = queryset.filter(is_read=True).update(is_read=False, read_at=None)
        self.message_user(request, f'{updated} notifications marked as unread.')
    mark_as_unread.short_description = 'Mark selected as unread'
    
    def has_add_permission(self, request):
        """Prevent manual creation of notifications"""
        return False


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    """
    Admin interface for NotificationPreference model
    """
    list_display = [
        'user_link', 
        'email_enabled_icon', 
        'sms_enabled_icon', 
        'push_enabled_icon',
        'order_updates_icon', 
        'payment_alerts_icon',
        'updated_at_relative'
    ]
    
    list_filter = [
        'email_enabled', 
        'sms_enabled', 
        'push_enabled',
        'order_updates', 
        'payment_alerts', 
        'promotions',
        'email_digest'
    ]
    
    search_fields = ['user__username', 'user__email']
    
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('User', {
            'fields': ('user',)
        }),
        ('Channel Preferences', {
            'fields': ('email_enabled', 'sms_enabled', 'push_enabled', 'in_app_enabled'),
            'classes': ('wide',)
        }),
        ('Notification Types', {
            'fields': ('order_updates', 'payment_alerts', 'promotions', 'system_alerts'),
            'classes': ('wide',)
        }),
        ('Digest Settings', {
            'fields': ('email_digest', 'digest_frequency'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def user_link(self, obj):
        """Link to user admin page"""
        url = reverse('admin:accounts_user_change', args=[obj.user.id])
        return format_html('<a href="{}">{}</a>', url, obj.user.username)
    user_link.short_description = 'User'
    user_link.admin_order_field = 'user__username'
    
    def email_enabled_icon(self, obj):
        return '✅' if obj.email_enabled else '❌'
    email_enabled_icon.short_description = 'Email'
    
    def sms_enabled_icon(self, obj):
        return '✅' if obj.sms_enabled else '❌'
    sms_enabled_icon.short_description = 'SMS'
    
    def push_enabled_icon(self, obj):
        return '✅' if obj.push_enabled else '❌'
    push_enabled_icon.short_description = 'Push'
    
    def order_updates_icon(self, obj):
        return '✅' if obj.order_updates else '❌'
    order_updates_icon.short_description = 'Orders'
    
    def payment_alerts_icon(self, obj):
        return '✅' if obj.payment_alerts else '❌'
    payment_alerts_icon.short_description = 'Payments'
    
    def updated_at_relative(self, obj):
        """Human-readable update time"""
        now = timezone.now()
        diff = now - obj.updated_at
        if diff.days > 7:
            return obj.updated_at.strftime('%Y-%m-%d')
        elif diff.days > 0:
            return f'{diff.days} days ago'
        elif diff.seconds > 3600:
            return f'{diff.seconds // 3600} hours ago'
        else:
            return 'Recently'
    updated_at_relative.short_description = 'Last Updated'
    updated_at_relative.admin_order_field = 'updated_at'


@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    """
    Admin interface for EmailLog model
    """
    list_display = [
        'recipient', 
        'subject_preview', 
        'status_badge', 
        'notification_type',
        'sent_at_relative', 
        'created_at_relative'
    ]
    
    list_filter = [
        'status', 
        'notification_type', 
        ('sent_at', admin.DateFieldListFilter)
    ]
    
    search_fields = ['recipient', 'subject', 'error_message']
    
    readonly_fields = [field.name for field in EmailLog._meta.fields]
    
    fieldsets = (
        ('Email Details', {
            'fields': ('recipient', 'subject', 'body', 'notification_type')
        }),
        ('Status', {
            'fields': ('status', 'error_message', 'sent_at')
        }),
        ('Metadata', {
            'fields': ('created_at',)
        }),
    )
    
    def subject_preview(self, obj):
        return obj.subject[:50] + '...' if len(obj.subject) > 50 else obj.subject
    subject_preview.short_description = 'Subject'
    
    def status_badge(self, obj):
        colors = {
            'sent': '#4CAF50',
            'failed': '#F44336',
            'pending': '#FFC107',
        }
        color = colors.get(obj.status, '#9E9E9E')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 12px; font-size: 11px;">{}</span>',
            color, obj.status.upper()
        )
    status_badge.short_description = 'Status'
    
    def sent_at_relative(self, obj):
        if obj.sent_at:
            now = timezone.now()
            diff = now - obj.sent_at
            if diff.days > 7:
                return obj.sent_at.strftime('%Y-%m-%d')
            elif diff.days > 0:
                return f'{diff.days} days ago'
            elif diff.seconds > 3600:
                return f'{diff.seconds // 3600} hours ago'
            else:
                return 'Recently'
        return 'Not sent'
    sent_at_relative.short_description = 'Sent'
    
    def created_at_relative(self, obj):
        now = timezone.now()
        diff = now - obj.created_at
        if diff.days > 7:
            return obj.created_at.strftime('%Y-%m-%d')
        else:
            return f'{diff.days} days' if diff.days > 0 else 'Today'
    created_at_relative.short_description = 'Created'
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False


@admin.register(SMSLog)
class SMSLogAdmin(admin.ModelAdmin):
    """
    Admin interface for SMSLog model
    """
    list_display = [
        'phone_number', 
        'message_preview', 
        'status_badge', 
        'notification_type',
        'sent_at_relative'
    ]
    
    list_filter = [
        'status', 
        'notification_type', 
        ('sent_at', admin.DateFieldListFilter)
    ]
    
    search_fields = ['phone_number', 'message', 'error_message']
    
    readonly_fields = [field.name for field in SMSLog._meta.fields]
    
    fieldsets = (
        ('SMS Details', {
            'fields': ('phone_number', 'message', 'notification_type')
        }),
        ('Status', {
            'fields': ('status', 'error_message', 'provider_response', 'sent_at')
        }),
        ('Metadata', {
            'fields': ('created_at',)
        }),
    )
    
    def message_preview(self, obj):
        return obj.message[:50] + '...' if len(obj.message) > 50 else obj.message
    message_preview.short_description = 'Message'
    
    def status_badge(self, obj):
        colors = {
            'sent': '#4CAF50',
            'failed': '#F44336',
            'pending': '#FFC107',
        }
        color = colors.get(obj.status, '#9E9E9E')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 12px; font-size: 11px;">{}</span>',
            color, obj.status.upper()
        )
    status_badge.short_description = 'Status'
    
    def sent_at_relative(self, obj):
        if obj.sent_at:
            now = timezone.now()
            diff = now - obj.sent_at
            if diff.days > 7:
                return obj.sent_at.strftime('%Y-%m-%d')
            elif diff.days > 0:
                return f'{diff.days} days ago'
            elif diff.seconds > 3600:
                return f'{diff.seconds // 3600} hours ago'
            else:
                return 'Recently'
        return 'Not sent'
    sent_at_relative.short_description = 'Sent'
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False


# Custom admin site customization
admin.site.site_header = 'Food Store Admin Portal'
admin.site.site_title = 'Food Store Admin'
admin.site.index_title = 'Welcome to Food Store Administration'

# Optional: Add custom admin views
class NotificationStats(admin.AdminSite):
    """Custom admin view for notification statistics"""
    
    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path('notification-stats/', self.admin_view(self.notification_stats), 
                 name='notification-stats'),
        ]
        return custom_urls + urls
    
    def notification_stats(self, request):
        from django.shortcuts import render
        from django.db.models import Count, Q
        
        context = {
            'total_notifications': Notification.objects.count(),
            'unread_notifications': Notification.objects.filter(is_read=False).count(),
            'notifications_by_type': Notification.objects.values('type').annotate(count=Count('id')),
            'recent_emails': EmailLog.objects.filter(status='sent')[:10],
            'email_success_rate': EmailLog.objects.aggregate(
                success=Count('id', filter=Q(status='sent')) * 100.0 / Count('id')
            ) if EmailLog.objects.count() > 0 else 0,
        }
        return render(request, 'admin/notification_stats.html', context)

# Uncomment to use custom admin site
# admin_site = NotificationStats(name='foodstoreadmin')