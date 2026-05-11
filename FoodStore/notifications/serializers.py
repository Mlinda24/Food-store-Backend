from rest_framework import serializers
from .models import Notification, NotificationPreference, EmailLog, SMSLog

class NotificationSerializer(serializers.ModelSerializer):
    """Serializer for notifications"""
    time_ago = serializers.SerializerMethodField()
    
    class Meta:
        model = Notification
        fields = [
            'id', 'type', 'priority', 'title', 'message', 
            'data', 'is_read', 'read_at', 'created_at', 'time_ago'
        ]
        read_only_fields = ['id', 'created_at', 'read_at', 'time_ago']
    
    def get_time_ago(self, obj):
        """Get human-readable time since notification was created"""
        from django.utils.timesince import timesince
        return timesince(obj.created_at)


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    """Serializer for notification preferences"""
    class Meta:
        model = NotificationPreference
        exclude = ['user', 'created_at', 'updated_at']


class MarkNotificationReadSerializer(serializers.Serializer):
    """Serializer for marking notifications as read"""
    notification_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False
    )
    mark_all = serializers.BooleanField(default=False)


class EmailLogSerializer(serializers.ModelSerializer):
    """Serializer for email logs (admin only)"""
    class Meta:
        model = EmailLog
        fields = '__all__'
        read_only_fields = ['id', 'created_at']


class SMSLogSerializer(serializers.ModelSerializer):
    """Serializer for SMS logs (admin only)"""
    class Meta:
        model = SMSLog
        fields = '__all__'
        read_only_fields = ['id', 'created_at']