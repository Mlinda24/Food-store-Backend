from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from orders.models import Cart
from drivers.models import DriverProfile
from restaurants.models import Restaurant, RestaurantWallet

User = get_user_model()

class Command(BaseCommand):
    help = 'Ensure test users exist (creates them if missing)'

    def handle(self, *args, **options):
        self.stdout.write('🔍 Checking for test users...')
        
        created_count = 0
        
        # Create customer
        customer, created = User.objects.get_or_create(
            username='customer1',
            defaults={
                'email': 'customer1@example.com',
                'role': 'customer',
                'phone': '0888123456'
            }
        )
        if created:
            customer.set_password('customer123')
            customer.save()
            Cart.objects.get_or_create(user=customer)
            self.stdout.write(self.style.SUCCESS('✅ Created customer1'))
            created_count += 1
        else:
            self.stdout.write('✓ customer1 already exists')
        
        # Create driver
        driver, created = User.objects.get_or_create(
            username='driver1',
            defaults={
                'email': 'driver1@example.com',
                'role': 'driver',
                'phone': '0999123456'
            }
        )
        if created:
            driver.set_password('driver123')
            driver.save()
            DriverProfile.objects.get_or_create(
                user=driver,
                defaults={
                    'phone_number': '0999123456',
                    'vehicle_type': 'motorcycle',
                    'vehicle_registration': 'REG001',
                    'license_number': 'LIC001',
                    'status': 'offline',
                    'is_available': False,
                    'is_verified': True,
                }
            )
            self.stdout.write(self.style.SUCCESS('✅ Created driver1'))
            created_count += 1
        else:
            self.stdout.write('✓ driver1 already exists')
        
        # Create restaurant user
        rest_user, created = User.objects.get_or_create(
            username='restaurant1',
            defaults={
                'email': 'restaurant1@example.com',
                'role': 'restaurant',
                'phone': '0777123456'
            }
        )
        if created:
            rest_user.set_password('restaurant123')
            rest_user.save()
            restaurant, created = Restaurant.objects.get_or_create(
                owner=rest_user,
                defaults={
                    'name': 'Test Restaurant',
                    'address': '123 Main Street',
                    'phone': '0777123456',
                    'description': 'A great place to eat',
                    'is_open': True,
                }
            )
            if created:
                RestaurantWallet.objects.get_or_create(restaurant=restaurant)
            self.stdout.write(self.style.SUCCESS('✅ Created restaurant1'))
            created_count += 1
        else:
            self.stdout.write('✓ restaurant1 already exists')
        
        if created_count > 0:
            self.stdout.write(self.style.SUCCESS(f'\n🎉 Created {created_count} new test users'))
        else:
            self.stdout.write(self.style.SUCCESS('\n✓ All test users already exist'))