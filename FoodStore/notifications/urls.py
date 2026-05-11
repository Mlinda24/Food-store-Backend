from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register('notifications', views.NotificationViewSet, basename='notification')

urlpatterns = [
    path('', include(router.urls)),
    path('preferences/', views.NotificationPreferenceView.as_view(), name='notification-preferences'),
    path('test/', views.TestNotificationView.as_view(), name='test-notification'),
]