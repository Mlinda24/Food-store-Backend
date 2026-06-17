from django.contrib import admin
from .models import Restaurant, Category, MenuItem

@admin.register(Restaurant)
class RestaurantAdmin(admin.ModelAdmin):
    list_display  = ['name', 'owner', 'phone', 'is_open', 'created']
    list_filter   = ['is_open']
    search_fields = ['name', 'address']

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display  = ['name', 'restaurant']
    search_fields = ['name']

@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display  = ['name', 'restaurant', 'category', 'price', 'is_available']
    list_filter   = ['is_available', 'restaurant']
    search_fields = ['name']