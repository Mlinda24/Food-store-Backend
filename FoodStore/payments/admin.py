from django.contrib import admin
from .models import Payment, WebhookLog

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['id', 'reference', 'order', 'amount', 'method', 'status', 'created_at']
    list_filter = ['status', 'method', 'created_at']
    search_fields = ['reference', 'transaction_id', 'order__id', 'order__customer__username']
    readonly_fields = ['reference', 'created_at', 'payment_details']
    
    fieldsets = (
        ('Payment Information', {
            'fields': ('reference', 'order', 'amount', 'method', 'status')
        }),
        ('Transaction Details', {
            'fields': ('transaction_id', 'phone_number', 'payment_details'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('order', 'order__customer')


@admin.register(WebhookLog)
class WebhookLogAdmin(admin.ModelAdmin):
    list_display = ['id', 'reference', 'received_at']
    list_filter = ['received_at']
    search_fields = ['reference']
    readonly_fields = ['reference', 'payload', 'received_at']
    
    fieldsets = (
        ('Webhook Data', {
            'fields': ('reference', 'payload')
        }),
        ('Timestamps', {
            'fields': ('received_at',)
        }),
    )
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False