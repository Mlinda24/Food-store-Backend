from rest_framework import viewsets, generics, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db.models import Sum
from decimal import Decimal
import uuid
import json
import requests
import logging
from django.conf import settings

from .models import Restaurant, MenuItem, Category, RestaurantWallet, WalletTransaction
from .serializers import (
    RestaurantSerializer, MenuItemSerializer, MenuItemPublicSerializer,
    CategorySerializer
)
from orders.models import Order

logger = logging.getLogger(__name__)


# ─── Restaurant ViewSet ───────────────────────────────────────────────────────

class RestaurantViewSet(viewsets.ModelViewSet):
    queryset = Restaurant.objects.all()
    serializer_class = RestaurantSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Short-circuit during drf-yasg schema generation
        if getattr(self, 'swagger_fake_view', False):
            return Restaurant.objects.none()

        user = self.request.user

        # AnonymousUser has no 'role' attribute — guard explicitly
        if not user.is_authenticated:
            return Restaurant.objects.none()

        if user.role == 'restaurant':
            return Restaurant.objects.filter(owner=user)

        return Restaurant.objects.all()

    def perform_create(self, serializer):
        restaurant = serializer.save(owner=self.request.user)
        RestaurantWallet.objects.get_or_create(restaurant=restaurant)

    # ── /my_restaurant ────────────────────────────────────────────────────────

    @action(detail=False, methods=['get', 'patch'])
    def my_restaurant(self, request):
        try:
            restaurant = Restaurant.objects.get(owner=request.user)
        except Restaurant.DoesNotExist:
            return Response(
                {'detail': 'No restaurant found'},
                status=status.HTTP_404_NOT_FOUND
            )

        if request.method == 'GET':
            serializer = RestaurantSerializer(restaurant)
            return Response(serializer.data)

        # PATCH
        serializer = RestaurantSerializer(
            restaurant, data=request.data, partial=True
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # ── /stats ────────────────────────────────────────────────────────────────

    @action(detail=False, methods=['get'])
    def stats(self, request):
        try:
            restaurant = Restaurant.objects.get(owner=request.user)
        except Restaurant.DoesNotExist:
            return Response(
                {'detail': 'No restaurant found'},
                status=status.HTTP_404_NOT_FOUND
            )

        wallet, _ = RestaurantWallet.objects.get_or_create(restaurant=restaurant)

        now = timezone.now()
        today = now.date()

        today_orders = Order.objects.filter(
            restaurant_id=restaurant.id, created__date=today
        )
        monthly_orders = Order.objects.filter(
            restaurant_id=restaurant.id,
            created__year=now.year,
            created__month=now.month,
        )
        total_orders = Order.objects.filter(restaurant_id=restaurant.id)
        active_orders = Order.objects.filter(
            restaurant_id=restaurant.id,
            status__in=['pending', 'confirmed', 'preparing'],
        )

        def _sum(qs):
            return float(
                qs.aggregate(Sum('total_price'))['total_price__sum'] or Decimal('0')
            )

        return Response({
            'walletBalance':    float(wallet.balance),
            'totalEarned':      float(wallet.total_earned),
            'totalWithdrawn':   float(wallet.total_withdrawn),
            'todayEarnings':    _sum(today_orders),
            'todayOrders':      today_orders.count(),
            'monthlyEarnings':  _sum(monthly_orders),
            'monthlyOrders':    monthly_orders.count(),
            'totalEarnings':    _sum(total_orders),
            'totalOrders':      total_orders.count(),
            'activeOrders':     active_orders.count(),
            'averageRating':    float(restaurant.rating) if restaurant.rating else 4.5,
        })

    # ── /wallet_balance ───────────────────────────────────────────────────────

    @action(detail=False, methods=['get'])
    def wallet_balance(self, request):
        try:
            restaurant = Restaurant.objects.get(owner=request.user)
        except Restaurant.DoesNotExist:
            return Response(
                {'error': 'Restaurant not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        wallet, _ = RestaurantWallet.objects.get_or_create(restaurant=restaurant)
        return Response({
            'balance':          float(wallet.balance),
            'total_earned':     float(wallet.total_earned),
            'total_withdrawn':  float(wallet.total_withdrawn),
        })

    # ── /wallet_transactions ──────────────────────────────────────────────────

    @action(detail=False, methods=['get'])
    def wallet_transactions(self, request):
        try:
            restaurant = Restaurant.objects.get(owner=request.user)
        except Restaurant.DoesNotExist:
            return Response(
                {'error': 'Restaurant not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        wallet, _ = RestaurantWallet.objects.get_or_create(restaurant=restaurant)
        transactions = (
            WalletTransaction.objects
            .filter(wallet=wallet)
            .order_by('-created_at')[:50]
        )

        return Response({
            'balance':          float(wallet.balance),
            'total_earned':     float(wallet.total_earned),
            'total_withdrawn':  float(wallet.total_withdrawn),
            'transactions': [
                {
                    'id':               tx.id,
                    'type':             tx.transaction_type,
                    'amount':           float(tx.amount),
                    'formatted_amount': f'MK{tx.amount:,.2f}',
                    'status':           tx.status,
                    'reference':        str(tx.reference),
                    'description':      tx.description,
                    'created_at':       tx.created_at.isoformat(),
                }
                for tx in transactions
            ],
        })

    # ── /withdraw ─────────────────────────────────────────────────────────────

    @action(detail=False, methods=['post'])
    def withdraw(self, request):
        try:
            restaurant = Restaurant.objects.get(owner=request.user)
        except Restaurant.DoesNotExist:
            return Response(
                {'error': 'Restaurant not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        try:
            wallet = restaurant.wallet
        except RestaurantWallet.DoesNotExist:
            wallet, _ = RestaurantWallet.objects.get_or_create(restaurant=restaurant)

        # ── Validate inputs ───────────────────────────────────────────────────

        try:
            amount = Decimal(str(request.data.get('amount', '0')))
        except Exception:
            return Response(
                {'error': 'Invalid amount format'},
                status=status.HTTP_400_BAD_REQUEST
            )

        phone_number = request.data.get('phone_number', '').strip()
        provider = request.data.get('provider', 'mpamba').strip()

        if amount <= 0:
            return Response(
                {'error': 'Amount must be greater than zero'},
                status=status.HTTP_400_BAD_REQUEST
            )

        MIN_WITHDRAWAL = Decimal('50.00')
        if amount < MIN_WITHDRAWAL:
            return Response(
                {'error': f'Minimum withdrawal is MK{MIN_WITHDRAWAL}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if wallet.balance < amount:
            return Response(
                {'error': f'Insufficient balance. Available: MK{wallet.balance:.2f}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not phone_number:
            return Response(
                {'error': 'Phone number is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Clean phone number - remove any non-digit characters
        phone_cleaned = ''.join(filter(str.isdigit, phone_number))
        
        # Remove leading '0' if present, PayChangu wants 9 digits without leading zero
        if phone_cleaned.startswith('0'):
            phone_cleaned = phone_cleaned[1:]
        
        if len(phone_cleaned) != 9:
            return Response(
                {'error': 'Please enter a valid 9-digit phone number (e.g., 881779699)'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ── Create transaction record ─────────────────────────────────────────

        transaction = WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type='debit',
            amount=amount,
            status='processing',
            description=f'Withdrawal to {phone_number} via {provider}',
        )

        # ── Map provider to PayChangu format ──────────────────────────────────
        provider_map = {
            'mpamba': 'tnm',
            'airtel': 'airtel_money',
        }
        paychangu_provider = provider_map.get(provider, 'tnm')
        
        # ── For PayChangu, we use the same /payment endpoint but with different payload ──
        # This creates a payout instead of a payment collection
        payout_data = {
            'amount': str(amount),
            'currency': 'MWK',
            'type': 'payout',  # Specify this is a payout
            'phone_number': phone_cleaned,
            'provider': paychangu_provider,
            'reference': str(transaction.reference),
            'callback_url': f'{settings.WEBHOOK_BASE_URL}/api/payments/withdrawal-webhook/',
            'description': f'Withdrawal for restaurant {restaurant.name}',
            'first_name': restaurant.name,
            'last_name': 'Restaurant',
            'email': restaurant.owner.email if restaurant.owner else 'restaurant@foodstore.com',
        }

        headers = {
            'Authorization': f'Bearer {settings.PAYCHANGU_SECRET_KEY}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }

        # Use the same /payment endpoint that works for collections
        url = f'{settings.PAYCHANGU_BASE_URL}/payment'
        
        logger.info(f'Processing withdrawal: {amount} to {phone_cleaned}')
        logger.info(f'Endpoint: {url}')
        logger.info(f'Payload: {json.dumps(payout_data)}')

        try:
            response = requests.post(
                url,
                json=payout_data,
                headers=headers,
                timeout=30,
            )
            
            logger.info(f'Response status: {response.status_code}')
            logger.info(f'Response body: {response.text}')
            
            if response.status_code in (200, 201, 202):
                response_data = response.json()
                data = response_data.get('data', response_data)
                
                # Update transaction with payout info
                transaction.status = 'completed'
                transaction.metadata = {
                    'payout_id': data.get('id') or data.get('transaction_id'),
                    'payout_reference': data.get('reference'),
                    'provider_response': response_data,
                    'phone_number': phone_number,
                    'provider': provider,
                    'status': data.get('status'),
                }
                transaction.save()

                # Deduct from wallet
                wallet.balance -= amount
                wallet.total_withdrawn += amount
                wallet.save(update_fields=['balance', 'total_withdrawn'])

                logger.info(f'Withdrawal successful: {amount} to {phone_cleaned}, tx={transaction.reference}')

                return Response({
                    'success': True,
                    'message': f'MK{amount:,.2f} sent to {phone_number} successfully',
                    'reference': str(transaction.reference),
                    'payout_reference': data.get('reference'),
                    'amount': float(amount),
                    'new_balance': float(wallet.balance),
                }, status=status.HTTP_200_OK)
            else:
                # Payout failed - mark transaction as failed
                transaction.status = 'failed'
                transaction.metadata = {
                    'error': response.text,
                    'status_code': response.status_code,
                    'phone_number': phone_number,
                    'provider': provider,
                }
                transaction.save()
                
                logger.error(f'Withdrawal failed: {response.text}')
                
                # Try to parse error message
                try:
                    error_data = response.json()
                    error_message = error_data.get('message', {})
                    if isinstance(error_message, dict):
                        error_text = ', '.join([f'{k}: {v}' for k, v in error_message.items()])
                    else:
                        error_text = str(error_message)
                except:
                    error_text = response.text
                
                return Response({
                    'error': 'Withdrawal failed. Please try again.',
                    'details': error_text,
                }, status=status.HTTP_400_BAD_REQUEST)
                
        except requests.RequestException as e:
            transaction.status = 'failed'
            transaction.metadata = {
                'error': str(e),
                'phone_number': phone_number,
                'provider': provider,
            }
            transaction.save()
            
            logger.error(f'Withdrawal request failed: {e}')
            
            return Response({
                'error': 'Payment service unavailable. Please try again.',
                'details': str(e),
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ─── Menu Item ViewSet (owner) ────────────────────────────────────────────────

class MenuItemViewSet(viewsets.ModelViewSet):
    queryset = MenuItem.objects.all()
    serializer_class = MenuItemSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return MenuItem.objects.none()

        user = self.request.user

        if not user.is_authenticated:
            return MenuItem.objects.none()

        if user.role == 'restaurant':
            try:
                restaurant = Restaurant.objects.get(owner=user)
                return MenuItem.objects.filter(restaurant=restaurant)
            except Restaurant.DoesNotExist:
                return MenuItem.objects.none()

        return MenuItem.objects.filter(is_available=True)

    def _resolve_category(self, category_name, restaurant):
        """Return a Category id from a name string, or None."""
        if category_name and isinstance(category_name, str) and category_name.strip():
            category, _ = Category.objects.get_or_create(
                name=category_name.strip(),
                restaurant=restaurant,
            )
            return category.id
        return None

    def _get_owner_restaurant(self, user):
        """Return the restaurant owned by user, or raise."""
        try:
            return Restaurant.objects.get(owner=user)
        except Restaurant.DoesNotExist:
            return None

    # ── Create ────────────────────────────────────────────────────────────────

    def create(self, request, *args, **kwargs):
        restaurant = self._get_owner_restaurant(request.user)
        if not restaurant:
            return Response(
                {'error': 'You do not have a restaurant registered'},
                status=status.HTTP_400_BAD_REQUEST
            )

        data = request.data.copy()
        data['restaurant'] = restaurant.id
        data['category'] = self._resolve_category(data.get('category'), restaurant)

        serializer = self.get_serializer(data=data)
        if serializer.is_valid():
            menu_item = serializer.save(restaurant=restaurant)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # ── Update / Partial update ───────────────────────────────────────────────

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()

        restaurant = self._get_owner_restaurant(request.user)
        if not restaurant:
            return Response(
                {'error': 'Restaurant not found'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if instance.restaurant != restaurant:
            return Response(
                {'error': 'You do not have permission to edit this item'},
                status=status.HTTP_403_FORBIDDEN
            )

        data = request.data.copy()
        category_name = data.get('category')
        resolved = self._resolve_category(category_name, restaurant)
        # Only set to None when caller explicitly sends empty string
        if category_name is not None:
            data['category'] = resolved

        serializer = self.get_serializer(instance, data=data, partial=partial)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # ── Destroy ───────────────────────────────────────────────────────────────

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()

        restaurant = self._get_owner_restaurant(request.user)
        if not restaurant:
            return Response(
                {'error': 'Restaurant not found'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if instance.restaurant != restaurant:
            return Response(
                {'error': 'You do not have permission to delete this item'},
                status=status.HTTP_403_FORBIDDEN
            )

        item_name = instance.name
        self.perform_destroy(instance)
        return Response(
            {'message': f'Menu item "{item_name}" deleted successfully'},
            status=status.HTTP_204_NO_CONTENT
        )


# ─── Restaurant Menu ViewSet (public/customer) ────────────────────────────────

class RestaurantMenuViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request, restaurant_pk=None):
        if getattr(self, 'swagger_fake_view', False):
            return Response([])

        menu_items = MenuItem.objects.filter(
            restaurant_id=restaurant_pk,
            is_available=True,
        )
        serializer = MenuItemPublicSerializer(menu_items, many=True)
        return Response(serializer.data)


# ─── All Available Menu Items (customer home feed) ────────────────────────────

class AvailableMenuItemsViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        if getattr(self, 'swagger_fake_view', False):
            return Response([])

        menu_items = MenuItem.objects.filter(
            is_available=True,
            restaurant__is_open=True,
        ).select_related('restaurant', 'category')

        serializer = MenuItemPublicSerializer(menu_items, many=True)
        return Response(serializer.data)