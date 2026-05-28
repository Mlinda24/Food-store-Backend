# restaurants/management/commands/create_wallets.py
from django.core.management.base import BaseCommand
from restaurants.models import Restaurant, RestaurantWallet


class Command(BaseCommand):
    help = 'Create wallets for all existing restaurants that don\'t have one'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS('Creating wallets for existing restaurants'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
        
        created_count = 0
        existing_count = 0
        
        for restaurant in Restaurant.objects.all():
            wallet, created = RestaurantWallet.objects.get_or_create(restaurant=restaurant)
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'✅ Created wallet for: {restaurant.name}'))
            else:
                existing_count += 1
                self.stdout.write(self.style.WARNING(f'⚠️ Wallet already exists for: {restaurant.name} - Balance: MK{wallet.balance}'))
        
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS(f'Summary: {created_count} wallets created, {existing_count} already existed'))
        self.stdout.write(self.style.SUCCESS('=' * 60))