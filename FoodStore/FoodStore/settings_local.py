"""
Local development settings - for testing driver functionality only
This file OVERRIDES settings.py for local development
"""

from .settings import *

# ============================================
# DEBUG & SECURITY
# ============================================
DEBUG = True

# Disable security for local development
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_BROWSER_XSS_FILTER = False
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

# ============================================
# DATABASE - Use SQLite for local development
# ============================================
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db_local.sqlite3',  # Separate from production
    }
}

# ============================================
# ALLOWED HOSTS & CORS
# ============================================
ALLOWED_HOSTS = ['*']  # Allow all hosts for local testing

# CORS - Allow all for local development
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True

# Allow specific methods and headers
CORS_ALLOW_METHODS = [
    'DELETE',
    'GET',
    'OPTIONS',
    'PATCH',
    'POST',
    'PUT',
]

CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
]

# CSRF Trusted Origins for local development
CSRF_TRUSTED_ORIGINS = [
    'http://localhost:3000',
    'http://127.0.0.1:3000',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
    'http://localhost:5173',
    'http://127.0.0.1:5173',
]

# ============================================
# CLOUDINARY - Disable for local development
# ============================================
# Remove cloudinary from installed apps
INSTALLED_APPS = [app for app in INSTALLED_APPS if app != 'cloudinary']

# Use local file storage instead of cloudinary
DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'

# ============================================
# EMAIL - Use console backend for development
# ============================================
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# ============================================
# PAYCHANGU - Use Sandbox for testing
# ============================================
PAYCHANGU_PUBLIC_KEY = 'pub-test-LmfcsVz5qVD4I4HJMv3K1hARQ6ZdVpr'
PAYCHANGU_SECRET_KEY = 'sec-test-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
PAYCHANGU_BASE_URL = 'https://sandbox.paychangu.com'

# ============================================
# WEBHOOK - Local development
# ============================================
WEBHOOK_BASE_URL = 'http://localhost:8000'
PAYCHANGU_WEBHOOK_SECRET = 'Tambudzai1939'

# ============================================
# SITE URL - Local development
# ============================================
SITE_URL = 'http://localhost:8000'
FRONTEND_URL = 'http://localhost:3000'

# ============================================
# STATIC & MEDIA FILES
# ============================================
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles_local'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media_local'

# ============================================
# LOGGING - For debugging
# ============================================
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'DEBUG',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'DEBUG',  # Shows SQL queries
            'propagate': False,
        },
        'drivers': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'orders': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}

print("=" * 50)
print("RUNNING WITH LOCAL DEVELOPMENT SETTINGS")
print(f"Database: SQLite ({DATABASES['default']['NAME']})")
print(f"Debug Mode: {DEBUG}")
print(f"CORS: All origins allowed")
print(f"Email: Console backend")
print(f"Cloudinary: Disabled")
print("=" * 50)