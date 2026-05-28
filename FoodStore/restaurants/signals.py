# restaurants/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Restaurant, RestaurantWallet


@receiver(post_save, sender=Restaurant)
def create_restaurant_wallet(sender, instance, created, **kwargs):
    """Create a wallet for every new restaurant"""
    if created:
        wallet, created = RestaurantWallet.objects.get_or_create(restaurant=instance)
        if created:
            print(f"✅ Wallet created for restaurant: {instance.name}")


@receiver(post_save, sender=Restaurant)
def save_restaurant_wallet(sender, instance, **kwargs):
    """Save wallet when restaurant is saved"""
    if hasattr(instance, 'wallet'):
        instance.wallet.save()