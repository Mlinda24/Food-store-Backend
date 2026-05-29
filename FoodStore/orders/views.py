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
            # IMPORTANT: always start as pending / unpaid
            # status only moves to 'confirmed' after payment AND restaurant confirmation
            'status': 'pending',
            'payment_status': 'unpaid',
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

        # Clear cart after order created
        cart.items.all().delete()
        cart.restaurant_id = None
        cart.save()

        serializer = self.get_serializer(order)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['patch'])
    def update_status(self, request, pk=None):
        order = self.get_object()
        new_status = request.data.get('status')
        old_status = order.status

        valid_statuses = [
            'pending', 'confirmed', 'preparing',
            'ready', 'picked_up', 'delivered', 'cancelled',
        ]
        if new_status not in valid_statuses:
            return Response(
                {'error': f'Invalid status. Must be one of: {valid_statuses}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ──────────────────────────────────────────────────────────────────────
        # PAYMENT GUARD: only allow moving past 'pending' if the order
        # has been paid. The webhook sets payment_status='paid'
        # ──────────────────────────────────────────────────────────────────────
        paid_statuses = {'confirmed', 'preparing', 'ready', 'picked_up', 'delivered'}
        if new_status in paid_statuses:
            order_payment_status = getattr(order, 'payment_status', None)
            if order_payment_status != 'paid':
                return Response(
                    {
                        'error': (
                            f"Cannot set status to '{new_status}' — "
                            "order has not been paid yet."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # ──────────────────────────────────────────────────────────────────────
        # CREDIT WALLET WHEN ORDER IS CONFIRMED BY RESTAURANT
        # This ensures restaurant only gets paid for orders they confirm
        # ──────────────────────────────────────────────────────────────────────
        if new_status == 'confirmed' and old_status != 'confirmed':
            success = self._credit_wallet_on_confirmation(order)
            if not success:
                return Response(
                    {'error': 'Failed to credit wallet. Please try again.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        order.status = new_status
        order.save()

        # Send notification to customer about status change
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
            logger.error(f'Notification failed: {e}')

        serializer = self.get_serializer(order)
        return Response({
            'status': 'success',
            'order_status': order.status,
            'payment_status': order.payment_status,
            'message': f'Order status updated to {new_status}',
            'data': serializer.data
        })

    def _credit_wallet_on_confirmation(self, order):
        """Credit restaurant wallet when order is confirmed by restaurant owner"""
        try:
            from payments.models import Payment
            from decimal import Decimal
            
            # Get the payment for this order
            try:
                payment = Payment.objects.get(order=order)
            except Payment.DoesNotExist:
                logger.warning(f'No payment found for order #{order.id}')
                return False
            
            # Check if payment is completed and not yet distributed
            if payment.status == 'completed' and not payment.distributed_to_wallets:
                # Get the restaurant
                restaurant = order.restaurant
                if not restaurant:
                    logger.warning(f'No restaurant found for order #{order.id}')
                    return False
                
                # Get or create wallet
                wallet, created = RestaurantWallet.objects.get_or_create(restaurant=restaurant)
                if created:
                    logger.info(f'Created new wallet for {restaurant.name}')
                
                # Calculate amounts
                total_amount = Decimal(str(payment.amount))
                platform_fee_percent = Decimal('10.00')
                platform_fee = (total_amount * platform_fee_percent) / Decimal('100')
                restaurant_amount = payment.pending_restaurant_amount
                
                if restaurant_amount == 0:
                    restaurant_amount = total_amount - platform_fee
                
                # Credit the wallet
                wallet.balance += restaurant_amount
                wallet.total_earned += restaurant_amount
                wallet.save(update_fields=['balance', 'total_earned'])
                
                # Create transaction record
                WalletTransaction.objects.create(
                    wallet=wallet,
                    transaction_type='credit',
                    amount=restaurant_amount,
                    status='successful',
                    description=f'Payment from Order #{order.id} - {order.customer.username} (confirmed)',
                )
                
                # Mark payment as distributed
                payment.distributed_to_wallets = True
                payment.distributed_at = timezone.now()
                payment.restaurant_amount = restaurant_amount
                payment.save()
                
                logger.info(f'Wallet credited for order #{order.id}: MK{restaurant_amount:,.2f}')
                
                # Send notification to restaurant
                try:
                    from notifications.services import NotificationService
                    NotificationService.send_notification(
                        user=restaurant.owner,
                        notification_type='wallet',
                        title='Wallet Credited',
                        message=f'Order #{order.id} confirmed. MK{restaurant_amount:,.2f} credited to your wallet.',
                        data={'order_id': str(order.id), 'amount': str(restaurant_amount)},
                        send_email=True,
                        send_sms=False,
                        priority='high',
                    )
                except Exception as e:
                    logger.error(f'Notification failed: {e}')
                
                return True
            else:
                logger.info(f'Payment for order #{order.id} not ready for distribution: status={payment.status}, distributed={payment.distributed_to_wallets}')
                return False
                
        except Exception as e:
            logger.error(f'Error crediting wallet for order #{order.id}: {e}', exc_info=True)
            return False

    @action(detail=False, methods=['get'])
    def my_orders(self, request):
        """Get orders for the current user (customer)"""
        orders = Order.objects.filter(customer=request.user).order_by('-created')
        serializer = self.get_serializer(orders, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def restaurant_orders(self, request):
        """Get orders for the restaurant owner"""
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
        """Get pending orders for restaurant owner"""
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
                payment_status='paid'
            ).order_by('-created')
            serializer = self.get_serializer(orders, many=True)
            return Response(serializer.data)
        except Restaurant.DoesNotExist:
            return Response(
                {'error': 'No restaurant found for this user'},
                status=status.HTTP_404_NOT_FOUND,
            )

    @action(detail=False, methods=['get'])
    def confirmed_orders(self, request):
        """Get confirmed orders for restaurant owner"""
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
                status='confirmed',
                payment_status='paid'
            ).order_by('-created')
            serializer = self.get_serializer(orders, many=True)
            return Response(serializer.data)
        except Restaurant.DoesNotExist:
            return Response(
                {'error': 'No restaurant found for this user'},
                status=status.HTTP_404_NOT_FOUND,
            )