from django.contrib import admin
from .models import Cart, CartItem, Order, OrderItem

class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    readonly_fields = ['added_at']
    fields = ['menu_item_id', 'menu_item_name', 'menu_item_price', 'quantity', 'customization', 'special_instructions', 'added_at']

@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'restaurant_id', 'restaurant_name', 'get_item_count', 'get_total_price', 'created_at', 'updated_at']
    list_filter = ['created_at', 'updated_at']
    search_fields = ['user__username', 'user__email', 'restaurant_name']
    readonly_fields = ['created_at', 'updated_at']
    inlines = [CartItemInline]
    
    def get_item_count(self, obj):
        return obj.items.count()
    get_item_count.short_description = 'Item Count'
    
    def get_total_price(self, obj):
        total = sum(item.menu_item_price * item.quantity for item in obj.items.all())
        return f'MK{total:.2f}'
    get_total_price.short_description = 'Total Price'

@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ['id', 'cart', 'menu_item_id', 'menu_item_name', 'quantity', 'added_at']
    list_filter = ['added_at']
    search_fields = ['cart__user__username', 'menu_item_name']
    readonly_fields = ['added_at']
    fields = ['cart', 'menu_item_id', 'menu_item_name', 'menu_item_price', 'quantity', 
              'customization', 'special_instructions', 'added_at']

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ['price']
    fields = ['menu_item_id', 'menu_item_name', 'menu_item_price', 'quantity', 'price', 
              'customization', 'special_instructions']

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'customer', 'restaurant_id', 'restaurant_name', 'status', 'total_price', 'created']
    list_filter = ['status', 'created']
    search_fields = ['customer__username', 'restaurant_name', 'delivery_address']
    readonly_fields = ['total_price', 'created', 'updated_at']
    inlines = [OrderItemInline]
    fieldsets = (
        ('Order Information', {
            'fields': ('customer', 'restaurant_id', 'restaurant_name', 'status', 'total_price')
        }),
        ('Delivery Details', {
            'fields': ('delivery_address', 'note')
        }),
        ('Timestamps', {
            'fields': ('created', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ['id', 'order', 'menu_item_id', 'menu_item_name', 'quantity', 'price']
    list_filter = ['order__status']
    search_fields = ['order__customer__username', 'menu_item_name']
    readonly_fields = ['menu_item_name', 'menu_item_price']
    fields = ['order', 'menu_item_id', 'menu_item_name', 'menu_item_price', 'quantity', 
              'price', 'customization', 'special_instructions']