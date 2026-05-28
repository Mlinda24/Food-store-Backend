import os
from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from restaurants.models import Restaurant, MenuItem
import cloudinary.uploader

class Command(BaseCommand):
    help = 'Migrate existing images to Cloudinary'

    def handle(self, *args, **options):
        # Migrate restaurant images
        for restaurant in Restaurant.objects.all():
            if restaurant.image and not restaurant.image.name.startswith('https://res.cloudinary.com'):
                try:
                    # Read the file
                    if restaurant.image and restaurant.image.name:
                        # Upload to Cloudinary
                        result = cloudinary.uploader.upload(
                            restaurant.image.path,
                            folder='restaurants/',
                            public_id=os.path.splitext(os.path.basename(restaurant.image.name))[0]
                        )
                        restaurant.image = result['secure_url']
                        restaurant.save()
                        self.stdout.write(f'Migrated restaurant: {restaurant.name}')
                except Exception as e:
                    self.stdout.write(f'Error migrating restaurant {restaurant.name}: {e}')

        # Migrate menu item images
        for item in MenuItem.objects.all():
            if item.image and not item.image.name.startswith('https://res.cloudinary.com'):
                try:
                    if item.image and item.image.name:
                        result = cloudinary.uploader.upload(
                            item.image.path,
                            folder='menu/',
                            public_id=os.path.splitext(os.path.basename(item.image.name))[0]
                        )
                        item.image = result['secure_url']
                        item.save()
                        self.stdout.write(f'Migrated menu item: {item.name}')
                except Exception as e:
                    self.stdout.write(f'Error migrating menu item {item.name}: {e}')

        self.stdout.write('Migration complete!')