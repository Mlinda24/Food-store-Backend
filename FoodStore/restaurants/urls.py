# restaurants/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .customer_views import (
    CustomerRestaurantListView,
    CustomerRestaurantDetailView,
    RestaurantMenuView,
    CustomerMenuSearchView,
    FeaturedRestaurantsView
)

router = DefaultRouter()
router.register(r'owner/restaurants', views.RestaurantViewSet)
router.register(r'owner/menu-items', views.MenuItemViewSet)

urlpatterns = [
    path('', include(router.urls)),
    
    # Add direct withdrawal endpoint (optional)
    path('restaurants/withdraw/', views.RestaurantViewSet.as_view({'post': 'withdraw'}), name='withdraw'),
    
    # Customer endpoints
    path('customer/restaurants/', CustomerRestaurantListView.as_view(), name='customer-restaurants'),
    path('customer/restaurants/<int:pk>/', CustomerRestaurantDetailView.as_view(), name='customer-restaurant-detail'),
    path('customer/restaurants/<int:pk>/menu/', RestaurantMenuView.as_view(), name='restaurant-menu'),
    path('customer/menu/search/', CustomerMenuSearchView.as_view(), name='menu-search'),
    path('customer/featured/', FeaturedRestaurantsView.as_view(), name='featured-restaurants'),
]