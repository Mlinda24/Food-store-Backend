from django.contrib import admin
from .models import DriverProfile

@admin.register(DriverProfile)
class DriverProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'vehicle_type', 'vehicle_registration', 'status', 'is_available', 'total_deliveries']
    list_filter = ['status', 'vehicle_type', 'is_available', 'is_verified']
    search_fields = ['user__username', 'user__email', 'vehicle_registration', 'license_number']
    readonly_fields = ['created_at', 'updated_at', 'total_deliveries', 'total_earnings']
    
    fieldsets = (
        ('Driver Information', {
            'fields': ('user', 'phone_number', 'alternative_phone')
        }),
        ('Vehicle Information', {
            'fields': ('vehicle_type', 'vehicle_registration', 'vehicle_model', 'vehicle_color')
        }),
        ('License Information', {
            'fields': ('license_number', 'license_expiry_date')
        }),
        ('Status', {
            'fields': ('status', 'is_available', 'is_verified')
        }),
        ('Statistics', {
            'fields': ('total_deliveries', 'total_earnings', 'rating', 'total_ratings')
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')