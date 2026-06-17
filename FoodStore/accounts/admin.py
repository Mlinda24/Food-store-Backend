from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display  = ['username', 'email', 'role', 'phone', 'is_staff']
    list_filter   = ['role', 'is_staff', 'is_active']
    search_fields = ['username', 'email', 'phone']
    ordering      = ['username']

    fieldsets = UserAdmin.fieldsets + (
        ('Extra Info', {'fields': ('role', 'phone')}),
    )