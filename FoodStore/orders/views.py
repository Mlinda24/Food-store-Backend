from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from .models import Cart, CartItem, Order, OrderItem
from .serializers import CartSerializer, OrderSerializer

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

            if not cart.restaurant_id:
                cart.restaurant_id = menu_item.restaurant.id  # ← fixed
                cart.save()

            if cart.restaurant_id and cart.restaurant_id != menu_item.restaurant.id:
                return Response(
                    {'error': 'Cannot add items from different restaurants'},
                    status=status.HTTP_400_BAD_REQUEST
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
                }
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
            status=status.HTTP_200_OK
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
                return Order.objects.filter(restaurant=restaurant).order_by('-created')
            except Restaurant.DoesNotExist:
                return Order.objects.none()

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

        if RESTAURANTS_AVAILABLE and not cart.restaurant_id:
            return Response(
                {'error': 'No restaurant selected'},
                status=status.HTTP_400_BAD_REQUEST
            )

        total_price = sum(
            item.menu_item_price * item.quantity
            for item in cart.items.all()
        )

        delivery_address = request.data.get('delivery_address', '')
        if not delivery_address:
            return Response(
                {'error': 'Delivery address is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        order_data = {
            'customer': request.user,
            'total_price': total_price,
            'delivery_address': delivery_address,
            'note': request.data.get('note', ''),
        }

        if RESTAURANTS_AVAILABLE:
            order_data['restaurant_id'] = cart.restaurant_id

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
                special_instructions=cart_item.special_instructions
            )

        cart.items.all().delete()
        cart.restaurant_id = None
        cart.save()

        serializer = self.get_serializer(order)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['patch'])
    def update_status(self, request, pk=None):
        order = self.get_object()
        new_status = request.data.get('status')

        valid_statuses = [
            'pending', 'confirmed', 'preparing',
            'ready', 'picked_up', 'delivered', 'cancelled'
        ]
        if new_status not in valid_statuses:
            return Response(
                {'error': f'Invalid status. Must be one of: {valid_statuses}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        order.status = new_status
        order.save()

        serializer = self.get_serializer(order)
        return Response(serializer.data)