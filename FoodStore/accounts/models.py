from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    CUSTOMER = 'customer'
    RESTAURANT = 'restaurant'
    DRIVER = 'driver'
    ADMIN = 'admin'
    
    ROLE_CHOICES = [
        (CUSTOMER, 'Customer'),
        (RESTAURANT, 'Restaurant Owner'),
        (DRIVER, 'Driver'),
        (ADMIN, 'Admin'),
    ]
    
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=CUSTOMER)
    phone = models.CharField(max_length=20, blank=True, null=True)
    
    groups = models.ManyToManyField(
        'auth.Group',
        related_name='accounts_user_set',
        blank=True,
        help_text='The groups this user belongs to.',
        verbose_name='groups',
    )
    
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        related_name='accounts_user_set',
        blank=True,
        help_text='Specific permissions for this user.',
        verbose_name='user permissions',
    )
    
    def __str__(self):
        return self.username
    
    @property
    def is_restaurant_owner(self):
        return self.role == self.RESTAURANT
    
    @property
    def is_customer(self):
        return self.role == self.CUSTOMER
    
    @property
    def is_driver(self):
        return self.role == self.DRIVER
    
    @property
    def is_admin_user(self):
        return self.role == self.ADMIN or self.is_superuser
    
    class Meta:
        db_table = 'auth_user'
        verbose_name = 'User'
        verbose_name_plural = 'Users'