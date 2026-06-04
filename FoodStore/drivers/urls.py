# urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import DriverViewSet, DeliveryOrderViewSet

router = DefaultRouter()
router.register(r'drivers', DriverViewSet, basename='driver')
router.register(r'delivery/orders', DeliveryOrderViewSet, basename='delivery-order')

urlpatterns = [
    path('api/', include(router.urls)),
    path('api/drivers/status/', views.driver_status, name='driver-status'),
path('api/drivers/update_status/', views.update_status, name='update-status'),
path('api/drivers/profile_status/', views.profile_status, name='profile-status'),
path('api/drivers/profile/', views.driver_profile, name='driver-profile'),
]