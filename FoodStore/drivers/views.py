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
    DeliveryAssignmentSerializer
)
from orders.models import Order
import logging

logger = logging.getLogger(__name__)


class DriverViewSet(viewsets.GenericViewSet):
    """Driver profile and earnings management"""
    permission_classes = [IsAuthenticated]
    serializer_class = DriverProfileSerializer
    
    def get_queryset(self):
        return DriverProfile.objects.filter(user=self.request.user)
    
    @action(detail=False, methods=['get'])
    def profile(self, request):
        driver, created = DriverProfile.objects.get_or_create(user=request.user)
        serializer = DriverProfileSerializer(driver)
        return Response(serializer.data)
    
    @action(detail=False, methods=['patch'])
    def update_profile(self, request):
        driver, _ = DriverProfile.objects.get_or_create(user=request.user)
        updatable_fields = ['phone_number', 'vehicle_type', 'vehicle_registration', 
                           'vehicle_model', 'vehicle_color', 'license_number', 
                           'license_expiry_date', 'alternative_phone']
        for field in updatable_fields:
            if field in request.data:
                setattr(driver, field, request.data[field])
        driver.save()
        serializer = DriverProfileSerializer(driver)
        return Response(serializer.data)
    
    @action(detail=False, methods=['patch'])
    def profile_status(self, request):
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
        driver, _ = DriverProfile.objects.get_or_create(user=request.user)
        now = timezone.now()
        today = now.date()
        week_start = now - timedelta(days=now.weekday())
        
        today_deliveries = DeliveryAssignment.objects.filter(
            driver=driver, delivered_at__date=today, status='delivered'
        )
        today_earnings = sum(float(d.delivery_fee) for d in today_deliveries)
        
        week_deliveries = DeliveryAssignment.objects.filter(
            driver=driver, delivered_at__gte=week_start, status='delivered'
        )
        week_earnings = sum(float(d.delivery_fee) for d in week_deliveries)
        
        month_deliveries = DeliveryAssignment.objects.filter(
            driver=driver,
            delivered_at__year=now.year,
            delivered_at__month=now.month,
            status='delivered'
        )
        month_earnings = sum(float(d.delivery_fee) for d in month_deliveries)
        
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
        driver, _ = DriverProfile.objects.get_or_create(user=request.user)
        deliveries = DeliveryAssignment.objects.filter(driver=driver).order_by('-created_at')
        serializer = DeliveryAssignmentSerializer(deliveries, many=True)
        return Response({
            'count': deliveries.count(),
            'deliveries': serializer.data
        })


