from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal
from apps.core.models import Item
from apps.production.models import ProductionRun


class Warehouse(models.Model):
    """Warehouse/Storage location"""
    
    WAREHOUSE_TYPE_CHOICES = (
        ('raw', 'Raw Materials'),
        ('packing', 'Packing Materials'),
        ('finished', 'Finished Goods'),
        ('wip', 'Work in Progress'),
        ('quarantine', 'Quarantine'),
        ('damaged', 'Damaged Goods'),
        ('returns', 'Returns'),
        ('consignment', 'Consignment'),
    )

    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, unique=True, help_text="RM-STORE, FG-WH, etc.")
    warehouse_type = models.CharField(
        max_length=20, 
        choices=WAREHOUSE_TYPE_CHOICES,
        default='raw',
        help_text="Type of warehouse"
    )
    
    # Location information
    location = models.CharField(max_length=100, blank=True, help_text="Physical location")
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True, default="Addis Ababa")
    country = models.CharField(max_length=100, blank=True, default="Ethiopia")
    
    # Contact information
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    manager = models.CharField(max_length=100, blank=True, help_text="Warehouse manager name")
    
    # Capacity
    capacity = models.DecimalField(
        max_digits=12, 
        decimal_places=4, 
        null=True, 
        blank=True,
        help_text="Total capacity in cubic meters or kg"
    )
    capacity_unit = models.CharField(
        max_length=10, 
        default="m³",
        help_text="Unit of capacity measurement"
    )
    
    # Status
    is_active = models.BooleanField(default=True)
    is_damaged = models.BooleanField(default=False, help_text="Is this a damaged goods warehouse?")
    is_quarantine = models.BooleanField(default=False, help_text="Is this a quarantine warehouse?")
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_warehouses'
    )

    class Meta:
        ordering = ['name']
        verbose_name = "Warehouse"
        verbose_name_plural = "Warehouses"
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['warehouse_type']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"

    @property
    def current_stock_value(self):
        """Calculate total stock value in this warehouse"""
        total = self.current_stock.aggregate(
            total=models.Sum(models.F('quantity') * models.F('item__unit_cost'))
        )['total'] or 0
        return total

    @property
    def item_count(self):
        """Count unique items in this warehouse"""
        return self.current_stock.values('item').distinct().count()


class Lot(models.Model):
    """Batch/Lot – mandatory for RUTF traceability"""
    
    QUALITY_STATUS_CHOICES = (
        ('pending', 'Pending Inspection'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('quarantine', 'In Quarantine'),
    )

    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name='lots')
    batch_number = models.CharField(max_length=50, unique=True, help_text="PN-20260226-001")
    
    # Supplier information - using string reference to avoid circular import
    supplier = models.ForeignKey(
        'purchasing.Supplier',  # Changed from direct import to string reference
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='lots'
    )
    supplier_batch = models.CharField(
        max_length=50, 
        blank=True, 
        help_text="Supplier's batch number"
    )
    
    # Dates
    manufacturing_date = models.DateField()
    expiry_date = models.DateField()
    received_date = models.DateField(default=timezone.now)
    manufactured_date = models.DateField(null=True, blank=True)
    
    # Quantities
    initial_quantity = models.DecimalField(
        max_digits=12, 
        decimal_places=4, 
        default=0,
        validators=[MinValueValidator(0)]
    )
    current_quantity = models.DecimalField(
        max_digits=12, 
        decimal_places=4, 
        default=0,
        validators=[MinValueValidator(0)]
    )
    allocated_quantity = models.DecimalField(
        max_digits=12, 
        decimal_places=4, 
        default=0,
        help_text="Quantity allocated to production orders"
    )
    
    # Quality
    quality_status = models.CharField(
        max_length=20,
        choices=QUALITY_STATUS_CHOICES,
        default='pending'
    )
    quality_checked_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='checked_lots'
    )
    quality_checked_date = models.DateTimeField(null=True, blank=True)
    quality_notes = models.TextField(blank=True)
    
    # Documents
    certificate_of_analysis = models.FileField(
        upload_to='lots/coa/',
        null=True,
        blank=True,
        help_text="Certificate of Analysis"
    )
    
    # Status
    is_active = models.BooleanField(default=True)
    is_blocked = models.BooleanField(default=False, help_text="Blocked from use")
    block_reason = models.TextField(blank=True)
    
    # Metadata
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_lots'
    )

    class Meta:
        ordering = ['-expiry_date', 'batch_number']
        unique_together = [['item', 'batch_number']]
        verbose_name = "Lot/Batch"
        verbose_name_plural = "Lots/Batches"
        indexes = [
            models.Index(fields=['batch_number']),
            models.Index(fields=['expiry_date']),
            models.Index(fields=['quality_status']),
        ]

    def __str__(self):
        return f"{self.batch_number} - {self.item.code} (exp {self.expiry_date})"

    @property
    def days_to_expire(self):
        """Calculate days until expiry"""
        return (self.expiry_date - timezone.now().date()).days

    @property
    def age_days(self):
        """Calculate age in days since received"""
        return (timezone.now().date() - self.received_date).days

    @property
    def available_quantity(self):
        """Calculate available quantity (not allocated)"""
        return self.current_quantity - self.allocated_quantity

    def is_near_expiry(self, days=90):
        """Check if lot is near expiry"""
        return 0 < self.days_to_expire <= days

    def is_expired(self):
        """Check if lot is expired"""
        return self.expiry_date < timezone.now().date()

    def save(self, *args, **kwargs):
        # Set current_quantity to initial_quantity on creation
        if not self.pk:
            self.current_quantity = self.initial_quantity
        super().save(*args, **kwargs)


