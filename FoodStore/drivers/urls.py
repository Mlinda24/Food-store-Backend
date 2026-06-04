from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import DriverViewSet, DeliveryOrderViewSet

router = DefaultRouter()
router.register(r'', DriverViewSet, basename='driver')
router.register(r'delivery/orders', DeliveryOrderViewSet, basename='delivery-order')

urlpatterns = [
    path('', include(router.urls)),
]