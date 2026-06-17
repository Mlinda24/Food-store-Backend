from rest_framework import generics, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from .models import Restaurant, MenuItem
from .serializers import RestaurantSerializer, MenuItemPublicSerializer

class CustomerRestaurantListView(generics.ListAPIView):
    """Customer-facing: Browse all available restaurants"""
    serializer_class = RestaurantSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = Restaurant.objects.filter(is_open=True)
        
        search = self.request.query_params.get('search', '')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | 
                Q(description__icontains=search)
            )
        
        min_rating = self.request.query_params.get('min_rating')
        if min_rating:
            queryset = queryset.filter(rating__gte=min_rating)
        
        sort_by = self.request.query_params.get('sort', 'rating')
        if sort_by == 'rating':
            queryset = queryset.order_by('-rating')
        elif sort_by == 'name':
            queryset = queryset.order_by('name')
        
        return queryset


class CustomerRestaurantDetailView(generics.RetrieveAPIView):
    """Customer-facing: View restaurant details"""
    queryset = Restaurant.objects.filter(is_open=True)
    serializer_class = RestaurantSerializer
    permission_classes = [IsAuthenticated]
    
    def get(self, request, *args, **kwargs):
        if request.path.endswith('/menu/'):
            return self.get_menu(request, *args, **kwargs)
        return super().get(request, *args, **kwargs)
    
    def get_menu(self, request, *args, **kwargs):
        restaurant = self.get_object()
        menu_items = MenuItem.objects.filter(
            restaurant=restaurant,
            is_available=True
        ).select_related('category')
        
        categories_data = {}
        for item in menu_items:
            category_name = item.category.name if item.category else "Other"
            if category_name not in categories_data:
                categories_data[category_name] = {
                    'category_id': item.category.id if item.category else None,
                    'items': []
                }
            categories_data[category_name]['items'].append(
                MenuItemPublicSerializer(item).data
            )
        
        menu_structure = [
            {
                'category_name': name,
                'category_id': data['category_id'],
                'items': data['items']
            }
            for name, data in categories_data.items()
        ]
        
        return Response({
            'restaurant': self.get_serializer(restaurant).data,
            'menu': menu_structure
        })


class CustomerMenuSearchView(generics.ListAPIView):
    """Customer-facing: Search menu items"""
    serializer_class = MenuItemPublicSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = MenuItem.objects.filter(
            is_available=True,
            restaurant__is_open=True
        ).select_related('restaurant', 'category')
        
        search_query = self.request.query_params.get('q', '')
        if search_query:
            queryset = queryset.filter(
                Q(name__icontains=search_query) |
                Q(description__icontains=search_query)
            )
        
        max_price = self.request.query_params.get('max_price')
        if max_price:
            queryset = queryset.filter(price__lte=max_price)
        
        return queryset


class FeaturedRestaurantsView(generics.ListAPIView):
    """Get featured restaurants for homepage"""
    serializer_class = RestaurantSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Restaurant.objects.filter(is_open=True).order_by('-rating')[:10]



class RestaurantMenuView(generics.GenericAPIView):
    """
    Get restaurant menu grouped by categories
    GET /api/customer/restaurants/{id}/menu/
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, pk):
        try:
            restaurant = Restaurant.objects.get(pk=pk, is_open=True)
        except Restaurant.DoesNotExist:
            return Response({'error': 'Restaurant not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Get all available menu items for this restaurant
        menu_items = MenuItem.objects.filter(
            restaurant=restaurant,
            is_available=True
        ).select_related('category')
        
        # Group by category
        categories_data = {}
        for item in menu_items:
            category_name = item.category.name if item.category else "Other"
            if category_name not in categories_data:
                categories_data[category_name] = {
                    'category_id': item.category.id if item.category else None,
                    'items': []
                }
            categories_data[category_name]['items'].append(
                MenuItemPublicSerializer(item).data
            )
        
        # Format response
        menu_structure = [
            {
                'category_name': name,
                'category_id': data['category_id'],
                'items': data['items']
            }
            for name, data in categories_data.items()
        ]
        
        return Response({
            'restaurant': RestaurantSerializer(restaurant).data,
            'menu': menu_structure
        })        