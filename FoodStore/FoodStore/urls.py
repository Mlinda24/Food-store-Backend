# FoodStore/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

# Swagger schema setup
schema_view = get_schema_view(
    openapi.Info(
        title="Food Store API",
        default_version='v1',
        description="API documentation for Food Store Backend",
        terms_of_service="https://www.google.com/policies/terms/",
        contact=openapi.Contact(email="admin@foodstore.com"),
        license=openapi.License(name="BSD License"),
    ),
    public=True,
    permission_classes=[permissions.AllowAny],
)

urlpatterns = [
    # Admin
    path('admin/', admin.site.urls),

    # Auth endpoints
    path('api/auth/', include('accounts.urls')),

    # App endpoints
    path('api/', include('restaurants.urls')),
    path('api/', include('orders.urls')),
    path('api/', include('payments.urls')),
    path('api/drivers/', include('drivers.urls')),
    path('api/', include('delivery.urls')),
    # DRF login
    path('api-auth/', include('rest_framework.urls')),

    # Swagger UI
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
]

# Serve media and static files in ALL environments (including production)
# This is necessary for Render to serve uploaded images
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)