class DeliveryOrderViewSet(viewsets.GenericViewSet):
    """Delivery order management for drivers"""
    permission_classes = [IsAuthenticated]
    queryset = Order.objects.all()  
    
    @action(detail=False, methods=['get'])
    def available(self, request):
        orders = Order.objects.filter(
        status='ready',
        ).filter(
        Q(delivery_assignment__isnull=True) |
        Q(delivery_assignment__status='cancelled')
        ).order_by('-created')

        available_orders = []
        for order in orders:
            restaurant_name = "Restaurant"
            restaurant_address = ""
            try:
                if hasattr(order, 'restaurant') and order.restaurant:
                    restaurant_name = order.restaurant.name
                    restaurant_address = order.restaurant.address
                elif hasattr(order, 'restaurant_id') and order.restaurant_id:
                    from restaurants.models import Restaurant
                    restaurant = Restaurant.objects.filter(id=order.restaurant_id).first()
                    if restaurant:
                        restaurant_name = restaurant.name
                        restaurant_address = restaurant.address
            except:
                pass

            # Get order items summary
            items_summary = ""
            try:
                if hasattr(order, 'items') and order.items.exists():
                    item_count = order.items.count()
                    items_summary = f"{item_count} item{'s' if item_count > 1 else ''}"
                else:
                    items_summary = "Food items"
            except:
                items_summary = "Food items"

            available_orders.append({
                'id': str(order.id),
                'restaurant_name': restaurant_name,
                'restaurant_address': restaurant_address,
                'customer_name': order.customer.username if order.customer else 'Customer',
                'customer_phone': order.customer.phone if order.customer and order.customer.phone else '',
                'delivery_address': order.delivery_address,
                'delivery_fee': float(getattr(order, 'delivery_fee', 2000.00)),
                'distance': '2.5 km',
                'estimated_time': '25-35 min',
                'items': items_summary,
                'status': 'available',
                'order_status': order.status,  # This will be 'ready'
                'created': order.created.isoformat() if hasattr(order, 'created') else timezone.now().isoformat(),
            })

        logger.info(f'Driver available orders: {len(available_orders)} ready orders found')
        return Response(available_orders)
    
    @action(detail=False, methods=['get'])
    def my(self, request):
        driver, _ = DriverProfile.objects.get_or_create(user=request.user)
        deliveries = DeliveryAssignment.objects.filter(
            driver=driver
        ).select_related('order').order_by('-created_at')
        
        result = []
        for delivery in deliveries:
            order = delivery.order
            result.append({
                'id': str(delivery.id),
                'order_id': str(order.id),
                'restaurant_name': getattr(order, 'restaurant_name', 'Restaurant'),
                'customer_name': order.customer.username if order.customer else 'Customer',
                'customer_phone': order.customer.phone if order.customer and order.customer.phone else '',
                'delivery_address': order.delivery_address,
                'status': delivery.status,
                'delivery_fee': float(delivery.delivery_fee),
                'accepted_at': delivery.accepted_at.isoformat() if delivery.accepted_at else None,
                'picked_up_at': delivery.picked_up_at.isoformat() if delivery.picked_up_at else None,
                'delivered_at': delivery.delivered_at.isoformat() if delivery.delivered_at else None,
                'created_at': delivery.created_at.isoformat(),
            })
        
        return Response(result)
    
    @action(detail=False, methods=['get'])
    def active(self, request):
        driver, _ = DriverProfile.objects.get_or_create(user=request.user)
        try:
            active_delivery = DeliveryAssignment.objects.filter(
                driver=driver,
                status__in=['accepted', 'picked_up']
            ).first()
            order = active_delivery.order
            return Response({
                'id': str(active_delivery.id),
                'order_id': str(order.id),
                'restaurant_name': getattr(order, 'restaurant_name', 'Restaurant'),
                'restaurant_address': getattr(order, 'delivery_address', ''),
                'customer_name': order.customer.username if order.customer else 'Customer',
                'customer_phone': order.customer.phone if order.customer and order.customer.phone else '',
                'delivery_address': order.delivery_address,
                'status': active_delivery.status,
                'delivery_fee': float(active_delivery.delivery_fee),
                'accepted_at': active_delivery.accepted_at.isoformat() if active_delivery.accepted_at else None,
                'picked_up_at': active_delivery.picked_up_at.isoformat() if active_delivery.picked_up_at else None,
                'items_summary': f"{order.items.count()} items" if hasattr(order, 'items') else "Food items",
            })
        except DeliveryAssignment.DoesNotExist:
            return Response({})
    
    @action(detail=True, methods=['post'])
    def accept(self, request, pk=None):
        try:
            order = Order.objects.get(id=pk)
        except Order.DoesNotExist:
            return Response({'error': 'Order not found'}, status=status.HTTP_404_NOT_FOUND)
        
        
        if order.payment_status != 'paid':
            return Response(
                {'error': 'Order has not been paid yet'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        driver, _ = DriverProfile.objects.get_or_create(user=request.user)
        
        if driver.status != 'online':
            return Response(
                {'error': 'Driver is not online. Please go online first.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if already assigned
        if DeliveryAssignment.objects.filter(order=order).exclude(status='cancelled').exists():
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
            
            # Update driver status
            driver.status = 'busy'
            driver.is_available = False
            driver.save()
            
            order.status = 'driver_assigned'
            order.driver_id = driver.user.id
            order.driver_name = driver.user.get_full_name() or driver.user.username
            order.driver_assigned_at = timezone.now()
            order.driver_accepted_at = timezone.now()
            order.save()
            
            logger.info(f'Driver {driver.user.username} accepted order #{order.id}')
        
        return Response({
            'success': True,
            'id': str(delivery.id),
            'order_id': str(order.id),
            'status': delivery.status,
            'message': 'Order accepted successfully'
        }, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['post'])
    def decline(self, request, pk=None):
        try:
            order = Order.objects.get(id=pk)
        except Order.DoesNotExist:
            return Response({'error': 'Order not found'}, status=status.HTTP_404_NOT_FOUND)
        logger.info(f'Driver declined order #{order.id}')
        return Response({'success': True, 'message': 'Order declined'})
    
    @action(detail=True, methods=['patch'])
    def status(self, request, pk=None):
        try:
            delivery = DeliveryAssignment.objects.select_related('driver', 'order').get(id=pk)
        except DeliveryAssignment.DoesNotExist:
            return Response({'error': 'Delivery not found'}, status=status.HTTP_404_NOT_FOUND)
        
        new_status = request.data.get('status')
        
        if new_status not in ['picked_up', 'delivered', 'cancelled']:
            return Response(
                {'error': 'Invalid status. Must be picked_up, delivered, or cancelled'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        driver = DriverProfile.objects.get(user=request.user)
        if delivery.driver.id != driver.id:
            return Response(
                {'error': 'You are not authorized to update this delivery'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        with transaction.atomic():
            if new_status == 'picked_up':
                delivery.status = 'picked_up'
                delivery.picked_up_at = timezone.now()
                delivery.save()
                
                # Update order status
                order = delivery.order
                order.status = 'picked_up'
                order.save()
                
                logger.info(f'Driver {driver.user.username} picked up order #{order.id}')
                
            elif new_status == 'delivered':
                delivery.status = 'delivered'
                delivery.delivered_at = timezone.now()
                delivery.save()
                
                order = delivery.order
                order.status = 'delivered'
                order.save()
                
                # Update driver earnings
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
                
                # Reset order status back to ready
                order = delivery.order
                order.status = 'ready'
                order.save()
                
                driver.status = 'online'
                driver.is_available = True
                driver.save()
                
                logger.info(f'Delivery #{delivery.id} cancelled by driver')
        
        return Response({
            'success': True,
            'id': str(delivery.id),
            'status': delivery.status,
            'message': f'Delivery status updated to {new_status}'
        })