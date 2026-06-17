from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db.models import Sum
from datetime import date

from .models import Restaurant, MenuItem, Category
from .serializers import (
    RestaurantSerializer, MenuItemSerializer, MenuItemPublicSerializer, 
    CategorySerializer
)
from orders.models import Order

# ------------------------------
# Restaurant ViewSet
# ------------------------------
class RestaurantViewSet(viewsets.ModelViewSet):
    queryset = Restaurant.objects.all()
    serializer_class = RestaurantSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'restaurant':
            return Restaurant.objects.filter(owner=user)
        return Restaurant.objects.all()

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    @action(detail=False, methods=['get', 'patch'])
    def my_restaurant(self, request):
        try:
            restaurant = Restaurant.objects.get(owner=request.user)
            if request.method == 'GET':
                serializer = RestaurantSerializer(restaurant)
                return Response(serializer.data)
            elif request.method == 'PATCH':
                serializer = RestaurantSerializer(
                    restaurant, data=request.data, partial=True
                )
                if serializer.is_valid():
                    serializer.save()
                    return Response(serializer.data)
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Restaurant.DoesNotExist:
            return Response({'detail': 'No restaurant found'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        try:
            restaurant = Restaurant.objects.get(owner=request.user)

            now = timezone.now()
            today = now.date()
            current_month = now.month
            current_year = now.year

            today_orders = Order.objects.filter(
                restaurant=restaurant, created__date=today
            )
            monthly_orders = Order.objects.filter(
                restaurant=restaurant,
                created__year=current_year,
                created__month=current_month
            )
            total_orders = Order.objects.filter(restaurant=restaurant)
            active_orders = Order.objects.filter(
                restaurant=restaurant, status__in=['pending', 'confirmed', 'preparing']
            )

            stats = {
                'todayEarnings': float(today_orders.aggregate(Sum('total_price'))['total_price__sum'] or 0),
                'todayOrders': today_orders.count(),
                'monthlyEarnings': float(monthly_orders.aggregate(Sum('total_price'))['total_price__sum'] or 0),
                'monthlyOrders': monthly_orders.count(),
                'totalEarnings': float(total_orders.aggregate(Sum('total_price'))['total_price__sum'] or 0),
                'totalOrders': total_orders.count(),
                'activeOrders': active_orders.count(),
                'averageRating': 4.8,
            }
            return Response(stats)
        except Restaurant.DoesNotExist:
            return Response({'detail': 'No restaurant found'}, status=status.HTTP_404_NOT_FOUND)


# ------------------------------
# Menu Item ViewSets
# ------------------------------
class MenuItemViewSet(viewsets.ModelViewSet):
    queryset = MenuItem.objects.all()
    serializer_class = MenuItemSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated and user.role == 'restaurant':
            try:
                restaurant = Restaurant.objects.get(owner=user)
                return MenuItem.objects.filter(restaurant=restaurant)
            except Restaurant.DoesNotExist:
                return MenuItem.objects.none()
        return MenuItem.objects.filter(is_available=True)
    
    def create(self, request, *args, **kwargs):
        """Create a new menu item for the restaurant owner's restaurant"""
        try:
            restaurant = Restaurant.objects.get(owner=request.user)
        except Restaurant.DoesNotExist:
            return Response(
                {'error': 'You do not have a restaurant registered'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Prepare data with restaurant
        data = request.data.copy()
        data['restaurant'] = restaurant.id
        
        # Handle category (create if doesn't exist)
        category_name = data.get('category')
        if category_name and isinstance(category_name, str) and category_name.strip():
            category, created = Category.objects.get_or_create(
                name=category_name.strip(),
                restaurant=restaurant
            )
            data['category'] = category.id
        else:
            data['category'] = None
        
        serializer = self.get_serializer(data=data)
        if serializer.is_valid():
            menu_item = serializer.save()
            print(f"✅ Menu item created: {menu_item.name}")
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        else:
            print(f"❌ Serializer errors: {serializer.errors}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def update(self, request, *args, **kwargs):
        """Update a menu item"""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        
        # Check if user owns this menu item
        try:
            restaurant = Restaurant.objects.get(owner=request.user)
            if instance.restaurant != restaurant:
                return Response(
                    {'error': 'You do not have permission to edit this item'},
                    status=status.HTTP_403_FORBIDDEN
                )
        except Restaurant.DoesNotExist:
            return Response(
                {'error': 'Restaurant not found'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Make a mutable copy of request data
        request_data = request.data.copy()
        
        # Handle category
        category_name = request_data.get('category')
        if category_name and isinstance(category_name, str) and category_name.strip():
            category, created = Category.objects.get_or_create(
                name=category_name.strip(),
                restaurant=restaurant
            )
            request_data['category'] = category.id
        elif category_name == '' or category_name is None:
            request_data['category'] = None
        
        serializer = self.get_serializer(instance, data=request_data, partial=partial)
        if serializer.is_valid():
            menu_item = serializer.save()
            print(f"✅ Menu item updated: {menu_item.name}")
            return Response(serializer.data)
        print(f"❌ Update errors: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def destroy(self, request, *args, **kwargs):
        """Delete a menu item"""
        instance = self.get_object()
        
        # Check if user owns this menu item
        try:
            restaurant = Restaurant.objects.get(owner=request.user)
            if instance.restaurant != restaurant:
                return Response(
                    {'error': 'You do not have permission to delete this item'},
                    status=status.HTTP_403_FORBIDDEN
                )
        except Restaurant.DoesNotExist:
            return Response(
                {'error': 'Restaurant not found'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        item_name = instance.name
        self.perform_destroy(instance)
        print(f"🗑️ Menu item deleted: {item_name}")
        return Response({'message': f'Menu item "{item_name}" deleted successfully'}, status=status.HTTP_204_NO_CONTENT)


class RestaurantMenuViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    
    def list(self, request, restaurant_pk=None):
        menu_items = MenuItem.objects.filter(restaurant_id=restaurant_pk, is_available=True)
        serializer = MenuItemPublicSerializer(menu_items, many=True)
        return Response(serializer.data)


# ------------------------------
# All Available Menu Items
# ------------------------------
class AvailableMenuItemsViewSet(viewsets.ViewSet):
    """
    Returns all available menu items across all restaurants.
    """
    permission_classes = [IsAuthenticated]
    
    def list(self, request):
        menu_items = MenuItem.objects.filter(is_available=True, restaurant__is_open=True)
        serializer = MenuItemPublicSerializer(menu_items, many=True)
        return Response(serializer.data)