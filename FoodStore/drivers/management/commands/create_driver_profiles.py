import os
from django.core.management.base import BaseCommand
from accounts.models import User
from drivers.models import DriverProfile

class Command(BaseCommand):
    help = 'Create driver profiles for existing driver users'

    def handle(self, *args, **options):
        self.stdout.write('Checking for driver users...')
        driver_users = User.objects.filter(role='driver')
        
        if not driver_users.exists():
            self.stdout.write(self.style.WARNING('No driver users found'))
            return
        
        created_count = 0
        for user in driver_users:
            profile, created = DriverProfile.objects.get_or_create(
                user=user,
                defaults={
                    'phone_number': user.phone_number or '0000000000',
                    'vehicle_type': 'motorcycle',
                    'vehicle_registration': f'REG{user.id}',
                    'vehicle_model': 'Standard',
                    'vehicle_color': 'Black',
                    'license_number': f'LIC{user.id}',
                    'license_expiry_date': '2025-12-31',
                    'status': 'offline',
                    'is_available': False,
                    'is_verified': True,
                }
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'Created profile for {user.username}'))
            else:
                self.stdout.write(f'Profile already exists for {user.username}')
        
        self.stdout.write(self.style.SUCCESS(f'Done. Created {created_count} profiles'))