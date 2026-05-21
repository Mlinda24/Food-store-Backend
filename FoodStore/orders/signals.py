# orders/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Order
import logging

logger = logging.getLogger(__name__)

@receiver(post_save, sender=Order)
def handle_order_delivery(sender, instance, created, **kwargs):
    """Auto-distribute payment when order is delivered"""
    if not created and instance.status == 'delivered':
        try:
            old_instance = sender.objects.get(pk=instance.pk)
            if old_instance.status != 'delivered':
                # Order just got delivered!
                logger.info(f"Order #{instance.id} delivered. Distributing payment...")
                
                if hasattr(instance, 'payment'):
                    payment = instance.payment
                    if payment.status == 'completed' and not payment.distributed_to_wallets:
                        from payments.services.wallet_service import WalletDistributionService
                        WalletDistributionService.distribute_to_wallets(payment)
                    else:
                        logger.warning(f"Cannot distribute: payment status={payment.status}")
        except sender.DoesNotExist:
            pass