from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db.models import Sum
from decimal import Decimal
from datetime import date

from .models import Restaurant, MenuItem, Category, RestaurantWallet, WalletTransaction
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
        restaurant = serializer.save(owner=self.request.user)
        # Create wallet automatically for new restaurant
        RestaurantWallet.objects.get_or_create(restaurant=restaurant)

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
            
            # Get or create wallet
            wallet, created = RestaurantWallet.objects.get_or_create(restaurant=restaurant)

            now = timezone.now()
            today = now.date()
            current_month = now.month
            current_year = now.year

            today_orders = Order.objects.filter(
                restaurant_id=restaurant.id, created__date=today
            )
            monthly_orders = Order.objects.filter(
                restaurant_id=restaurant.id,
                created__year=current_year,
                created__month=current_month
            )
            total_orders = Order.objects.filter(restaurant_id=restaurant.id)
            active_orders = Order.objects.filter(
                restaurant_id=restaurant.id,
                status__in=['pending', 'confirmed', 'preparing']
            )

            total_earnings = total_orders.aggregate(Sum('total_price'))['total_price__sum'] or Decimal('0')
            monthly_earnings = monthly_orders.aggregate(Sum('total_price'))['total_price__sum'] or Decimal('0')
            today_earnings = today_orders.aggregate(Sum('total_price'))['total_price__sum'] or Decimal('0')

            stats = {
                # Wallet information (what they can withdraw)
                'walletBalance': float(wallet.balance),
                'totalEarned': float(wallet.total_earned),
                'totalWithdrawn': float(wallet.total_withdrawn),
                # Order statistics (for display only)
                'todayEarnings': float(today_earnings),
                'todayOrders': today_orders.count(),
                'monthlyEarnings': float(monthly_earnings),
                'monthlyOrders': monthly_orders.count(),
                'totalEarnings': float(total_earnings),
                'totalOrders': total_orders.count(),
                'activeOrders': active_orders.count(),
                'averageRating': float(restaurant.rating) if restaurant.rating else 4.5,
            }
            return Response(stats)
        except Restaurant.DoesNotExist:
            return Response({'detail': 'No restaurant found'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['get'])
    def wallet_balance(self, request):
        """Get restaurant wallet balance"""
        try:
            restaurant = Restaurant.objects.get(owner=request.user)
            wallet, created = RestaurantWallet.objects.get_or_create(restaurant=restaurant)
            
            return Response({
                'balance': float(wallet.balance),
                'total_earned': float(wallet.total_earned),
                'total_withdrawn': float(wallet.total_withdrawn),
            })
        except Restaurant.DoesNotExist:
            return Response({'error': 'Restaurant not found'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['get'])
    def wallet_transactions(self, request):
        """Get wallet transaction history"""
        try:
            restaurant = Restaurant.objects.get(owner=request.user)
            wallet, created = RestaurantWallet.objects.get_or_create(restaurant=restaurant)
            
            transactions = WalletTransaction.objects.filter(wallet=wallet).order_by('-created_at')[:50]
            
            data = []
            for tx in transactions:
                data.append({
                    'id': tx.id,
                    'type': tx.transaction_type,
                    'amount': float(tx.amount),
                    'formatted_amount': f"MK{tx.amount:,.2f}",
                    'status': tx.status,
                    'reference': str(tx.reference),
                    'description': tx.description,
                    'created_at': tx.created_at.isoformat(),
                })
            
            return Response({
                'balance': float(wallet.balance),
                'total_earned': float(wallet.total_earned),
                'total_withdrawn': float(wallet.total_withdrawn),
                'transactions': data
            })
        except Restaurant.DoesNotExist:
            return Response({'error': 'Restaurant not found'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['post'])
    def withdraw(self, request):
        """Request withdrawal from restaurant wallet to mobile money"""
        try:
            restaurant = Restaurant.objects.get(owner=request.user)
            wallet = restaurant.wallet
            
            amount = Decimal(str(request.data.get('amount', '0')))
            phone_number = request.data.get('phone_number', '')
            provider = request.data.get('provider', 'mpamba')
            
            # Validate amount
            if amount <= 0:
                return Response({'error': 'Invalid amount'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Check minimum withdrawal
            min_withdrawal = Decimal('1000.00')
            if amount < min_withdrawal:
                return Response({'error': f'Minimum withdrawal amount is MK{min_withdrawal}'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Check sufficient balance
            if wallet.balance < amount:
                return Response({'error': f'Insufficient balance. Available: MK{wallet.balance}'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Validate phone number
            if not phone_number:
                return Response({'error': 'Phone number is required'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Clean phone number
            phone_cleaned = ''.join(filter(str.isdigit, phone_number))
            if len(phone_cleaned) < 9:
                return Response({'error': 'Please enter a valid phone number'}, status=status.HTTP_400_BAD_REQUEST)
            
            if not phone_cleaned.startswith('0'):
                phone_cleaned = f'0{phone_cleaned}'
            
            # Deduct wallet balance
            wallet.balance -= amount
            wallet.total_withdrawn += amount
            wallet.save()
            
            # Create transaction record
            import uuid
            transaction = WalletTransaction.objects.create(
                wallet=wallet,
                transaction_type='debit',
                amount=amount,
                status='pending',
                description=f'Withdrawal request to {phone_cleaned} via {provider}'
            )
            
            print(f'💰 Withdrawal requested:')
            print(f'   Restaurant: {restaurant.name}')
            print(f'   Amount: MK{amount}')
            print(f'   Phone: {phone_cleaned}')
            print(f'   Provider: {provider}')
            print(f'   New Balance: MK{wallet.balance}')
            
            return Response({
                'success': True,
                'message': 'Withdrawal request submitted successfully',
                'reference': str(transaction.reference),
                'amount': float(amount),
                'new_balance': float(wallet.balance),
            }, status=status.HTTP_200_OK)
            
        except Restaurant.DoesNotExist:
            return Response({'error': 'Restaurant not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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
            menu_item = serializer.save(restaurant=restaurant)
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