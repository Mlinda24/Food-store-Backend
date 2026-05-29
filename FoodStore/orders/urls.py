# orders/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'orders', views.OrderViewSet, basename='order')
router.register(r'cart', views.CartViewSet, basename='cart')

urlpatterns = [
    path('', include(router.urls)),
    
    # Explicit endpoint for my_orders
    path('my_orders/', views.OrderViewSet.as_view({'get': 'my_orders'}), name='my-orders'),
    
    # Cart endpoints
    path('cart/', views.CartViewSet.as_view({'get': 'retrieve'}), name='cart'),
    path('cart/add_item/', views.CartViewSet.as_view({'post': 'add_item'}), name='add-to-cart'),
    path('cart/update_item/', views.CartViewSet.as_view({'patch': 'update_item'}), name='update-cart-item'),
    path('cart/remove_item/', views.CartViewSet.as_view({'delete': 'remove_item'}), name='remove-from-cart'),
    path('cart/clear_cart/', views.CartViewSet.as_view({'delete': 'clear'}), name='clear-cart'),
]