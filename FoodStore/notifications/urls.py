# notifications/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'notifications', views.NotificationViewSet, basename='notification')

urlpatterns = [
    path('', include(router.urls)),
    
    # Explicit endpoints for notifications
    path('notifications/', views.NotificationViewSet.as_view({'get': 'list'}), name='notifications-list'),
    path('notifications/unread_count/', views.NotificationViewSet.as_view({'get': 'unread_count'}), name='unread-count'),
    path('notifications/mark_read/', views.NotificationViewSet.as_view({'post': 'mark_read'}), name='mark-read'),
    path('notifications/<int:pk>/read/', views.NotificationViewSet.as_view({'post': 'read'}), name='notification-read'),
]