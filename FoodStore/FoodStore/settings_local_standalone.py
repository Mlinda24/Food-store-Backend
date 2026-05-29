"""
Standalone local development settings - Does NOT import from settings.py
Use this for local testing without affecting production settings
"""

from pathlib import Path
import os
from datetime import timedelta

# Build paths
BASE_DIR = Path(__file__).resolve().parent.parent

# ============================================
# SECURITY
# ============================================
SECRET_KEY = 'django-insecure-local-dev-key-2024-foodie-express'
DEBUG = True

# ============================================
# ALLOWED HOSTS
# ============================================
ALLOWED_HOSTS = ['*']

# ============================================
# DATABASE - SQLite for local development
# ============================================
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db_local.sqlite3',
    }
}

# ============================================
# INSTALLED APPS (minimal for driver testing)
# ============================================
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    'drf_yasg',
    'accounts',
    'restaurants',
    'orders',
    'payments',
    'notifications',
    'drivers',
]

# ============================================
# MIDDLEWARE
# ============================================
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# ============================================
# URL Configuration
# ============================================
ROOT_URLCONF = 'FoodStore.urls'

# ============================================
# TEMPLATES
# ============================================
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# ============================================
# WSGI
# ============================================
WSGI_APPLICATION = 'FoodStore.wsgi.application'

# ============================================
# AUTHENTICATION
# ============================================
AUTH_USER_MODEL = 'accounts.User'

# ============================================
# PASSWORD VALIDATION
# ============================================
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ============================================
# INTERNATIONALIZATION
# ============================================
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# ============================================
# STATIC & MEDIA FILES
# ============================================
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles_local'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media_local'

# ============================================
# DEFAULT AUTO FIELD
# ============================================
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ============================================
# REST FRAMEWORK
# ============================================
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
}

# ============================================
# JWT SETTINGS
# ============================================
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# ============================================
# CORS SETTINGS
# ============================================
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_METHODS = ['DELETE', 'GET', 'OPTIONS', 'PATCH', 'POST', 'PUT']
CORS_ALLOW_HEADERS = [
    'accept', 'accept-encoding', 'authorization', 'content-type',
    'dnt', 'origin', 'user-agent', 'x-csrftoken', 'x-requested-with',
]

CSRF_TRUSTED_ORIGINS = [
    'http://localhost:3000',
    'http://127.0.0.1:3000',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
]

# ============================================
# EMAIL - Console backend for development
# ============================================
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# ============================================
# PAYCHANGU - Sandbox
# ============================================
PAYCHANGU_PUBLIC_KEY = 'pub-test-LmfcsVz5qVD4I4HJMv3K1hARQ6ZdVpr'
PAYCHANGU_SECRET_KEY = 'sec-test-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
PAYCHANGU_BASE_URL = 'https://sandbox.paychangu.com'

# ============================================
# WEBHOOK
# ============================================
WEBHOOK_BASE_URL = 'http://localhost:8000'
PAYCHANGU_WEBHOOK_SECRET = 'Tambudzai1939'

# ============================================
# SITE URL
# ============================================
SITE_URL = 'http://localhost:8000'

print("=" * 50)
print("RUNNING WITH STANDALONE LOCAL DEVELOPMENT SETTINGS")
print(f"Database: SQLite ({DATABASES['default']['NAME']})")
print(f"Debug Mode: {DEBUG}")
print(f"CORS: All origins allowed")
print("=" * 50)