# payments/admin.py
from django.contrib import admin
from .models import Payment, WebhookLog
from restaurants.models import Restaurant
from .models import Payment  # Wallet models are in payments.models if you moved them there

# If Wallet models are in payments.models, import from there
try:
    from .models import RestaurantWallet, WalletTransaction
except ImportError:
    # If they're in restaurants.models, import from there
    from restaurants.models import RestaurantWallet, WalletTransaction


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'reference', 'order', 'amount_display', 'method', 
        'status', 'distributed_to_wallets', 'created_at'
    ]
    list_filter = ['status', 'method', 'distributed_to_wallets', 'created_at']
    search_fields = ['reference', 'transaction_id', 'order__id', 'order__customer__username']
    readonly_fields = ['created_at', 'updated_at', 'paid_at', 'distributed_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('reference', 'order', 'amount', 'method', 'status', 'phone_number')
        }),
        ('Transaction Details', {
            'fields': ('transaction_id', 'payment_details', 'paid_at')
        }),
        ('Wallet Distribution', {
            'fields': ('distributed_to_wallets', 'distributed_at', 'platform_fee', 
                      'restaurant_amount', 'driver_amount')
        }),
        ('Refund Information', {
            'fields': ('refunded_amount', 'refund_reason', 'refunded_at')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def amount_display(self, obj):
        return f"MK{obj.amount:,.2f}"
    amount_display.short_description = 'Amount'
    
    actions = ['mark_as_completed', 'mark_distributed']
    
    def mark_as_completed(self, request, queryset):
        updated = queryset.update(status='completed')
        self.message_user(request, f'{updated} payments marked as completed.')
    mark_as_completed.short_description = "Mark selected payments as completed"
    
    def mark_distributed(self, request, queryset):
        updated = queryset.update(distributed_to_wallets=True)
        self.message_user(request, f'{updated} payments marked as distributed.')
    mark_distributed.short_description = "Mark selected payments as distributed"


@admin.register(WebhookLog)
class WebhookLogAdmin(admin.ModelAdmin):
    list_display = ['id', 'reference', 'event_type', 'processed', 'received_at']
    list_filter = ['processed', 'received_at']
    search_fields = ['reference']
    readonly_fields = ['received_at', 'payload']
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False


# Register RestaurantWallet if it exists in the model
try:
    from .models import RestaurantWallet
    @admin.register(RestaurantWallet)
    class RestaurantWalletAdmin(admin.ModelAdmin):
        list_display = ['id', 'restaurant', 'balance_display', 'total_earned_display', 'total_withdrawn_display', 'updated_at']
        search_fields = ['restaurant__name', 'restaurant__owner__username']
        readonly_fields = ['updated_at']
        
        def balance_display(self, obj):
            return f"MK{obj.balance:,.2f}"
        balance_display.short_description = 'Balance'
        
        def total_earned_display(self, obj):
            return f"MK{obj.total_earned:,.2f}"
        total_earned_display.short_description = 'Total Earned'
        
        def total_withdrawn_display(self, obj):
            return f"MK{obj.total_withdrawn:,.2f}"
        total_withdrawn_display.short_description = 'Total Withdrawn'
except ImportError:
    pass


# Register WalletTransaction if it exists in the model
try:
    from .models import WalletTransaction
    @admin.register(WalletTransaction)
    class WalletTransactionAdmin(admin.ModelAdmin):
        list_display = ['id', 'wallet', 'transaction_type', 'amount_display', 'status', 'created_at']
        list_filter = ['transaction_type', 'status', 'created_at']
        search_fields = ['wallet__restaurant__name', 'description', 'reference']
        readonly_fields = ['created_at', 'reference']
        
        def amount_display(self, obj):
            return f"MK{obj.amount:,.2f}"
        amount_display.short_description = 'Amount'
except ImportError:
    pass