
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal

class Cart(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='cart'
    )
    restaurant_id = models.IntegerField(null=True, blank=True)
    restaurant_name = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def total_price(self):
        return sum(item.total for item in self.items.all())
    
    @property
    def total_items(self):
        return sum(item.quantity for item in self.items.all())

    def __str__(self):
        return f"Cart for {self.user.username}"

    class Meta:
        verbose_name = 'Cart'
        verbose_name_plural = 'Carts'


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    menu_item_id = models.IntegerField()
    menu_item_name = models.CharField(max_length=255)
    menu_item_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)
    customization = models.JSONField(default=dict, blank=True)
    special_instructions = models.TextField(blank=True, default='')
    added_at = models.DateTimeField(auto_now_add=True)

    @property
    def total(self):
        return self.menu_item_price * self.quantity

    def __str__(self):
        base = f"{self.quantity} x {self.menu_item_name}"
        if self.customization:
            cust_str = ', '.join([f"{k}: {v}" for k, v in self.customization.items()])
            return f"{base} ({cust_str})"
        return base

    class Meta:
        verbose_name = 'Cart Item'
        verbose_name_plural = 'Cart Items'


class Order(models.Model):
    # Updated STATUS_CHOICES with more delivery states
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('driver_assigned', 'Driver Assigned'),
        ('driver_arrived', 'Driver Arrived at Restaurant'),
        ('preparing', 'Preparing'),
        ('ready', 'Ready for Pickup'),
        ('picked_up', 'Picked Up'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]
    
    # Payment status choices
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('escrow', 'In Escrow'),
        ('distributed', 'Distributed to Wallets'),
        ('refunded', 'Refunded'),
        ('failed', 'Failed'),
    ]
    
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='orders'
    )
    restaurant_id = models.IntegerField()
    restaurant_name = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    total_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    delivery_address = models.TextField(blank=True, default='')
    note = models.TextField(blank=True, default='')
    created = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # ========== NEW PAYMENT FIELDS ==========
    payment_status = models.CharField(
        max_length=20, 
        choices=PAYMENT_STATUS_CHOICES, 
        default='pending'
    )
    payment_method = models.CharField(
        max_length=20, 
        blank=True, 
        null=True,
        choices=[
            ('mpamba', 'TNM Mpamba'),
            ('airtel_money', 'Airtel Money'),
            ('card', 'Card'),
            ('cash', 'Cash on Delivery'),
        ]
    )
    payment_reference = models.CharField(
        max_length=200, 
        blank=True, 
        null=True,
        help_text="PayChangu transaction reference"
    )
    paid_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When customer completed payment"
    )
    
    # ========== NEW FINANCIAL FIELDS ==========
    platform_fee = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0,
        help_text="Platform fee (10%)"
    )
    driver_payment = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0,
        help_text="Amount paid to driver"
    )
    restaurant_payment = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0,
        help_text="Amount paid to restaurant"
    )
    
    # ========== NEW DRIVER FIELDS ==========
    driver_id = models.IntegerField(
        null=True, 
        blank=True,
        help_text="ID of assigned driver"
    )
    driver_name = models.CharField(
        max_length=255, 
        blank=True, 
        default='',
        help_text="Driver's name for display"
    )
    delivery_distance = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Distance in kilometers from restaurant to customer"
    )
    
    # ========== NEW TIMESTAMP FIELDS ==========
    driver_assigned_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When driver was assigned"
    )
    driver_accepted_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When driver accepted the order"
    )
    driver_arrived_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When driver arrived at restaurant"
    )
    driver_picked_up_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When driver picked up food"
    )
    delivered_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When driver marked as delivered"
    )
    delivery_confirmed_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When customer confirmed delivery"
    )
    money_distributed_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When money was sent to wallets"
    )
    escrow_released_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When money left escrow"
    )
    
    # ========== NEW FLAGS ==========
    delivery_confirmed_by_customer = models.BooleanField(
        default=False,
        help_text="Customer clicked 'Confirm Delivery'"
    )
    money_distributed = models.BooleanField(
        default=False,
        help_text="Money has been sent to wallets"
    )
    
    def __str__(self):
        return f"Order #{self.id} - {self.customer.username} - {self.status}"

    class Meta:
        verbose_name = 'Order'
        verbose_name_plural = 'Orders'
        ordering = ['-created']


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    menu_item_id = models.IntegerField()
    menu_item_name = models.CharField(max_length=255)
    menu_item_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)  # Price at time of order
    customization = models.JSONField(default=dict, blank=True)
    special_instructions = models.TextField(blank=True, default='')

    @property
    def total(self):
        return self.price * self.quantity

    @property
    def display_name(self):
        base = self.menu_item_name
        if self.customization:
            if 'relish' in self.customization:
                return f"{base} with {self.customization['relish']}"
            cust_str = ', '.join([f"{k}: {v}" for k, v in self.customization.items()])
            return f"{base} ({cust_str})"
        return base

    def __str__(self):
        base = f"{self.quantity} x {self.menu_item_name}"
        if self.customization:
            cust_str = ', '.join([f"{k}: {v}" for k, v in self.customization.items()])
            return f"{base} ({cust_str})"
        return base

    class Meta:
        verbose_name = 'Order Item'
        verbose_name_plural = 'Order Items'


