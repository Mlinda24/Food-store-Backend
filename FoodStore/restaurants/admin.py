from django.contrib import admin
from .models import Restaurant, Category, MenuItem, RestaurantWallet, WalletTransaction


class WalletTransactionInline(admin.TabularInline):
    """Display wallet transactions inline"""
    model = WalletTransaction
    fields = ['transaction_type', 'amount', 'status', 'description', 'created_at']
    readonly_fields = ['created_at', 'reference']
    extra = 0
    can_delete = True
    max_num = 0
    classes = ['collapse']
    
    def has_add_permission(self, request, obj=None):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return True


class RestaurantWalletInline(admin.StackedInline):
    """Display wallet information inline in restaurant admin - Made editable"""
    model = RestaurantWallet
    can_delete = True
    verbose_name_plural = 'Wallet Information'
    # Made fields editable - removed readonly
    fields = ['balance', 'total_earned', 'total_withdrawn', 'balance_display', 'total_earned_display', 'total_withdrawn_display', 'updated_at']
    readonly_fields = ['balance_display', 'total_earned_display', 'total_withdrawn_display', 'updated_at']
    classes = ['wide']
    extra = 0
    
    def balance_display(self, obj):
        return f"MK{obj.balance:,.2f}"
    balance_display.short_description = 'Current Balance (Formatted)'
    
    def total_earned_display(self, obj):
        return f"MK{obj.total_earned:,.2f}"
    total_earned_display.short_description = 'Total Earned (Formatted)'
    
    def total_withdrawn_display(self, obj):
        return f"MK{obj.total_withdrawn:,.2f}"
    total_withdrawn_display.short_description = 'Total Withdrawn (Formatted)'
    
    def has_add_permission(self, request, obj=None):
        return True  # Allow adding wallets
    
    def has_delete_permission(self, request, obj=None):
        return True  # Allow delete for superusers
    
    def has_change_permission(self, request, obj=None):
        return True  # Allow changing wallet values


@admin.register(Restaurant)
class RestaurantAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'owner', 'phone', 'is_open', 'wallet_balance', 'created']
    list_filter = ['is_open', 'created']
    search_fields = ['name', 'owner__username', 'phone', 'address']
    readonly_fields = ['created', 'updated']
    inlines = [RestaurantWalletInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('owner', 'name', 'description', 'address', 'phone', 'image')
        }),
        ('Operations', {
            'fields': ('is_open', 'rating')
        }),
        ('Delivery Settings', {
            'fields': ('delivery_time', 'delivery_fee', 'min_order_amount', 
                      'base_delivery_fee', 'fee_per_km', 'free_delivery_radius', 'max_delivery_radius'),
            'classes': ('collapse',)
        }),
        ('Tiered Delivery Fees', {
            'fields': ('tier_1_fee', 'tier_2_fee', 'tier_3_fee', 'tier_4_fee', 'tier_5_fee'),
            'classes': ('collapse',)
        }),
        ('Location', {
            'fields': ('latitude', 'longitude'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created', 'updated'),
            'classes': ('collapse',)
        }),
    )
    
    def wallet_balance(self, obj):
        """Display wallet balance in list view"""
        try:
            if hasattr(obj, 'wallet'):
                return f"MK{obj.wallet.balance:,.2f}"
            return "No wallet"
        except:
            return "No wallet"
    wallet_balance.short_description = 'Wallet Balance'
    
    def get_queryset(self, request):
        """Optimize queryset to include wallet"""
        return super().get_queryset(request).select_related('wallet')
    
    def delete_model(self, request, obj):
        """Delete restaurant and its related wallet"""
        try:
            if hasattr(obj, 'wallet'):
                obj.wallet.delete()
            obj.delete()
            self.message_user(request, f'Restaurant "{obj.name}" deleted successfully.')
        except Exception as e:
            self.message_user(request, f'Error deleting restaurant: {e}', level='ERROR')
    
    def delete_queryset(self, request, queryset):
        """Delete multiple restaurants and their wallets"""
        deleted_count = 0
        error_count = 0
        for obj in queryset:
            try:
                if hasattr(obj, 'wallet'):
                    obj.wallet.delete()
                obj.delete()
                deleted_count += 1
            except Exception as e:
                error_count += 1
                self.message_user(request, f'Error deleting "{obj.name}": {e}', level='ERROR')
        
        if deleted_count > 0:
            self.message_user(request, f'Successfully deleted {deleted_count} restaurant(s).')
        if error_count > 0:
            self.message_user(request, f'Failed to delete {error_count} restaurant(s).', level='WARNING')
    
    actions = ['delete_selected_restaurants', 'add_funds_to_wallets']
    
    def delete_selected_restaurants(self, request, queryset):
        """Custom action to delete selected restaurants with their wallets"""
        deleted_count = 0
        for obj in queryset:
            try:
                if hasattr(obj, 'wallet'):
                    obj.wallet.delete()
                obj.delete()
                deleted_count += 1
            except Exception as e:
                self.message_user(request, f'Error deleting "{obj.name}": {e}', level='ERROR')
        
        if deleted_count > 0:
            self.message_user(request, f'Successfully deleted {deleted_count} restaurant(s).')
    delete_selected_restaurants.short_description = "Delete selected restaurants (with wallets)"
    
    def add_funds_to_wallets(self, request, queryset):
        """Custom action to add funds to selected restaurants' wallets"""
        from decimal import Decimal
        
        amount = Decimal('1000.00')  # Default amount
        # You could also create a dialog to ask for amount
        # For simplicity, we'll add MK1000
        
        added_count = 0
        for obj in queryset:
            try:
                wallet, created = RestaurantWallet.objects.get_or_create(restaurant=obj)
                wallet.balance += amount
                wallet.total_earned += amount
                wallet.save()
                
                # Create transaction record
                WalletTransaction.objects.create(
                    wallet=wallet,
                    transaction_type='credit',
                    amount=amount,
                    status='successful',
                    description=f'Admin added funds: MK{amount}'
                )
                added_count += 1
            except Exception as e:
                self.message_user(request, f'Error adding funds to "{obj.name}": {e}', level='ERROR')
        
        if added_count > 0:
            self.message_user(request, f'Successfully added MK{amount} to {added_count} restaurant wallet(s).')
    add_funds_to_wallets.short_description = "Add MK1,000 funds to selected restaurants' wallets"


