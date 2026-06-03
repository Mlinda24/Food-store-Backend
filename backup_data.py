#!/usr/bin/env python
import os
import sys
import django
from django.core import serializers
from django.apps import apps
import json
from datetime import datetime
import shutil

# Set up Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'FoodStore.settings')

def setup_django():
    """Initialize Django"""
    django.setup()

def backup_all_data():
    """Backup all important data to JSON files"""
    setup_django()
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_dir = f'backups/backup_{timestamp}'
    os.makedirs(backup_dir, exist_ok=True)
    
    models_to_backup = [
        ('accounts', 'User'),
        ('restaurants', 'Restaurant'),
        ('restaurants', 'RestaurantWallet'),
        ('restaurants', 'WalletTransaction'),
        ('drivers', 'DriverProfile'),
        ('drivers', 'DeliveryAssignment'),
        ('orders', 'Order'),
        ('orders', 'Cart'),
        ('orders', 'CartItem'),
        ('payments', 'Payment'),
    ]
    
    backed_up = []
    failed = []
    
    for app, model_name in models_to_backup:
        try:
            model = apps.get_model(app, model_name)
            queryset = model.objects.all()
            data = serializers.serialize('json', queryset)
            
            with open(f'{backup_dir}/{app}_{model_name}.json', 'w') as f:
                f.write(data)
            backed_up.append(f'{app}.{model_name} ({queryset.count()} records)')
            print(f'✅ Backed up: {app}.{model_name} - {queryset.count()} records')
        except Exception as e:
            failed.append(f'{app}.{model_name}: {e}')
            print(f'❌ Failed to backup {app}.{model_name}: {e}')
    
    # Save backup info
    info = {
        'timestamp': timestamp,
        'backed_up': backed_up,
        'failed': failed,
        'total_models': len(models_to_backup),
        'successful_models': len(backed_up),
    }
    
    with open(f'{backup_dir}/backup_info.json', 'w') as f:
        json.dump(info, f, indent=2)
    
    print(f'\n📁 Backup saved to: {backup_dir}/')
    print(f'   ✅ Successful: {len(backed_up)} models')
    print(f'   ❌ Failed: {len(failed)} models')
    
    # Keep only last 10 backups
    if os.path.exists('backups'):
        backup_dirs = sorted([d for d in os.listdir('backups') if d.startswith('backup_')])
        while len(backup_dirs) > 10:
            old_backup = backup_dirs.pop(0)
            shutil.rmtree(f'backups/{old_backup}')
            print(f'🗑️ Removed old backup: {old_backup}')
    
    return backup_dir

if __name__ == '__main__':
    backup_all_data()