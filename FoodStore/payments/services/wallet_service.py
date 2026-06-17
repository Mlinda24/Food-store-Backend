from decimal import Decimal
from django.utils import timezone
from django.db import transaction as db_transaction
from django.contrib.auth import get_user_model
from orders.models import Order, Wallet, Transaction, Escrow
from payments.models import Payment
import logging
import uuid

logger = logging.getLogger(__name__)
User = get_user_model()

class WalletDistributionService:
    """Handles distribution of payments to wallets"""
    
    PLATFORM_FEE_PERCENTAGE = Decimal('10.0')  # 10%
    BASE_DRIVER_PAY = Decimal('500.00')  # MWK
    PER_KM_RATE = Decimal('200.00')  # MWK per km
    
    @classmethod
    def calculate_splits(cls, order, driver_payment=None):
        """Calculate how much each party gets"""
        total_amount = order.total_price
        
        # Platform fee (10%)
        platform_fee = (cls.PLATFORM_FEE_PERCENTAGE / 100) * total_amount
        
        # Driver payment (calculate if not provided)
        if driver_payment is None:
            driver_payment = cls.calculate_driver_payment(order)
        
        # Restaurant gets the rest
        restaurant_payment = total_amount - platform_fee - driver_payment
        
        return {
            'total': total_amount,
            'platform_fee': platform_fee,
            'driver_payment': driver_payment,
            'restaurant_payment': restaurant_payment
        }
    
    @classmethod
    def calculate_driver_payment(cls, order):
        """Calculate driver payment based on distance"""
        distance = order.delivery_distance or Decimal('2.00')
        driver_payment = cls.BASE_DRIVER_PAY + (Decimal(str(distance)) * cls.PER_KM_RATE)
        return driver_payment
    
    @classmethod
    def get_or_create_wallet(cls, user, user_type):
        """Get existing wallet or create new one"""
        if user_type == 'platform':
            # Platform wallet (special case - user is None)
            wallet, created = Wallet.objects.get_or_create(
                user=None,
                user_type='platform',
                defaults={
                    'balance': Decimal('0'),
                    'total_earned': Decimal('0'),
                    'total_withdrawn': Decimal('0'),
                    'currency': 'MWK'
                }
            )
        else:
            wallet, created = Wallet.objects.get_or_create(
                user=user,
                user_type=user_type,
                defaults={
                    'balance': Decimal('0'),
                    'total_earned': Decimal('0'),
                    'total_withdrawn': Decimal('0'),
                    'currency': 'MWK'
                }
            )
        
        if created:
            logger.info(f"Created new wallet for {user_type}: {user.username if user else 'Platform'}")
        
        return wallet
    
    @classmethod
    def get_restaurant_owner(cls, restaurant_id):
        """Get the owner user for a restaurant"""
        try:
            # Adjust this import based on your restaurant app structure
            from restaurant.models import Restaurant
            restaurant = Restaurant.objects.get(id=restaurant_id)
            return restaurant.owner
        except ImportError:
            logger.error("Restaurant model not found. Adjust import path.")
            return None
        except Exception as e:
            logger.error(f"Failed to get restaurant owner for ID {restaurant_id}: {e}")
            return None
    
    @classmethod
    def generate_transaction_id(cls):
        """Generate unique transaction ID"""
        return f"TXN-{uuid.uuid4().hex[:12].upper()}"
    
    @classmethod
    @db_transaction.atomic
    def distribute_to_wallets(cls, payment):
        """Main function: Distribute payment to wallets after order is delivered"""
        order = payment.order
        
        # Check if already distributed
        if payment.distributed_to_wallets:
            logger.info(f"Payment {payment.reference} already distributed")
            return True
        
        # Check if order is delivered
        if order.status != 'delivered':
            logger.warning(f"Order {order.id} not delivered yet. Status: {order.status}")
            return False
        
        # Calculate splits
        splits = cls.calculate_splits(order)
        
        # Update payment record
        payment.platform_fee = splits['platform_fee']
        payment.restaurant_amount = splits['restaurant_payment']
        payment.driver_amount = splits['driver_payment']
        payment.save()
        
        # Get or create wallets
        platform_wallet = cls.get_or_create_wallet(user=None, user_type='platform')
        
        # For restaurant
        restaurant_owner = cls.get_restaurant_owner(order.restaurant_id)
        if not restaurant_owner:
            logger.error(f"Cannot find restaurant owner for order {order.id}")
            return False
            
        restaurant_wallet = cls.get_or_create_wallet(
            user=restaurant_owner, 
            user_type='restaurant'
        )
        
        # For driver
        driver_user = None
        driver_wallet = None
        if order.driver_id:
            try:
                driver_user = User.objects.get(id=order.driver_id)
                driver_wallet = cls.get_or_create_wallet(user=driver_user, user_type='driver')
            except User.DoesNotExist:
                logger.warning(f"Driver user {order.driver_id} not found")
        
        # Update wallet balances
        # Platform wallet
        platform_wallet.balance += splits['platform_fee']
        platform_wallet.total_earned += splits['platform_fee']
        platform_wallet.save()
        
        # Create platform transaction
        Transaction.objects.create(
            transaction_id=cls.generate_transaction_id(),
            order=order,
            user=None,
            amount=splits['platform_fee'],
            transaction_type='platform_fee',
            status='completed',
            reference=payment.reference,
            description=f'Platform fee for order #{order.id}',
            balance_before=platform_wallet.balance - splits['platform_fee'],
            balance_after=platform_wallet.balance
        )
        
        # Restaurant wallet
        restaurant_wallet.balance += splits['restaurant_payment']
        restaurant_wallet.total_earned += splits['restaurant_payment']
        restaurant_wallet.save()
        
        # Create restaurant transaction
        Transaction.objects.create(
            transaction_id=cls.generate_transaction_id(),
            order=order,
            user=restaurant_owner,
            amount=splits['restaurant_payment'],
            transaction_type='restaurant_earning',
            status='completed',
            reference=payment.reference,
            description=f'Earnings from order #{order.id}',
            balance_before=restaurant_wallet.balance - splits['restaurant_payment'],
            balance_after=restaurant_wallet.balance
        )
        
        # Driver wallet (if driver exists)
        if driver_wallet and driver_user:
            driver_wallet.balance += splits['driver_payment']
            driver_wallet.total_earned += splits['driver_payment']
            driver_wallet.save()
            
            Transaction.objects.create(
                transaction_id=cls.generate_transaction_id(),
                order=order,
                user=driver_user,
                amount=splits['driver_payment'],
                transaction_type='driver_earning',
                status='completed',
                reference=payment.reference,
                description=f'Delivery payment for order #{order.id}',
                balance_before=driver_wallet.balance - splits['driver_payment'],
                balance_after=driver_wallet.balance
            )
        
        # Update escrow status
        if hasattr(order, 'escrow'):
            order.escrow.status = 'released'
            order.escrow.released_at = timezone.now()
            order.escrow.platform_fee_held = splits['platform_fee']
            order.escrow.restaurant_amount_held = splits['restaurant_payment']
            order.escrow.driver_amount_held = splits['driver_payment']
            order.escrow.save()
        
        # Update payment record
        payment.distributed_to_wallets = True
        payment.distributed_at = timezone.now()
        payment.save()
        
        # Update order
        order.payment_status = 'distributed'
        order.money_distributed = True
        order.money_distributed_at = timezone.now()
        order.platform_fee = splits['platform_fee']
        order.driver_payment = splits['driver_payment']
        order.restaurant_payment = splits['restaurant_payment']
        order.save()
        
        logger.info(
            f"Money distributed for Order #{order.id}: "
            f"Restaurant: {splits['restaurant_payment']}, "
            f"Driver: {splits['driver_payment']}, "
            f"Platform: {splits['platform_fee']}"
        )
        
        return True