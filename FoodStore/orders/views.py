from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db.models import Sum
from .models import Cart, CartItem, Order, OrderItem
from .serializers import CartSerializer, OrderSerializer

# Try to import from restaurants
try:
    from restaurants.models import MenuItem, Restaurant
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
                status=status.HTTP_400_BAD_REQUEST
            )

        if RESTAURANTS_AVAILABLE:
            menu_item = get_object_or_404(MenuItem, id=menu_item_id)
            
            if not cart.restaurant:
                cart.restaurant = menu_item.restaurant
                cart.save()

            if cart.restaurant and cart.restaurant.id != menu_item.restaurant.id:
                return Response(
                    {'error': 'Cannot add items from different restaurants'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            cart_item, created = CartItem.objects.get_or_create(
                cart=cart,
                menu_item=menu_item,
                customization=customization,
                defaults={
                    'quantity': quantity,
                    'special_instructions': special_instructions
                }
            )
        else:
            # Fallback when restaurants app not available
            menu_item_name = request.data.get('menu_item_name', 'Item')
            cart_item, created = CartItem.objects.get_or_create(
                cart=cart,
                menu_item_id=menu_item_id,
                customization=customization,
                defaults={
                    'quantity': quantity,
                    'special_instructions': special_instructions
                }
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
                status=status.HTTP_400_BAD_REQUEST
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
                status=status.HTTP_400_BAD_REQUEST
            )

        cart_item = get_object_or_404(CartItem, id=cart_item_id, cart=cart)
        cart_item.delete()

        if not cart.items.exists():
            cart.restaurant = None
            cart.save()

        serializer = CartSerializer(cart)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def clear_cart(self, request):
        cart = self.get_cart(request)
        cart.items.all().delete()
        cart.restaurant = None
        cart.save()
        
        return Response(
            {'message': 'Cart cleared successfully'},
            status=status.HTTP_200_OK
        )


class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        
        if RESTAURANTS_AVAILABLE and hasattr(user, 'role') and user.role == 'restaurant':
            try:
                restaurant = Restaurant.objects.get(owner=user)
                return Order.objects.filter(restaurant=restaurant).order_by('-created')
            except Restaurant.DoesNotExist:
                return Order.objects.none()
        
        # For customers, show their own orders
        return Order.objects.filter(customer=user).order_by('-created')

    def create(self, request, *args, **kwargs):
        try:
            cart = Cart.objects.get(user=request.user)
        except Cart.DoesNotExist:
            return Response(
                {'error': 'Cart not found'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not cart.items.exists():
            return Response(
                {'error': 'Cart is empty'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if RESTAURANTS_AVAILABLE and not cart.restaurant:
            return Response(
                {'error': 'No restaurant selected'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Calculate total price
        if RESTAURANTS_AVAILABLE:
            total_price = sum(item.menu_item.price * item.quantity for item in cart.items.all())
        else:
            total_price = sum(item.menu_item_price * item.quantity for item in cart.items.all())

        delivery_address = request.data.get('delivery_address', '')
        if not delivery_address:
            return Response(
                {'error': 'Delivery address is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Create order
        order_data = {
            'customer': request.user,
            'total_price': total_price,
            'delivery_address': delivery_address,
            'note': request.data.get('note', ''),
        }
        
        if RESTAURANTS_AVAILABLE:
            order_data['restaurant'] = cart.restaurant
        
        order = Order.objects.create(**order_data)

        # Create order items from cart items
        for cart_item in cart.items.all():
            OrderItem.objects.create(
                order=order,
                menu_item=cart_item.menu_item if RESTAURANTS_AVAILABLE else None,
                menu_item_id=cart_item.menu_item_id,
                menu_item_name=cart_item.menu_item_name if hasattr(cart_item, 'menu_item_name') else f"Item {cart_item.menu_item_id}",
                quantity=cart_item.quantity,
                price=cart_item.menu_item_price if hasattr(cart_item, 'menu_item_price') else 0,
                customization=cart_item.customization,
                special_instructions=cart_item.special_instructions
            )

        # Clear the cart
        cart.items.all().delete()
        if RESTAURANTS_AVAILABLE:
            cart.restaurant = None
            cart.save()

        serializer = self.get_serializer(order)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['patch'])
    def update_status(self, request, pk=None):
        order = self.get_object()
        new_status = request.data.get('status')
        
        valid_statuses = ['pending', 'confirmed', 'preparing', 'ready', 'delivered', 'cancelled']
        if new_status not in valid_statuses:
            return Response(
                {'error': f'Invalid status. Must be one of: {valid_statuses}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        order.status = new_status
        order.save()
        
        serializer = self.get_serializer(order)
        return Response(serializer.data)