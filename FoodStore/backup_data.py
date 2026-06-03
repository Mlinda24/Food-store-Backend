import os
import sys
import django
from django.core import serializers
from django.apps import apps
import json
from datetime import datetime
import shutil

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'FoodStore.settings')

def backup_all_data():
    django.setup()
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_dir = f'backups/backup_{timestamp}'
    os.makedirs(backup_dir, exist_ok=True)
    
    models_to_backup = [
        ('accounts', 'User'),
        ('restaurants', 'Restaurant'),
        ('drivers', 'DriverProfile'),
        ('orders', 'Order'),
        ('orders', 'Cart'),
        ('payments', 'Payment'),
    ]
    
    for app, model_name in models_to_backup:
        try:
            model = apps.get_model(app, model_name)
            data = serializers.serialize('json', model.objects.all())
            with open(f'{backup_dir}/{app}_{model_name}.json', 'w') as f:
                f.write(data)
            print(f'✅ Backed up: {app}.{model_name}')
        except Exception as e:
            print(f'❌ Failed: {app}.{model_name}: {e}')
    
    print(f'\n📁 Backup saved to: {backup_dir}/')

if __name__ == '__main__':
    backup_all_data()