# ========== NEW MODELS FOR WALLET & TRANSACTIONS ==========

class Wallet(models.Model):
    """User wallet for storing balances"""
    
    USER_TYPE_CHOICES = [
        ('customer', 'Customer'),
        ('restaurant', 'Restaurant Owner'),
        ('driver', 'Driver'),
        ('platform', 'Platform'),
        ('admin', 'Admin'),
    ]
    
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='wallet',
        null=True,
        blank=True,
        help_text="Null for platform wallet"
    )
    
    user_type = models.CharField(
        max_length=20,
        choices=USER_TYPE_CHOICES,
        default='customer'
    )
    
    balance = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0,
        help_text="Current wallet balance"
    )
    
    pending_balance = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0,
        help_text="Money waiting to be available"
    )
    
    total_earned = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0,
        help_text="Lifetime earnings"
    )
    
    total_withdrawn = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0,
        help_text="Money withdrawn"
    )
    
    currency = models.CharField(max_length=3, default='MWK')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        if self.user:
            return f"{self.user.username}'s Wallet: {self.balance} MWK"
        return f"Platform Wallet: {self.balance} MWK"
    
    class Meta:
        verbose_name = 'Wallet'
        verbose_name_plural = 'Wallets'


class Transaction(models.Model):
    """Record all money movements"""
    
    TRANSACTION_TYPES = [
        ('customer_payment', 'Customer Payment'),
        ('platform_fee', 'Platform Fee'),
        ('restaurant_earning', 'Restaurant Earning'),
        ('driver_earning', 'Driver Earning'),
        ('withdrawal', 'Withdrawal'),
        ('refund', 'Refund'),
        ('bonus', 'Bonus'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    transaction_id = models.CharField(
        max_length=100, 
        unique=True,
        help_text="Unique reference like TXN-20241223-001"
    )
    
    order = models.ForeignKey(
        Order, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='transactions'
    )
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='transactions',
        null=True,
        blank=True,
        help_text="Null for platform transactions"
    )
    
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    
    transaction_type = models.CharField(
        max_length=50, 
        choices=TRANSACTION_TYPES
    )
    
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='pending'
    )
    
    payment_method = models.CharField(
        max_length=50, 
        blank=True, 
        null=True
    )
    
    reference = models.CharField(
        max_length=200, 
        blank=True, 
        null=True,
        help_text="External reference (PayChangu, etc)"
    )
    
    description = models.TextField(blank=True, default='')
    
    balance_before = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0
    )
    
    balance_after = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0
    )
    
    metadata = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.transaction_id} - {self.transaction_type} - {self.amount} MWK"
    
    class Meta:
        verbose_name = 'Transaction'
        verbose_name_plural = 'Transactions'
        ordering = ['-created_at']


class Escrow(models.Model):
    """Hold payments before distribution"""
    
    STATUS_CHOICES = [
        ('holding', 'Holding'),
        ('released', 'Released'),
        ('refunded', 'Refunded'),
        ('disputed', 'Disputed'),
    ]
    
    order = models.OneToOneField(
        Order, 
        on_delete=models.CASCADE, 
        related_name='escrow'
    )
    
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='holding'
    )
    
    payment_reference = models.CharField(
        max_length=200, 
        blank=True, 
        null=True
    )
    
    platform_fee_held = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0
    )
    
    restaurant_amount_held = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0
    )
    
    driver_amount_held = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0
    )
    
    held_at = models.DateTimeField(auto_now_add=True)
    released_at = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"Escrow for Order #{self.order.id} - {self.amount} MWK"
    
    class Meta:
        verbose_name = 'Escrow'
        verbose_name_plural = 'Escrows'


class WithdrawalRequest(models.Model):
    """Request to withdraw money from wallet to mobile money"""
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('rejected', 'Rejected'),
    ]
    
    PROVIDER_CHOICES = [
        ('mpamba', 'TNM Mpamba'),
        ('airtel_money', 'Airtel Money'),
    ]
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='withdrawal_requests'
    )
    
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    
    phone_number = models.CharField(max_length=20)
    
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='pending'
    )
    
    reference = models.CharField(
        max_length=200, 
        blank=True, 
        null=True,
        help_text="PayChangu withdrawal reference"
    )
    
    notes = models.TextField(blank=True, default='')
    
    requested_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='processed_withdrawals'
    )
    
    def __str__(self):
        return f"Withdrawal #{self.id} - {self.user.username} - {self.amount} MWK"
    
    class Meta:
        verbose_name = 'Withdrawal Request'
        verbose_name_plural = 'Withdrawal Requests'
        ordering = ['-requested_at']