@admin.register(RestaurantWallet)
class RestaurantWalletAdmin(admin.ModelAdmin):
    list_display = ['id', 'restaurant', 'balance_display', 'total_earned_display', 'total_withdrawn_display', 'updated_at']
    list_filter = ['updated_at']
    search_fields = ['restaurant__name', 'restaurant__owner__username']
    # Made fields editable - removed readonly
    fields = ['restaurant', 'balance', 'total_earned', 'total_withdrawn', 'balance_display', 'total_earned_display', 'total_withdrawn_display', 'updated_at']
    readonly_fields = ['balance_display', 'total_earned_display', 'total_withdrawn_display', 'updated_at']
    inlines = [WalletTransactionInline]
    
    def balance_display(self, obj):
        return f"MK{obj.balance:,.2f}"
    balance_display.short_description = 'Balance (Formatted)'
    
    def total_earned_display(self, obj):
        return f"MK{obj.total_earned:,.2f}"
    total_earned_display.short_description = 'Total Earned (Formatted)'
    
    def total_withdrawn_display(self, obj):
        return f"MK{obj.total_withdrawn:,.2f}"
    total_withdrawn_display.short_description = 'Total Withdrawn (Formatted)'
    
    def has_add_permission(self, request):
        return True  # Allow adding wallets
    
    def has_delete_permission(self, request, obj=None):
        return True  # Allow superusers to delete wallets if needed
    
    def has_change_permission(self, request, obj=None):
        return True  # Allow changing wallet values
    
    def save_model(self, request, obj, form, change):
        """Save wallet and create transaction record if balance changed"""
        if change:
            # Get the original object before change
            original = RestaurantWallet.objects.get(pk=obj.pk)
            if original.balance != obj.balance:
                difference = obj.balance - original.balance
                if difference > 0:
                    transaction_type = 'credit'
                    description = f'Admin adjusted balance: +MK{difference}'
                elif difference < 0:
                    transaction_type = 'debit'
                    description = f'Admin adjusted balance: -MK{abs(difference)}'
                else:
                    transaction_type = None
                
                if transaction_type:
                    WalletTransaction.objects.create(
                        wallet=obj,
                        transaction_type=transaction_type,
                        amount=abs(difference),
                        status='successful',
                        description=description
                    )
        
        super().save_model(request, obj, form, change)
    
    def delete_model(self, request, obj):
        """Delete wallet with confirmation"""
        restaurant_name = obj.restaurant.name
        obj.delete()
        self.message_user(request, f'Wallet for "{restaurant_name}" deleted successfully.')
    
    actions = ['add_funds_to_selected_wallets', 'deduct_funds_from_selected_wallets']
    
    def add_funds_to_selected_wallets(self, request, queryset):
        """Add funds to selected wallets"""
        from decimal import Decimal
        
        amount = Decimal('1000.00')
        added_count = 0
        
        for wallet in queryset:
            try:
                wallet.balance += amount
                wallet.total_earned += amount
                wallet.save()
                
                WalletTransaction.objects.create(
                    wallet=wallet,
                    transaction_type='credit',
                    amount=amount,
                    status='successful',
                    description=f'Admin added funds: MK{amount}'
                )
                added_count += 1
            except Exception as e:
                self.message_user(request, f'Error: {e}', level='ERROR')
        
        if added_count > 0:
            self.message_user(request, f'Successfully added MK{amount} to {added_count} wallet(s).')
    add_funds_to_selected_wallets.short_description = "Add MK1,000 to selected wallets"
    
    def deduct_funds_from_selected_wallets(self, request, queryset):
        """Deduct funds from selected wallets"""
        from decimal import Decimal
        
        amount = Decimal('500.00')
        deducted_count = 0
        
        for wallet in queryset:
            try:
                if wallet.balance >= amount:
                    wallet.balance -= amount
                    wallet.total_withdrawn += amount
                    wallet.save()
                    
                    WalletTransaction.objects.create(
                        wallet=wallet,
                        transaction_type='debit',
                        amount=amount,
                        status='successful',
                        description=f'Admin deducted funds: MK{amount}'
                    )
                    deducted_count += 1
                else:
                    self.message_user(request, f'Insufficient balance in {wallet.restaurant.name}', level='WARNING')
            except Exception as e:
                self.message_user(request, f'Error: {e}', level='ERROR')
        
        if deducted_count > 0:
            self.message_user(request, f'Successfully deducted MK{amount} from {deducted_count} wallet(s).')
    deduct_funds_from_selected_wallets.short_description = "Deduct MK500 from selected wallets"


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = ['id', 'wallet', 'transaction_type', 'amount_display', 'status', 'created_at']
    list_filter = ['transaction_type', 'status', 'created_at']
    search_fields = ['wallet__restaurant__name', 'description', 'reference']
    readonly_fields = ['reference', 'created_at']
    fields = ['wallet', 'transaction_type', 'amount', 'status', 'description', 'reference', 'created_at']
    
    def amount_display(self, obj):
        return f"MK{obj.amount:,.2f}"
    amount_display.short_description = 'Amount'
    
    def has_add_permission(self, request):
        return True  # Allow adding transactions manually
    
    def has_change_permission(self, request, obj=None):
        return False  # Don't allow changing transactions
    
    def has_delete_permission(self, request, obj=None):
        return True  # Allow superusers to delete transactions if needed
    
    def save_model(self, request, obj, form, change):
        """Save transaction and update wallet balance if needed"""
        if not change:  # Only for new transactions
            wallet = obj.wallet
            if obj.transaction_type == 'credit':
                wallet.balance += obj.amount
                wallet.total_earned += obj.amount
            elif obj.transaction_type == 'debit':
                if wallet.balance >= obj.amount:
                    wallet.balance -= obj.amount
                    wallet.total_withdrawn += obj.amount
                else:
                    raise ValueError(f"Insufficient balance. Available: MK{wallet.balance}")
            wallet.save()
        
        super().save_model(request, obj, form, change)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'restaurant']
    list_filter = ['restaurant']
    search_fields = ['name', 'restaurant__name']


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'restaurant', 'category', 'price_display', 'is_available', 'created']
    list_filter = ['is_available', 'restaurant', 'category']
    search_fields = ['name', 'description', 'restaurant__name']
    
    def price_display(self, obj):
        return f"MK{obj.price:,.2f}"
    price_display.short_description = 'Price'