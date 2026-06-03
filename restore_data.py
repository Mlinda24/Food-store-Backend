#!/usr/bin/env python
import os
import sys
import django
from django.core import serializers
import json
import glob
from datetime import datetime

# Set up Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'FoodStore.settings')

def setup_django():
    """Initialize Django"""
    django.setup()

def get_latest_backup():
    """Get the most recent backup directory"""
    if not os.path.exists('backups'):
        return None
    backup_dirs = [d for d in os.listdir('backups') if d.startswith('backup_')]
    if not backup_dirs:
        return None
    return sorted(backup_dirs)[-1]

def restore_data(backup_path=None):
    """Restore data from backup"""
    setup_django()
    
    if not backup_path:
        latest = get_latest_backup()
        if not latest:
            print('❌ No backups found')
            return False
        backup_path = f'backups/{latest}'
    
    print(f'🔄 Restoring from: {backup_path}')
    
    restored = []
    failed = []
    
    for json_file in glob.glob(f'{backup_path}/*.json'):
        if 'backup_info' in json_file:
            continue
            
        model_name = os.path.basename(json_file).replace('.json', '')
        try:
            with open(json_file, 'r') as f:
                data = f.read()
            
            # Clear existing data for this model (except superusers)
            if 'User' in model_name:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                User.objects.exclude(is_superuser=True).delete()
            
            for obj in serializers.deserialize('json', data):
                obj.save()
            
            restored.append(model_name)
            print(f'✅ Restored: {model_name}')
        except Exception as e:
            failed.append(f'{model_name}: {e}')
            print(f'❌ Failed to restore {model_name}: {e}')
    
    print(f'\n📋 Restore Summary:')
    print(f'   ✅ Restored: {len(restored)} models')
    print(f'   ❌ Failed: {len(failed)} models')
    
    return True

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        restore_data(sys.argv[1])
    else:
        restore_data()