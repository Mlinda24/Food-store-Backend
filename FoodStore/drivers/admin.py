from django.contrib import admin
from .models import DriverProfile, DeliveryAssignment

@admin.register(DriverProfile)
class DriverProfileAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'phone_number', 'vehicle_type', 'status', 'is_verified', 'total_deliveries']
    list_filter = ['status', 'is_verified', 'vehicle_type']
    search_fields = ['user__username', 'user__email', 'phone_number', 'vehicle_registration']
    readonly_fields = ['created_at', 'updated_at', 'total_deliveries', 'total_earnings', 'current_balance']
    
    fieldsets = (
        ('User Information', {
            'fields': ('user', 'phone_number', 'alternative_phone')
        }),
        ('Vehicle Information', {
            'fields': ('vehicle_type', 'vehicle_registration', 'vehicle_model', 'vehicle_color')
        }),
        ('License Information', {
            'fields': ('license_number', 'license_expiry_date')
        }),
        ('Verification', {
            'fields': ('is_verified', 'verified_at')
        }),
        ('Status', {
            'fields': ('status', 'is_available')
        }),
        ('Location', {
            'fields': ('current_latitude', 'current_longitude', 'last_location_update')
        }),
        ('Statistics', {
            'fields': ('total_deliveries', 'total_earnings', 'current_balance', 'rating')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )


@admin.register(DeliveryAssignment)
class DeliveryAssignmentAdmin(admin.ModelAdmin):
    list_display = ['id', 'order', 'driver', 'status', 'delivery_fee', 'created_at']
    list_filter = ['status']
    search_fields = ['order__id', 'driver__user__username']
    readonly_fields = ['created_at', 'accepted_at', 'picked_up_at', 'delivered_at']
    
    fieldsets = (
        ('Assignment', {
            'fields': ('order', 'driver')
        }),
        ('Status', {
            'fields': ('status', 'delivery_fee')
        }),
        ('Timestamps', {
            'fields': ('accepted_at', 'picked_up_at', 'delivered_at', 'created_at')
        }),
    )


# FORCE REGISTRATION - Add this at the bottom
try:
    admin.site.unregister(DriverProfile)
except:
    pass
try:
    admin.site.unregister(DeliveryAssignment)
except:
    pass

admin.site.register(DriverProfile, DriverProfileAdmin)
admin.site.register(DeliveryAssignment, DeliveryAssignmentAdmin)