class StockTransaction(models.Model):
    """Every single stock movement is recorded here"""
    
    TYPE_CHOICES = (
        ('receipt', 'Goods Receipt (Purchase)'),
        ('issue', 'Issue to Production'),
        ('adjustment', 'Stock Adjustment'),
        ('transfer', 'Warehouse Transfer'),
        ('return', 'Return from Production'),
        ('return_supplier', 'Return to Supplier'),
        ('scrap', 'Scrap / Waste'),
        ('sample', 'Quality Sample'),
    )

    transaction_type = models.CharField(max_length=20, choices=TYPE_CHOICES, db_index=True)
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name='stock_transactions')
    lot = models.ForeignKey(Lot, on_delete=models.PROTECT, null=True, blank=True, related_name='transactions')
    
    warehouse_from = models.ForeignKey(
        Warehouse, 
        on_delete=models.PROTECT,
        related_name='out_transactions', 
        null=True, 
        blank=True
    )
    warehouse_to = models.ForeignKey(
        Warehouse, 
        on_delete=models.PROTECT,
        related_name='in_transactions', 
        null=True, 
        blank=True
    )
    
    quantity = models.DecimalField(
        max_digits=12, 
        decimal_places=4,
        validators=[MinValueValidator(0.0001)]
    )
    unit_cost = models.DecimalField(
        max_digits=12, 
        decimal_places=4, 
        null=True, 
        blank=True,
        help_text="Unit cost at time of transaction"
    )
    
    transaction_date = models.DateTimeField(default=timezone.now, db_index=True)
    reference = models.CharField(
        max_length=100, 
        blank=True, 
        help_text="GRN-001, PO-001, PROD-20260226-003, etc."
    )
    
    # Related documents - all using string references
    production_run = models.ForeignKey(
        ProductionRun, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='stock_transactions'
    )
    purchase_order = models.ForeignKey(
        'purchasing.PurchaseOrder',  # String reference
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_transactions'
    )
    sales_order = models.ForeignKey(
        'sales.SalesOrder',  # String reference
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_transactions'
    )
    
    # Balance tracking
    balance_before = models.DecimalField(
        max_digits=12, 
        decimal_places=4, 
        null=True, 
        blank=True
    )
    balance_after = models.DecimalField(
        max_digits=12, 
        decimal_places=4, 
        null=True, 
        blank=True
    )
    
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        'auth.User', 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='created_transactions'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-transaction_date']
        verbose_name = "Stock Transaction"
        verbose_name_plural = "Stock Transactions"
        indexes = [
            models.Index(fields=['transaction_type', 'transaction_date']),
            models.Index(fields=['reference']),
        ]

    def __str__(self):
        direction = "→" if self.warehouse_to else "←" if self.warehouse_from else "•"
        return f"{self.get_transaction_type_display()} | {self.quantity} {self.item.code} {direction}"

    def save(self, *args, **kwargs):
        # Update lot quantities
        if self.lot:
            if self.transaction_type in ['receipt', 'return']:
                self.lot.current_quantity += self.quantity
            elif self.transaction_type in ['issue', 'scrap', 'adjustment']:
                self.lot.current_quantity -= self.quantity
            self.lot.save()
        
        super().save(*args, **kwargs)


class CurrentStock(models.Model):
    """Fast lookup of current balance (updated automatically via signals)"""
    
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name='inventory_stock')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='current_stock')
    lot = models.ForeignKey(Lot, on_delete=models.PROTECT, null=True, blank=True, related_name='current_stock')
    
    quantity = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    reserved_quantity = models.DecimalField(
        max_digits=12, 
        decimal_places=4, 
        default=0,
        help_text="Quantity reserved for production/sales"
    )
    
    last_updated = models.DateTimeField(auto_now=True)
    last_transaction = models.ForeignKey(
        StockTransaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+'
    )

    class Meta:
        unique_together = [['item', 'warehouse', 'lot']]
        ordering = ['item__code', 'warehouse__name']
        verbose_name = "Current Stock"
        verbose_name_plural = "Current Stock"
        indexes = [
            models.Index(fields=['item', 'warehouse']),
        ]

    def __str__(self):
        lot_str = f" - {self.lot.batch_number}" if self.lot else ""
        return f"{self.item.code} @ {self.warehouse.name}{lot_str} = {self.quantity}"

    @property
    def available_quantity(self):
        """Calculate available quantity (not reserved)"""
        return self.quantity - self.reserved_quantity

    @property
    def stock_value(self):
        """Calculate stock value"""
        return self.quantity * (self.item.unit_cost or 0)

    def update_from_transaction(self, transaction):
        """Update current stock based on transaction"""
        if transaction.transaction_type in ['receipt', 'return']:
            self.quantity += transaction.quantity
        elif transaction.transaction_type in ['issue', 'scrap', 'adjustment']:
            self.quantity -= transaction.quantity
        
        self.last_transaction = transaction
        self.save()


# Signal to update CurrentStock
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=StockTransaction)
def update_current_stock(sender, instance, created, **kwargs):
    """Update CurrentStock when a transaction is created"""
    if created:
        # Update or create CurrentStock for destination warehouse
        if instance.warehouse_to:
            current, _ = CurrentStock.objects.get_or_create(
                item=instance.item,
                warehouse=instance.warehouse_to,
                lot=instance.lot,
                defaults={'quantity': 0}
            )
            current.update_from_transaction(instance)
        
        # Update CurrentStock for source warehouse (if different)
        if instance.warehouse_from and instance.warehouse_from != instance.warehouse_to:
            current, _ = CurrentStock.objects.get_or_create(
                item=instance.item,
                warehouse=instance.warehouse_from,
                lot=instance.lot,
                defaults={'quantity': 0}
            )
            current.update_from_transaction(instance)