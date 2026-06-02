from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.db.models import Sum, Count, Q
from datetime import timedelta
from .models import DriverProfile, DeliveryAssignment
from .serializers import (
    DriverProfileSerializer, 
    DeliveryAssignmentSerializer, 
    AvailableOrderSerializer
)
from orders.models import Order
import logging

logger = logging.getLogger(__name__)


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
    def update_profile(self, request):
        """Update driver profile"""
        driver, _ = DriverProfile.objects.get_or_create(user=request.user)
        
        # Update fields
        if 'phone_number' in request.data:
            driver.phone_number = request.data['phone_number']
        if 'vehicle_type' in request.data:
            driver.vehicle_type = request.data['vehicle_type']
        if 'vehicle_registration' in request.data:
            driver.vehicle_registration = request.data['vehicle_registration']
        if 'vehicle_model' in request.data:
            driver.vehicle_model = request.data['vehicle_model']
        if 'vehicle_color' in request.data:
            driver.vehicle_color = request.data['vehicle_color']
        if 'license_number' in request.data:
            driver.license_number = request.data['license_number']
        
        driver.save()
        serializer = DriverProfileSerializer(driver)
        return Response(serializer.data)
    
    @action(detail=False, methods=['patch'])
    def profile_status(self, request):
        """Update driver status (online/offline/busy)"""
        driver, _ = DriverProfile.objects.get_or_create(user=request.user)
        status_value = request.data.get('status')
        
        if status_value:
            if status_value not in ['offline', 'online', 'busy']:
                return Response(
                    {'error': 'Invalid status. Must be offline, online, or busy'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            driver.status = status_value
            driver.is_available = status_value == 'online'
            driver.save()
            logger.info(f'Driver {driver.user.username} status updated to {status_value}')
        
        serializer = DriverProfileSerializer(driver)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def location_update(self, request):
        """Update driver's current location"""
        driver, _ = DriverProfile.objects.get_or_create(user=request.user)
        
        latitude = request.data.get('latitude')
        longitude = request.data.get('longitude')
        
        if latitude is not None:
            driver.current_latitude = latitude
        if longitude is not None:
            driver.current_longitude = longitude
        
        driver.last_location_update = timezone.now()
        driver.save()
        
        return Response({
            'status': 'success', 
            'message': 'Location updated',
            'latitude': float(driver.current_latitude) if driver.current_latitude else None,
            'longitude': float(driver.current_longitude) if driver.current_longitude else None
        })
    
    @action(detail=False, methods=['get'])
    def earnings(self, request):
        """Get earnings summary for driver"""
        driver, _ = DriverProfile.objects.get_or_create(user=request.user)
        now = timezone.now()
        today = now.date()
        week_start = now - timedelta(days=now.weekday())
        
        # Today's deliveries
        today_deliveries = DeliveryAssignment.objects.filter(
            driver=driver,
            delivered_at__date=today,
            status='delivered'
        )
        today_earnings = sum(float(d.delivery_fee) for d in today_deliveries)
        
        # Week earnings
        week_deliveries = DeliveryAssignment.objects.filter(
            driver=driver,
            delivered_at__gte=week_start,
            status='delivered'
        )
        week_earnings = sum(float(d.delivery_fee) for d in week_deliveries)
        
        # Month earnings
        month_deliveries = DeliveryAssignment.objects.filter(
            driver=driver,
            delivered_at__year=now.year,
            delivered_at__month=now.month,
            status='delivered'
        )
        month_earnings = sum(float(d.delivery_fee) for d in month_deliveries)
        
        # Total
        all_deliveries = DeliveryAssignment.objects.filter(driver=driver, status='delivered')
        total_earnings = sum(float(d.delivery_fee) for d in all_deliveries)
        
        return Response({
            'today_earnings': float(today_earnings),
            'week_earnings': float(week_earnings),
            'month_earnings': float(month_earnings),
            'total_earnings': float(total_earnings),
            'total_deliveries': all_deliveries.count(),
            'rating': float(driver.rating),
        })
    
    @action(detail=False, methods=['get'])
    def delivery_history(self, request):
        """Get delivery history for driver"""
        driver, _ = DriverProfile.objects.get_or_create(user=request.user)
        deliveries = DeliveryAssignment.objects.filter(driver=driver).order_by('-created_at')
        serializer = DeliveryAssignmentSerializer(deliveries, many=True)
        return Response({
            'count': deliveries.count(),
            'deliveries': serializer.data
        })


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
        ).select_related('restaurant').order_by('-created')
        
        # Format response for driver app
        available_orders = []
        for order in orders:
            available_orders.append({
                'id': order.id,
                'restaurant_name': order.restaurant.name if order.restaurant else 'Restaurant',
                'restaurant_address': order.restaurant.address if order.restaurant else '',
                'customer_name': order.customer.username,
                'customer_phone': order.customer.phone if order.customer.phone else '',
                'delivery_address': order.delivery_address,
                'delivery_fee': float(getattr(order, 'delivery_fee', 2000.00)),
                'distance': '2.5 km',  # Calculate based on location
                'estimated_time': '25-35 min',
                'items_summary': f"{order.items.count()} items",
                'status': 'available',
                'created': order.created.isoformat(),
            })
        
        return Response(available_orders)
    
    @action(detail=False, methods=['get'])
    def my(self, request):
        """Get deliveries assigned to current driver"""
        driver, _ = DriverProfile.objects.get_or_create(user=request.user)
        deliveries = DeliveryAssignment.objects.filter(
            driver=driver
        ).select_related('order', 'order__restaurant', 'order__customer').order_by('-created_at')
        
        serializer = DeliveryAssignmentSerializer(deliveries, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def active(self, request):
        """Get active delivery for current driver"""
        driver, _ = DriverProfile.objects.get_or_create(user=request.user)
        try:
            active_delivery = DeliveryAssignment.objects.get(
                driver=driver,
                status__in=['accepted', 'picked_up']
            )
            serializer = DeliveryAssignmentSerializer(active_delivery)
            return Response(serializer.data)
        except DeliveryAssignment.DoesNotExist:
            return Response({})
    
    @action(detail=True, methods=['post'])
    def accept(self, request, pk=None):
        """Accept a delivery order"""
        try:
            order = Order.objects.get(id=pk)
        except Order.DoesNotExist:
            return Response({'error': 'Order not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Check if order is eligible for delivery
        if order.status != 'confirmed':
            return Response(
                {'error': f'Order status is {order.status}, cannot accept for delivery'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if order.payment_status != 'paid':
            return Response(
                {'error': 'Order has not been paid yet'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        driver, _ = DriverProfile.objects.get_or_create(user=request.user)
        
        # Check if driver is available
        if driver.status != 'online':
            return Response(
                {'error': 'Driver is not online. Please go online first.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if already assigned
        if DeliveryAssignment.objects.filter(order=order).exists():
            return Response(
                {'error': 'Order already assigned to a driver'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        with transaction.atomic():
            delivery = DeliveryAssignment.objects.create(
                order=order,
                driver=driver,
                status='accepted',
                delivery_fee=getattr(order, 'delivery_fee', 2000.00)
            )
            delivery.accepted_at = timezone.now()
            delivery.save()
            
            # Update driver status to busy
            driver.status = 'busy'
            driver.is_available = False
            driver.save()
        
        serializer = DeliveryAssignmentSerializer(delivery)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['post'])
    def decline(self, request, pk=None):
        """Decline a delivery order"""
        try:
            order = Order.objects.get(id=pk)
        except Order.DoesNotExist:
            return Response({'error': 'Order not found'}, status=status.HTTP_404_NOT_FOUND)
        
        driver, _ = DriverProfile.objects.get_or_create(user=request.user)
        
        # Create a declined record (optional, for history)
        delivery = DeliveryAssignment.objects.create(
            order=order,
            driver=driver,
            status='cancelled',
            delivery_fee=getattr(order, 'delivery_fee', 2000.00)
        )
        
        return Response({'status': 'success', 'message': 'Order declined'})
    
    @action(detail=True, methods=['patch'])
    def status(self, request, pk=None):
        """Update delivery status (picked_up, delivered)"""
        try:
            delivery = DeliveryAssignment.objects.select_related('driver', 'order', 'order__customer').get(id=pk)
        except DeliveryAssignment.DoesNotExist:
            return Response({'error': 'Delivery not found'}, status=status.HTTP_404_NOT_FOUND)
        
        new_status = request.data.get('status')
        
        if new_status not in ['picked_up', 'delivered', 'cancelled']:
            return Response(
                {'error': 'Invalid status. Must be picked_up, delivered, or cancelled'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if driver owns this delivery
        driver = DriverProfile.objects.get(user=request.user)
        if delivery.driver.id != driver.id:
            return Response(
                {'error': 'You are not authorized to update this delivery'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if new_status == 'picked_up':
            delivery.status = 'picked_up'
            delivery.picked_up_at = timezone.now()
            delivery.save()
            
        elif new_status == 'delivered':
            delivery.status = 'delivered'
            delivery.delivered_at = timezone.now()
            delivery.save()
            
            # Update order status
            order = delivery.order
            order.status = 'delivered'
            order.save()
            
            # Update driver earnings
            driver = delivery.driver
            driver.total_deliveries += 1
            driver.total_earnings += delivery.delivery_fee
            driver.current_balance += delivery.delivery_fee
            driver.status = 'online'
            driver.is_available = True
            driver.save()
            
            logger.info(f'Driver {driver.user.username} earned MK{delivery.delivery_fee} for delivery #{delivery.id}')
            
        elif new_status == 'cancelled':
            delivery.status = 'cancelled'
            delivery.save()
            
            # Set driver back to online
            driver = delivery.driver
            driver.status = 'online'
            driver.is_available = True
            driver.save()
        
        serializer = DeliveryAssignmentSerializer(delivery)
        return Response(serializer.data)