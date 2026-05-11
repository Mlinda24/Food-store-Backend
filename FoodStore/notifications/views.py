from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.viewsets import ModelViewSet
from django.db.models import Q
from django.shortcuts import get_object_or_404
from .models import Notification, NotificationPreference
from .serializers import (
    NotificationSerializer, NotificationPreferenceSerializer,
    MarkNotificationReadSerializer
)
from .services import NotificationService

class NotificationViewSet(ModelViewSet):
    """
    ViewSet for managing user notifications
    """
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Return only current user's notifications"""
        return Notification.objects.filter(user=self.request.user)
    
    @action(detail=False, methods=['get'])
    def unread(self, request):
        """Get unread notifications"""
        notifications = self.get_queryset().filter(is_read=False)
        serializer = self.get_serializer(notifications, many=True)
        return Response({
            'count': notifications.count(),
            'notifications': serializer.data
        })
    
    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        """Get count of unread notifications"""
        count = self.get_queryset().filter(is_read=False).count()
        return Response({'unread_count': count})
    
    @action(detail=False, methods=['post'])
    def mark_read(self, request):
        """Mark notifications as read"""
        serializer = MarkNotificationReadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        if serializer.validated_data.get('mark_all'):
            # Mark all notifications as read
            self.get_queryset().filter(is_read=False).update(is_read=True)
            return Response({'message': 'All notifications marked as read'})
        
        # Mark specific notifications
        notification_ids = serializer.validated_data.get('notification_ids', [])
        notifications = self.get_queryset().filter(id__in=notification_ids, is_read=False)
        
        for notification in notifications:
            notification.mark_as_read()
        
        return Response({'message': f'{len(notifications)} notifications marked as read'})
    
    @action(detail=True, methods=['post'])
    def read(self, request, pk=None):
        """Mark a single notification as read"""
        notification = self.get_object()
        notification.mark_as_read()
        return Response({'message': 'Notification marked as read'})
    
    @action(detail=False, methods=['delete'])
    def clear_all(self, request):
        """Delete all notifications for the user"""
        count = self.get_queryset().count()
        self.get_queryset().delete()
        return Response({'message': f'{count} notifications deleted'})


class NotificationPreferenceView(generics.RetrieveUpdateAPIView):
    """
    Get and update user's notification preferences
    """
    serializer_class = NotificationPreferenceSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        preferences, created = NotificationPreference.objects.get_or_create(
            user=self.request.user
        )
        return preferences


class TestNotificationView(generics.GenericAPIView):
    """
    Test endpoint for sending notifications (development only)
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """Send a test notification"""
        notification = NotificationService.send_notification(
            user=request.user,
            notification_type='system',
            title='Test Notification',
            message='This is a test notification from your food store app!',
            data={'test': True},
            send_email=True,
            send_sms=False
        )
        
        return Response({
            'message': 'Test notification sent',
            'notification': NotificationSerializer(notification).data
        })