from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.utils import timezone
import logging
from .models import Cart, CartItem, Order, OrderItem
from .serializers import CartSerializer, OrderSerializer

logger = logging.getLogger(__name__)

try:
    from restaurants.models import MenuItem, Restaurant, RestaurantWallet, WalletTransaction
    from decimal import Decimal
    RESTAURANTS_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    RESTAURANTS_AVAILABLE = False


class CartViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def get_cart(self, request):
        cart, created = Cart.objects.get_or_create(user=request.user)
        return cart

    def list(self, request):
        cart = self.get_cart(request)
        serializer = CartSerializer(cart)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def add_item(self, request):
        cart = self.get_cart(request)
        menu_item_id = request.data.get('menu_item_id')
        quantity = int(request.data.get('quantity', 1))
        customization = request.data.get('customization', {})
        special_instructions = request.data.get('special_instructions', '')

        if not menu_item_id:
            return Response(
                {'error': 'menu_item_id is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if RESTAURANTS_AVAILABLE:
            menu_item = get_object_or_404(MenuItem, id=menu_item_id)

            if not cart.restaurant_id:
                cart.restaurant_id = menu_item.restaurant.id
                cart.restaurant_name = menu_item.restaurant.name
                cart.save()

            if cart.restaurant_id and cart.restaurant_id != menu_item.restaurant.id:
                return Response(
                    {'error': 'Cannot add items from different restaurants'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            cart_item, created = CartItem.objects.get_or_create(
                cart=cart,
                menu_item_id=menu_item.id,
                customization=customization,
                defaults={
                    'quantity': quantity,
                    'menu_item_name': menu_item.name,
                    'menu_item_price': menu_item.price,
                    'special_instructions': special_instructions,
                },
            )
        else:
            cart_item, created = CartItem.objects.get_or_create(
                cart=cart,
                menu_item_id=menu_item_id,
                customization=customization,
                defaults={
                    'quantity': quantity,
                    'menu_item_name': f'Item {menu_item_id}',
                    'menu_item_price': 0,
                    'special_instructions': special_instructions,
                },
            )

        if not created:
            cart_item.quantity += quantity
            cart_item.save()

        serializer = CartSerializer(cart)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['patch'])
    def update_item(self, request):
        cart = self.get_cart(request)
        cart_item_id = request.data.get('cart_item_id')
        quantity = int(request.data.get('quantity', 1))

        if not cart_item_id:
            return Response(
                {'error': 'cart_item_id is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cart_item = get_object_or_404(CartItem, id=cart_item_id, cart=cart)

        if quantity <= 0:
            cart_item.delete()
        else:
            cart_item.quantity = quantity
            cart_item.save()

        serializer = CartSerializer(cart)
        return Response(serializer.data)

    @action(detail=False, methods=['delete'])
    def remove_item(self, request):
        cart = self.get_cart(request)
        cart_item_id = request.data.get('cart_item_id')

        if not cart_item_id:
            return Response(
                {'error': 'cart_item_id is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cart_item = get_object_or_404(CartItem, id=cart_item_id, cart=cart)
        cart_item.delete()

        if not cart.items.exists():
            cart.restaurant_id = None
            cart.save()

        serializer = CartSerializer(cart)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def clear_cart(self, request):
        cart = self.get_cart(request)
        cart.items.all().delete()
        cart.restaurant_id = None
        cart.save()
        return Response(
            {'message': 'Cart cleared successfully'},
            status=status.HTTP_200_OK,
        )


class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Order.objects.none()

        user = self.request.user

        if RESTAURANTS_AVAILABLE and hasattr(user, 'role') and user.role == 'restaurant':
            try:
                restaurant = Restaurant.objects.get(owner=user)
                return Order.objects.filter(restaurant_id=restaurant.id).order_by('-created')
            except Restaurant.DoesNotExist:
                return Order.objects.none()

        return Order.objects.filter(customer=user).order_by('-created')

    def create(self, request, *args, **kwargs):
        cart, _ = Cart.objects.get_or_create(user=request.user)

        restaurant_id = cart.restaurant_id or request.data.get('restaurant_id')

        if not cart.items.exists():
            return Response(
                {'error': 'Cart is empty. Please add items before placing an order.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if RESTAURANTS_AVAILABLE and not restaurant_id:
            return Response(
                {'error': 'No restaurant selected'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not cart.restaurant_id and restaurant_id:
            cart.restaurant_id = int(restaurant_id)
            cart.save()

        delivery_address = request.data.get('delivery_address', '').strip()
        if not delivery_address:
            return Response(
                {'error': 'Delivery address is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        total_price = sum(
            item.menu_item_price * item.quantity
            for item in cart.items.all()
        )

        order_data = {
            'customer': request.user,
            'total_price': total_price,
            'delivery_address': delivery_address,
            'note': request.data.get('note', ''),
            'status': 'pending',
            'payment_status': 'pending',
        }

        if RESTAURANTS_AVAILABLE:
            order_data['restaurant_id'] = cart.restaurant_id or int(restaurant_id)

        order = Order.objects.create(**order_data)

        for cart_item in cart.items.all():
            OrderItem.objects.create(
                order=order,
                menu_item_id=cart_item.menu_item_id,
                menu_item_name=cart_item.menu_item_name,
                menu_item_price=cart_item.menu_item_price,
                quantity=cart_item.quantity,
                price=cart_item.menu_item_price * cart_item.quantity,
                customization=cart_item.customization,
                special_instructions=cart_item.special_instructions,
            )

        cart.items.all().delete()
        cart.restaurant_id = None
        cart.save()

        serializer = self.get_serializer(order)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['patch'])
    def update_status(self, request, pk=None):
        try:
            order = self.get_object()
        except Exception as e:
            return Response(
                {'error': f'Order not found: {str(e)}'},
                status=status.HTTP_404_NOT_FOUND
            )

        new_status = request.data.get('status')
        if not new_status:
            return Response(
                {'error': 'Status is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        valid_statuses = [
            'pending', 'confirmed', 'preparing',
            'ready', 'picked_up', 'delivered', 'cancelled',
        ]
        if new_status not in valid_statuses:
            return Response(
                {'error': f'Invalid status. Must be one of: {valid_statuses}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        old_status = order.status

        if old_status == 'cancelled' and new_status != 'cancelled':
            return Response(
                {
                    'error': 'Cannot update a cancelled order.',
                    'current_status': old_status,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        order.status = new_status
        order.save()

        logger.info(f'Order #{order.id} status updated: {old_status} → {new_status}')

        # Credit wallet ONLY when restaurant confirms — never on decline
        if new_status == 'confirmed' and old_status != 'confirmed':
            logger.info(f'Order #{order.id} confirmed — crediting wallet')
            try:
                from payments.views import _credit_wallet_on_order_confirmation
                _credit_wallet_on_order_confirmation(order)
            except Exception as e:
                logger.error(f'Wallet credit failed for order #{order.id}: {e}')

        try:
            from notifications.services import NotificationService
            NotificationService.send_notification(
                user=order.customer,
                notification_type='order',
                title=f'Order {new_status.capitalize()}',
                message=f'Your order #{order.id} status has been updated to {new_status}.',
                data={'order_id': str(order.id), 'status': new_status},
                send_email=False,
                send_sms=False,
                priority='high',
            )
        except Exception as e:
            logger.error(f'Notification failed for order #{order.id}: {e}')

        serializer = self.get_serializer(order)
        return Response({
            'success': True,
            'message': f'Order status updated to {new_status}',
            'order': serializer.data
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'])
    def my_orders(self, request):
        orders = Order.objects.filter(customer=request.user).order_by('-created')
        serializer = self.get_serializer(orders, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def restaurant_orders(self, request):
        if not RESTAURANTS_AVAILABLE:
            return Response(
                {'error': 'Restaurants module not available'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not hasattr(request.user, 'role') or request.user.role != 'restaurant':
            return Response(
                {'error': 'Only restaurant owners can access this endpoint'},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            restaurant = Restaurant.objects.get(owner=request.user)
            orders = Order.objects.filter(restaurant_id=restaurant.id).order_by('-created')
            serializer = self.get_serializer(orders, many=True)
            return Response(serializer.data)
        except Restaurant.DoesNotExist:
            return Response(
                {'error': 'No restaurant found for this user'},
                status=status.HTTP_404_NOT_FOUND,
            )

    @action(detail=False, methods=['get'])
    def pending_orders(self, request):
        if not RESTAURANTS_AVAILABLE:
            return Response(
                {'error': 'Restaurants module not available'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not hasattr(request.user, 'role') or request.user.role != 'restaurant':
            return Response(
                {'error': 'Only restaurant owners can access this endpoint'},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            restaurant = Restaurant.objects.get(owner=request.user)
            orders = Order.objects.filter(
                restaurant_id=restaurant.id,
                status='pending',
            ).order_by('-created')
            serializer = self.get_serializer(orders, many=True)
            return Response(serializer.data)
        except Restaurant.DoesNotExist:
            return Response(
                {'error': 'No restaurant found for this user'},
                status=status.HTTP_404_NOT_FOUND,
            )