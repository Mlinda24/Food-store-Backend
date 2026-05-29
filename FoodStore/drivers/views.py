from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db import transaction
from .models import DriverProfile, DeliveryAssignment
from .serializers import DriverProfileSerializer, DeliveryAssignmentSerializer, AvailableOrderSerializer
from orders.models import Order

class DriverViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = DriverProfileSerializer
    
    def get_queryset(self):
        return DriverProfile.objects.filter(user=self.request.user)
    
    @action(detail=False, methods=['get'])
    def profile(self, request):
        """Get or create driver profile for current user"""
        driver, created = DriverProfile.objects.get_or_create(user=request.user)
        serializer = DriverProfileSerializer(driver)
        return Response(serializer.data)
    
    @action(detail=False, methods=['patch'])
    def profile_status(self, request):
        """Update driver status (online/offline/busy)"""
        driver, _ = DriverProfile.objects.get_or_create(user=request.user)
        status_value = request.data.get('status')
        if status_value:
            driver.status = status_value
            driver.is_available = status_value == 'online'
            driver.save()
        serializer = DriverProfileSerializer(driver)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def location_update(self, request):
        """Update driver's current location"""
        driver, _ = DriverProfile.objects.get_or_create(user=request.user)
        driver.current_latitude = request.data.get('latitude')
        driver.current_longitude = request.data.get('longitude')
        driver.last_location_update = timezone.now()
        driver.save()
        return Response({'status': 'ok', 'message': 'Location updated'})


class DeliveryOrderViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def available(self, request):
        """Get orders available for delivery"""
        # Orders that are confirmed and paid but not yet assigned to a driver
        orders = Order.objects.filter(
            status='confirmed',
            payment_status='paid',
            delivery_assignment__isnull=True
        ).exclude(
            delivery_assignment__status__in=['accepted', 'picked_up', 'delivered']
        ).select_related('restaurant')
        
        serializer = AvailableOrderSerializer(orders, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def my(self, request):
        """Get deliveries assigned to current driver"""
        driver, _ = DriverProfile.objects.get_or_create(user=request.user)
        deliveries = DeliveryAssignment.objects.filter(driver=driver).select_related('order', 'order__restaurant')
        serializer = DeliveryAssignmentSerializer(deliveries, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def accept(self, request, pk=None):
        """Accept a delivery order"""
        try:
            order = Order.objects.get(id=pk)
        except Order.DoesNotExist:
            return Response({'error': 'Order not found'}, status=status.HTTP_404_NOT_FOUND)
        
        driver, _ = DriverProfile.objects.get_or_create(user=request.user)
        
        # Check if already assigned
        if DeliveryAssignment.objects.filter(order=order).exists():
            return Response({'error': 'Order already assigned'}, status=status.HTTP_400_BAD_REQUEST)
        
        with transaction.atomic():
            delivery = DeliveryAssignment.objects.create(
                order=order,
                driver=driver,
                status='accepted',
                delivery_fee=2000.00
            )
            delivery.accepted_at = timezone.now()
            delivery.save()
        
        serializer = DeliveryAssignmentSerializer(delivery)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['patch'])
    def status(self, request, pk=None):
        """Update delivery status (picked_up, delivered)"""
        try:
            delivery = DeliveryAssignment.objects.select_related('driver', 'order').get(id=pk)
        except DeliveryAssignment.DoesNotExist:
            return Response({'error': 'Delivery not found'}, status=status.HTTP_404_NOT_FOUND)
        
        new_status = request.data.get('status')
        
        if new_status == 'picked_up':
            delivery.status = 'picked_up'
            delivery.picked_up_at = timezone.now()
            delivery.save()
        elif new_status == 'delivered':
            delivery.status = 'delivered'
            delivery.delivered_at = timezone.now()
            
            # Update order status
            order = delivery.order
            order.status = 'delivered'
            order.save()
            
            # Update driver earnings
            driver = delivery.driver
            driver.total_deliveries += 1
            driver.total_earnings += delivery.delivery_fee
            driver.current_balance += delivery.delivery_fee
            driver.save()
        elif new_status == 'cancelled':
            delivery.status = 'cancelled'
            delivery.save()
        else:
            return Response({'error': 'Invalid status'}, status=status.HTTP_400_BAD_REQUEST)
        
        serializer = DeliveryAssignmentSerializer(delivery)
        return Response(serializer.data)