from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import DriverViewSet, DeliveryOrderViewSet

router = DefaultRouter()
router.register(r'drivers', DriverViewSet, basename='driver')
router.register(r'orders', DeliveryOrderViewSet, basename='delivery-order')

urlpatterns = [
    path('', include(router.urls)),
]