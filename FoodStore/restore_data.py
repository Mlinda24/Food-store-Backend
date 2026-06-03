import os
import sys
import django
from django.core import serializers
import json
import glob

# Setup Django - use the correct module path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'FoodStore.settings')
django.setup()

def restore_data(backup_path):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    print(f'🔄 Restoring from: {backup_path}')
    
    restored = []
    failed = []
    
    for json_file in glob.glob(f'{backup_path}/*.json'):
        model_name = os.path.basename(json_file).replace('.json', '')
        try:
            with open(json_file, 'r') as f:
                data = f.read()
            
            if 'User' in model_name:
                User.objects.exclude(is_superuser=True).delete()
            
            for obj in serializers.deserialize('json', data):
                obj.save()
            
            restored.append(model_name)
            print(f'✅ Restored: {model_name}')
        except Exception as e:
            failed.append(f'{model_name}: {e}')
            print(f'❌ Failed to restore {model_name}: {e}')
    
    print(f'\n📊 Restore Summary:')
    print(f'   ✅ Restored: {len(restored)} models')
    print(f'   ❌ Failed: {len(failed)} models')

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        restore_data(sys.argv[1])
    else:
        print('Usage: python restore_data.py backups/backup_YYYYMMDD_HHMMSS/')
