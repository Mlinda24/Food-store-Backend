# drivers/views.py - COMPLETE FIXED VERSION
from django.db.models import Q, Sum, Count, Avg
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from decimal import Decimal
from datetime import timedelta
import math

from orders.models import Order
from .models import DriverProfile, DeliveryAssignment, DriverLocationHistory, DriverEarning
from .serializers import (
    DriverProfileSerializer, DriverRegisterSerializer, DriverLocationSerializer,
    DriverStatusSerializer, DeliveryAssignmentSerializer, AvailableOrderSerializer,
    DriverEarningSummarySerializer
)

User = get_user_model()


class DriverViewSet(viewsets.ViewSet):
    """Driver operations viewset"""
    permission_classes = [IsAuthenticated]
    
    # Helper methods
    def get_driver_profile(self, user):
        try:
            return DriverProfile.objects.get(user=user)
        except DriverProfile.DoesNotExist:
            return None
    
    # ------------------------------------------------------------------
    # Driver Registration
    # ------------------------------------------------------------------
    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def register(self, request):
        """Register as a new driver"""
        serializer = DriverRegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if user already exists
        if User.objects.filter(username=serializer.validated_data['username']).exists():
            return Response({'error': 'Username already exists'}, status=status.HTTP_400_BAD_REQUEST)
        
        if User.objects.filter(email=serializer.validated_data['email']).exists():
            return Response({'error': 'Email already exists'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Create user with role='driver'
        user = User.objects.create_user(
            username=serializer.validated_data['username'],
            email=serializer.validated_data['email'],
            password=serializer.validated_data['password']
        )
        user.role = 'driver'
        user.phone = serializer.validated_data['phone_number']
        user.save()
        
        # Create driver profile
        driver_profile = DriverProfile.objects.create(
            user=user,
            phone_number=serializer.validated_data['phone_number'],
            vehicle_type=serializer.validated_data['vehicle_type'],
            vehicle_registration=serializer.validated_data['vehicle_registration'],
            license_number=serializer.validated_data['license_number'],
            license_expiry_date=serializer.validated_data['license_expiry_date'],
            status='offline',
            is_available=False,
            is_verified=False
        )
        
        return Response({
            'success': True,
            'message': 'Driver registration successful. Awaiting verification.',
            'driver_id': driver_profile.id,
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'role': user.role,
                'phone': user.phone
            }
        }, status=status.HTTP_201_CREATED)
    
    # ------------------------------------------------------------------
    # Convert Existing User to Driver
    # ------------------------------------------------------------------
    @action(detail=False, methods=['post'])
    def apply_as_driver(self, request):
        """Convert existing authenticated user to driver"""
        # Check if user already has a driver profile
        if hasattr(request.user, 'driver_profile'):
            return Response({'error': 'You are already registered as a driver'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if user already has driver role
        if request.user.role == 'driver':
            return Response({'error': 'User role is already driver'}, status=status.HTTP_400_BAD_REQUEST)
        
        serializer = DriverRegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        # Update user role and phone
        request.user.role = 'driver'
        request.user.phone = serializer.validated_data['phone_number']
        request.user.save()
        
        # Create driver profile for existing user
        driver_profile = DriverProfile.objects.create(
            user=request.user,
            phone_number=serializer.validated_data['phone_number'],
            vehicle_type=serializer.validated_data['vehicle_type'],
            vehicle_registration=serializer.validated_data['vehicle_registration'],
            license_number=serializer.validated_data['license_number'],
            license_expiry_date=serializer.validated_data['license_expiry_date'],
            status='offline',
            is_available=False,
            is_verified=False
        )
        
        return Response({
            'success': True,
            'message': 'Driver application submitted. Awaiting verification.',
            'driver_id': driver_profile.id,
            'user': {
                'id': request.user.id,
                'username': request.user.username,
                'email': request.user.email,
                'role': request.user.role,
                'phone': request.user.phone
            }
        }, status=status.HTTP_201_CREATED)
    
    # ------------------------------------------------------------------
    # Get/Update Driver Profile
    # ------------------------------------------------------------------
    @action(detail=False, methods=['get'])
    def profile(self, request):
        """Get current driver's profile"""
        driver = self.get_driver_profile(request.user)
        if not driver:
            return Response({'error': 'Driver profile not found'}, status=status.HTTP_404_NOT_FOUND)
        
        serializer = DriverProfileSerializer(driver)
        return Response(serializer.data)
    
    @action(detail=False, methods=['patch'])
    def update_profile(self, request):
        """Update driver profile"""
        driver = self.get_driver_profile(request.user)
        if not driver:
            return Response({'error': 'Driver profile not found'}, status=status.HTTP_404_NOT_FOUND)
        
        serializer = DriverProfileSerializer(driver, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            # Also update phone in User model if provided
            if 'phone_number' in request.data:
                request.user.phone = request.data['phone_number']
                request.user.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    # ------------------------------------------------------------------
    # Location Updates
    # ------------------------------------------------------------------
    @action(detail=False, methods=['post'])
    def update_location(self, request):
        """Update driver's current location"""
        driver = self.get_driver_profile(request.user)
        if not driver:
            return Response({'error': 'Driver profile not found'}, status=status.HTTP_404_NOT_FOUND)
        
        serializer = DriverLocationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        driver.current_latitude = serializer.validated_data['latitude']
        driver.current_longitude = serializer.validated_data['longitude']
        driver.last_location_update = timezone.now()
        driver.save()
        
        # Save location history
        DriverLocationHistory.objects.create(
            driver=request.user,
            latitude=serializer.validated_data['latitude'],
            longitude=serializer.validated_data['longitude']
        )
        
        return Response({
            'success': True,
            'message': 'Location updated',
            'latitude': str(driver.current_latitude),
            'longitude': str(driver.current_longitude)
        })
    
    # ------------------------------------------------------------------
    # Availability Status
    # ------------------------------------------------------------------
    @action(detail=False, methods=['patch'])
    def update_status(self, request):
        """Update driver's availability status"""
        driver = self.get_driver_profile(request.user)
        if not driver:
            return Response({'error': 'Driver profile not found'}, status=status.HTTP_404_NOT_FOUND)
        
        serializer = DriverStatusSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        driver.status = serializer.validated_data['status']
        if 'is_available' in serializer.validated_data:
            driver.is_available = serializer.validated_data['is_available']
        else:
            driver.is_available = (driver.status == 'online')
        driver.save()
        
        return Response({
            'success': True,
            'status': driver.status,
            'is_available': driver.is_available
        })
    
    @action(detail=False, methods=['post'])
    def go_online(self, request):
        """Set driver status to online"""
        driver = self.get_driver_profile(request.user)
        if not driver:
            return Response({'error': 'Driver profile not found'}, status=status.HTTP_404_NOT_FOUND)
        
        if not driver.is_verified:
            return Response({'error': 'Driver account not verified yet'}, status=status.HTTP_403_FORBIDDEN)
        
        if not driver.current_latitude or not driver.current_longitude:
            return Response({'error': 'Please update your location first'}, status=status.HTTP_400_BAD_REQUEST)
        
        driver.status = 'online'
        driver.is_available = True
        driver.save()
        
        return Response({
            'success': True,
            'status': 'online',
            'message': 'You are now online and available for deliveries'
        })
    
    @action(detail=False, methods=['post'])
    def go_offline(self, request):
        """Set driver status to offline"""
        driver = self.get_driver_profile(request.user)
        if driver:
            driver.status = 'offline'
            driver.is_available = False
            driver.save()
        
        return Response({
            'success': True,
            'status': 'offline',
            'message': 'You are now offline'
        })
    
    # ------------------------------------------------------------------
    # Available Orders (Nearby)
    # ------------------------------------------------------------------
    @action(detail=False, methods=['get'])
    def available_orders(self, request):
        """Get nearby orders available for pickup"""
        driver = self.get_driver_profile(request.user)
        if not driver:
            return Response({'error': 'Driver profile not found'}, status=status.HTTP_404_NOT_FOUND)
        
        if not driver.is_available or driver.status != 'online':
            return Response({'error': 'You must be online to see available orders'}, status=status.HTTP_400_BAD_REQUEST)
        
        if not driver.current_latitude or not driver.current_longitude:
            return Response({'error': 'Please update your location first'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Find orders ready for pickup
        available_orders = Order.objects.filter(
            status__in=['ready', 'preparing'],
            driver_id__isnull=True,
            delivery_assignment__isnull=True
        ).exclude(
            status='cancelled'
        ).order_by('created')
        
        # Calculate distance and estimated earning for each order
        order_data = []
        for order in available_orders:
            restaurant_lat = None
            restaurant_lng = None
            
            try:
                from restaurants.models import Restaurant
                restaurant = Restaurant.objects.get(id=order.restaurant_id)
                restaurant_lat = getattr(restaurant, 'latitude', None)
                restaurant_lng = getattr(restaurant, 'longitude', None)
            except:
                pass
            
            distance = None
            if restaurant_lat and restaurant_lng:
                distance = self.calculate_distance(
                    float(driver.current_latitude),
                    float(driver.current_longitude),
                    float(restaurant_lat),
                    float(restaurant_lng)
                )
            
            estimated_earning = self.calculate_delivery_fee(distance or Decimal('2.0'))
            
            order_data.append({
                'id': order.id,
                'restaurant_id': order.restaurant_id,
                'restaurant_name': order.restaurant_name,
                'total_price': str(order.total_price),
                'delivery_address': order.delivery_address,
                'created': order.created,
                'distance_km': float(distance) if distance else None,
                'estimated_earning': str(estimated_earning)
            })
        
        # Sort by distance
        order_data.sort(key=lambda x: x['distance_km'] if x['distance_km'] else 999)
        
        return Response({
            'count': len(order_data),
            'orders': order_data
        })
    
    def calculate_distance(self, lat1, lon1, lat2, lon2):
        """Calculate distance between two points in km using Haversine formula"""
        R = 6371
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        
        a = math.sin(delta_lat/2) * math.sin(delta_lat/2) + \
            math.cos(lat1_rad) * math.cos(lat2_rad) * \
            math.sin(delta_lon/2) * math.sin(delta_lon/2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        
        distance = R * c
        return Decimal(str(round(distance, 2)))
    
    def calculate_delivery_fee(self, distance_km):
        """Calculate delivery fee based on distance"""
        base_fee = Decimal('500.00')
        per_km_rate = Decimal('200.00')
        return base_fee + (distance_km * per_km_rate)
    
    # ------------------------------------------------------------------
    # Accept Order
    # ------------------------------------------------------------------
    @action(detail=False, methods=['post'])
    def accept_order(self, request):
        """Accept a delivery order"""
        order_id = request.data.get('order_id')
        
        if not order_id:
            return Response({'error': 'order_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        driver = self.get_driver_profile(request.user)
        if not driver:
            return Response({'error': 'Driver profile not found'}, status=status.HTTP_404_NOT_FOUND)
        
        if not driver.is_available:
            return Response({'error': 'You are not available for deliveries'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            return Response({'error': 'Order not found'}, status=status.HTTP_404_NOT_FOUND)
        
        if order.driver_id:
            return Response({'error': 'Order already assigned to another driver'}, status=status.HTTP_400_BAD_REQUEST)
        
        if order.status not in ['ready', 'preparing']:
            return Response({'error': f'Order not ready for pickup. Status: {order.status}'}, status=status.HTTP_400_BAD_REQUEST)
        
        restaurant_lat = None
        restaurant_lng = None
        try:
            from restaurants.models import Restaurant
            restaurant = Restaurant.objects.get(id=order.restaurant_id)
            restaurant_lat = getattr(restaurant, 'latitude', None)
            restaurant_lng = getattr(restaurant, 'longitude', None)
        except:
            pass
        
        distance = Decimal('2.0')
        if restaurant_lat and restaurant_lng and driver.current_latitude and driver.current_longitude:
            distance = self.calculate_distance(
                float(driver.current_latitude),
                float(driver.current_longitude),
                float(restaurant_lat),
                float(restaurant_lng)
            )
        
        delivery_fee = self.calculate_delivery_fee(distance)
        
        delivery = DeliveryAssignment.objects.create(
            order=order,
            driver=request.user,
            status='assigned',
            distance_km=distance,
            estimated_time_minutes=int(distance * 5),
            delivery_fee=delivery_fee,
            total_earning=delivery_fee
        )
        
        order.driver_id = request.user.id
        order.driver_name = request.user.get_full_name() or request.user.username
        order.delivery_distance = distance
        order.status = 'driver_assigned'
        order.driver_assigned_at = timezone.now()
        order.save()
        
        driver.status = 'busy'
        driver.is_available = False
        driver.save()
        
        return Response({
            'success': True,
            'message': 'Order accepted successfully',
            'delivery_id': delivery.id,
            'order_id': order.id,
            'distance_km': str(distance),
            'delivery_fee': str(delivery_fee),
            'estimated_minutes': delivery.estimated_time_minutes
        })
    
    # ------------------------------------------------------------------
    # Update Delivery Status
    # ------------------------------------------------------------------
    @action(detail=False, methods=['post'])
    def update_delivery_status(self, request):
        """Update delivery status (arrived, picked_up, delivered)"""
        delivery_id = request.data.get('delivery_id')
        status_update = request.data.get('status')
        
        if not delivery_id or not status_update:
            return Response({'error': 'delivery_id and status are required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            delivery = DeliveryAssignment.objects.get(id=delivery_id, driver=request.user)
        except DeliveryAssignment.DoesNotExist:
            return Response({'error': 'Delivery not found'}, status=status.HTTP_404_NOT_FOUND)
        
        order = delivery.order
        
        if status_update == 'arrived':
            delivery.status = 'arrived'
            delivery.arrived_at = timezone.now()
            delivery.save()
            order.status = 'driver_arrived'
            order.save()
            return Response({'success': True, 'status': 'arrived', 'message': 'You have arrived at the restaurant'})
        
        elif status_update == 'picked_up':
            delivery.status = 'picked_up'
            delivery.picked_up_at = timezone.now()
            delivery.save()
            order.status = 'picked_up'
            order.driver_picked_up_at = timezone.now()
            order.save()
            return Response({'success': True, 'status': 'picked_up', 'message': 'Food picked up. Heading to customer.'})
        
        elif status_update == 'delivered':
            delivery.status = 'delivered'
            delivery.delivered_at = timezone.now()
            if delivery.picked_up_at:
                time_taken = (timezone.now() - delivery.picked_up_at).total_seconds() / 60
                delivery.actual_time_minutes = int(time_taken)
            delivery.save()
            
            order.status = 'delivered'
            order.delivered_at = timezone.now()
            order.save()
            
            driver = self.get_driver_profile(request.user)
            driver.total_deliveries += 1
            driver.total_earnings += delivery.total_earning
            driver.status = 'online'
            driver.is_available = True
            driver.save()
            
            DriverEarning.objects.create(
                driver=request.user,
                delivery_assignment=delivery,
                amount=delivery.delivery_fee,
                earning_type='delivery_fee',
                description=f'Delivery fee for order #{order.id}'
            )
            
            return Response({
                'success': True,
                'status': 'delivered',
                'message': 'Order delivered successfully!',
                'earned': str(delivery.total_earning)
            })
        
        else:
            return Response({'error': 'Invalid status update'}, status=status.HTTP_400_BAD_REQUEST)
    
    # ------------------------------------------------------------------
    # Cancel Delivery
    # ------------------------------------------------------------------
    @action(detail=False, methods=['post'])
    def cancel_delivery(self, request):
        """Cancel an accepted delivery"""
        delivery_id = request.data.get('delivery_id')
        reason = request.data.get('reason', '')
        
        if not delivery_id:
            return Response({'error': 'delivery_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            delivery = DeliveryAssignment.objects.get(id=delivery_id, driver=request.user)
        except DeliveryAssignment.DoesNotExist:
            return Response({'error': 'Delivery not found'}, status=status.HTTP_404_NOT_FOUND)
        
        if delivery.status in ['picked_up', 'delivered']:
            return Response({'error': 'Cannot cancel delivery after food is picked up'}, status=status.HTTP_400_BAD_REQUEST)
        
        delivery.status = 'cancelled'
        delivery.cancelled_at = timezone.now()
        delivery.rejection_reason = reason
        delivery.save()
        
        order = delivery.order
        order.driver_id = None
        order.driver_name = ''
        order.status = 'ready'
        order.save()
        
        driver = self.get_driver_profile(request.user)
        driver.status = 'online'
        driver.is_available = True
        driver.save()
        
        return Response({
            'success': True,
            'message': 'Delivery cancelled successfully'
        })
    
    # ------------------------------------------------------------------
    # My Active Delivery
    # ------------------------------------------------------------------
    @action(detail=False, methods=['get'])
    def active_delivery(self, request):
        """Get current active delivery for driver"""
        driver = self.get_driver_profile(request.user)
        if not driver:
            return Response({'error': 'Driver profile not found'}, status=status.HTTP_404_NOT_FOUND)
        
        active_delivery = DeliveryAssignment.objects.filter(
            driver=request.user,
            status__in=['assigned', 'arrived', 'picked_up']
        ).first()
        
        if active_delivery:
            serializer = DeliveryAssignmentSerializer(active_delivery)
            return Response(serializer.data)
        
        return Response({'has_active_delivery': False})
    
    # ------------------------------------------------------------------
    # Delivery History
    # ------------------------------------------------------------------
    @action(detail=False, methods=['get'])
    def delivery_history(self, request):
        """Get driver's delivery history"""
        deliveries = DeliveryAssignment.objects.filter(
            driver=request.user
        ).order_by('-delivered_at')[:50]
        
        serializer = DeliveryAssignmentSerializer(deliveries, many=True)
        return Response({
            'count': deliveries.count(),
            'deliveries': serializer.data
        })
    
    # ------------------------------------------------------------------
    # Earnings Summary (FIXED - Single, Complete Version)
    # ------------------------------------------------------------------
    @action(detail=False, methods=['get'])
    def earnings_summary(self, request):
        """Get driver's earnings summary"""
        driver = self.get_driver_profile(request.user)
        if not driver:
            return Response({'error': 'Driver profile not found'}, status=status.HTTP_404_NOT_FOUND)
        
        today = timezone.now().date()
        week_start = today - timedelta(days=today.weekday())
        month_start = today.replace(day=1)
        
        today_earnings = DeliveryAssignment.objects.filter(
            driver=request.user,
            delivered_at__date=today,
            status='delivered'
        ).aggregate(total=Sum('total_earning'))['total'] or Decimal('0')
        
        week_earnings = DeliveryAssignment.objects.filter(
            driver=request.user,
            delivered_at__date__gte=week_start,
            status='delivered'
        ).aggregate(total=Sum('total_earning'))['total'] or Decimal('0')
        
        month_earnings = DeliveryAssignment.objects.filter(
            driver=request.user,
            delivered_at__date__gte=month_start,
            status='delivered'
        ).aggregate(total=Sum('total_earning'))['total'] or Decimal('0')
        
        today_deliveries = DeliveryAssignment.objects.filter(
            driver=request.user,
            delivered_at__date=today,
            status='delivered'
        ).count()
        
        # Calculate average rating from completed deliveries
        avg_rating = DeliveryAssignment.objects.filter(
            driver=request.user,
            status='delivered',
            customer_rating__isnull=False
        ).aggregate(avg=Avg('customer_rating'))['avg'] or driver.rating
        
        return Response({
            'today_earnings': float(today_earnings),
            'week_earnings': float(week_earnings),
            'month_earnings': float(month_earnings),
            'total_earnings': float(driver.total_earnings),
            'total_deliveries': driver.total_deliveries,
            'today_deliveries': today_deliveries,
            'rating': float(avg_rating),
            'acceptance_rate': 100.0,  # Calculate if you track this
            'completion_rate': 100.0,  # Calculate if you track this
            'average_delivery_time': 0,  # Calculate if you track this
            'total_distance': 0,  # Calculate if you track this
        })
    
    # ------------------------------------------------------------------
    # Rate Customer
    # ------------------------------------------------------------------
    @action(detail=False, methods=['post'])
    def rate_customer(self, request):
        """Rate the customer for a delivery"""
        delivery_id = request.data.get('delivery_id')
        rating = request.data.get('rating')
        feedback = request.data.get('feedback', '')
        
        if not delivery_id or not rating:
            return Response({'error': 'delivery_id and rating are required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            rating = int(rating)
            if rating < 1 or rating > 5:
                raise ValueError
        except:
            return Response({'error': 'Rating must be between 1 and 5'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            delivery = DeliveryAssignment.objects.get(id=delivery_id, driver=request.user)
        except DeliveryAssignment.DoesNotExist:
            return Response({'error': 'Delivery not found'}, status=status.HTTP_404_NOT_FOUND)
        
        if delivery.status != 'delivered':
            return Response({'error': 'Can only rate customers after delivery is complete'}, status=status.HTTP_400_BAD_REQUEST)
        
        delivery.customer_rating = rating
        delivery.customer_feedback = feedback
        delivery.save()
        
        return Response({
            'success': True,
            'message': 'Thank you for your feedback!'
        })