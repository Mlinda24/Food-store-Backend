from django.utils import timezone
from orders.models import Escrow
import logging

logger = logging.getLogger(__name__)

class EscrowService:
    """Manages escrow holding of payments"""
    
    @classmethod
    def create_escrow(cls, order, payment):
        """Create escrow record when payment is initiated"""
        escrow, created = Escrow.objects.get_or_create(
            order=order,
            defaults={
                'amount': order.total_price,
                'status': 'holding',
                'payment_reference': payment.reference,
            }
        )
        
        if created:
            logger.info(f"Escrow created for Order #{order.id}: {order.total_price} MWK")
        else:
            logger.info(f"Escrow already exists for Order #{order.id}")
            
        return escrow
    
    @classmethod
    def release_escrow(cls, order):
        """Release escrow after successful delivery"""
        if hasattr(order, 'escrow'):
            escrow = order.escrow
            escrow.status = 'released'
            escrow.released_at = timezone.now()
            escrow.save()
            logger.info(f"Escrow released for Order #{order.id}")
            return True
        return False
    
    @classmethod
    def refund_escrow(cls, order):
        """Refund escrow if order is cancelled"""
        if hasattr(order, 'escrow'):
            escrow = order.escrow
            escrow.status = 'refunded'
            escrow.released_at = timezone.now()
            escrow.save()
            logger.info(f"Escrow refunded for Order #{order.id}")
            return True
        return False