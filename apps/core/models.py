from django.db import models
from django.utils import timezone
from decimal import Decimal


class CompanyModel(models.Model):
    """Abstract base model that adds company scoping to all models"""
    company = models.ForeignKey(
        'company.Company',
        on_delete=models.CASCADE,
        related_name='%(class)s_set',
        help_text="Company this record belongs to",
        null=True,
        blank=True
    )

    class Meta:
        abstract = True


class Unit(CompanyModel):
    """Unit of measurement for items"""
    name = models.CharField(max_length=50, unique=True)
    abbreviation = models.CharField(max_length=10, unique=True)
    is_active = models.BooleanField(default=True, help_text="Whether this unit is active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Unit"
        verbose_name_plural = "Units"
        ordering = ['name']
        indexes = [
            models.Index(fields=['abbreviation']),
        ]

    def __str__(self):
        return f"{self.abbreviation} ({self.name})"


class Item(CompanyModel):
    """Item master data for all products, raw materials, and packaging"""
    
    ITEM_CATEGORY = (
        ('raw', 'Raw Material'),
        ('semi', 'Semi-Finished'),
        ('finished', 'Finished Product'),
        ('packing', 'Packing Material'),
        ('consumable', 'Consumable'),
        ('asset', 'Fixed Asset'),
    )

    PRODUCT_TYPE = (
        ('plumpy_nut', "Plumpy'Nut"),
        ('plumpy_sup', "Plumpy'Sup"),
        ('other', 'Other'),
    )

    STOCK_VALUATION_METHOD = (
        ('fifo', 'FIFO - First In First Out'),
        ('lifo', 'LIFO - Last In First Out'),
        ('average', 'Weighted Average'),
        ('standard', 'Standard Cost'),
    )

    # Basic Information
    code = models.CharField(max_length=50, unique=True, db_index=True, help_text="Unique item code")
    peach_code = models.CharField(max_length=100, blank=True, verbose_name="Peach / Purchase Name")
    name = models.CharField(max_length=200, help_text="Item name")
    description = models.TextField(blank=True, help_text="Detailed description")
    category = models.CharField(max_length=20, choices=ITEM_CATEGORY, db_index=True)
    product_type = models.CharField(max_length=20, choices=PRODUCT_TYPE, blank=True, null=True)

    # Unit and Status
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name='items')
    is_active = models.BooleanField(default=True, db_index=True)
    is_purchased = models.BooleanField(default=True, help_text="Can this item be purchased?")
    is_sold = models.BooleanField(default=False, help_text="Can this item be sold?")
    is_stocked = models.BooleanField(default=True, help_text="Is this item stocked in inventory?")

    # RUTF specific (Ready-to-Use Therapeutic Food)
    shelf_life_days = models.PositiveIntegerField(
        null=True, 
        blank=True, 
        help_text="730 for 24 months"
    )
    min_shelf_life_on_receipt = models.PositiveIntegerField(
        default=180,
        help_text="Minimum remaining shelf life when received (days)"
    )
    allergen_peanut = models.BooleanField(default=False, help_text="Contains peanut allergen")

    # Packaging specifications
    pack_size_kg = models.DecimalField(
        max_digits=8, 
        decimal_places=4, 
        null=True, 
        blank=True,
        help_text="e.g. 0.092 for Plumpy'Nut sachet"
    )
    weight_kg = models.DecimalField(
        max_digits=10, 
        decimal_places=4, 
        null=True, 
        blank=True,
        help_text="Item weight in kg"
    )
    volume_m3 = models.DecimalField(
        max_digits=10, 
        decimal_places=4, 
        null=True, 
        blank=True,
        help_text="Item volume in cubic meters"
    )

    # Cost and Valuation
    valuation_method = models.CharField(
        max_length=20,
        choices=STOCK_VALUATION_METHOD,
        default='average',
        help_text="Method used for stock valuation"
    )
    
    # Standard cost (for variance analysis and budgeting)
    std_unit_price = models.DecimalField(
        max_digits=12, 
        decimal_places=4, 
        default=Decimal('0.0000'),
        verbose_name="Standard Unit Price",
        help_text="Standard / budgeted unit price (for variance analysis)"
    )
    
    # Current/last purchase cost
    unit_cost = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=Decimal('0.0000'),
        verbose_name="Unit Cost",
        help_text="Cost per unit (per kg, per piece, etc.) - last purchase or average cost"
    )
    
    # Weighted average cost (calculated automatically)
    current_avg_cost = models.DecimalField(
        max_digits=12, 
        decimal_places=4, 
        default=Decimal('0.0000'), 
        editable=False,
        verbose_name="Average Cost",
        help_text="Weighted average cost from purchases"
    )

    # Stock Levels
    current_stock = models.DecimalField(
        max_digits=15,
        decimal_places=4,
        default=Decimal('0.0000'),
        verbose_name="Current Stock",
        help_text="Current quantity in stock (in the item's base unit)"
    )

    # Stock Alert Levels
    minimum_stock = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=Decimal('0.0000'),
        verbose_name="Minimum Stock Level",
        help_text="Alert when stock falls below this level (safety stock)"
    )
    
    maximum_stock = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=Decimal('0.0000'),
        verbose_name="Maximum Stock Level",
        help_text="Maximum desired stock level"
    )
    
    reorder_point = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=Decimal('0.0000'),
        verbose_name="Reorder Point",
        help_text="When stock reaches this level, trigger reorder (should be >= minimum_stock)"
    )
    
    reorder_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=Decimal('0.0000'),
        verbose_name="Reorder Quantity",
        help_text="Suggested quantity to order when below reorder point"
    )

    # Lead Times
    lead_time_days = models.PositiveIntegerField(
        default=0,
        help_text="Typical lead time in days for procurement"
    )

    # Tax Information
    tax_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=15.00,
        help_text="VAT/Tax rate percentage"
    )
    hs_code = models.CharField(
        max_length=20, 
        blank=True,
        verbose_name="HS Code",
        help_text="Harmonized System code for customs"
    )

    # Location
    default_location = models.CharField(
        max_length=100, 
        blank=True,
        help_text="Default storage location in warehouse"
    )
    bin_location = models.CharField(
        max_length=50, 
        blank=True,
        help_text="Bin/shelf location"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_items'
    )

    class Meta:
        verbose_name = "Item"
        verbose_name_plural = "Items"
        ordering = ['code']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['category']),
            models.Index(fields=['is_active']),
            models.Index(fields=['product_type']),
            models.Index(fields=['current_stock', 'minimum_stock']),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"

    # ===== Properties for Status Checks =====

    @property
    def is_rutf(self):
        """Check if item is RUTF (Plumpy'Nut or Plumpy'Sup)"""
        return self.product_type in ['plumpy_nut', 'plumpy_sup']

    @property
    def is_low_stock(self):
        """Check if current stock is below minimum stock level"""
        return self.current_stock <= self.minimum_stock

    @property
    def is_over_stock(self):
        """Check if current stock exceeds maximum stock level"""
        return self.maximum_stock > 0 and self.current_stock > self.maximum_stock

    @property
    def needs_reorder(self):
        """Check if current stock is at or below reorder point"""
        return self.current_stock <= self.reorder_point

    @property
    def stock_status(self):
        """Return a human-readable stock status with emoji"""
        if self.current_stock <= 0:
            return "🔴 Out of Stock"
        elif self.current_stock <= self.minimum_stock:
            return f"🟠 CRITICAL - Below Safety ({self.current_stock:.2f} / {self.minimum_stock:.2f})"
        elif self.current_stock <= self.reorder_point:
            return f"🟡 Reorder Needed ({self.current_stock:.2f} / {self.reorder_point:.2f})"
        elif self.maximum_stock > 0 and self.current_stock > self.maximum_stock:
            return f"🟣 Over Stock ({self.current_stock:.2f} / {self.maximum_stock:.2f})"
        return f"🟢 OK ({self.current_stock:.2f})"

    @property
    def stock_deficit(self):
        """Calculate how much below minimum stock (if any)"""
        if self.current_stock < self.minimum_stock:
            return self.minimum_stock - self.current_stock
        return Decimal('0.0000')

    @property
    def stock_value(self):
        """Calculate current stock value"""
        return self.current_stock * self.current_avg_cost

    # ===== Methods =====

    def save(self, *args, **kwargs):
        """Ensure reorder_point is at least minimum_stock"""
        if self.reorder_point < self.minimum_stock:
            self.reorder_point = self.minimum_stock
        super().save(*args, **kwargs)

    def update_avg_cost(self):
        """
        Update weighted average cost based on purchase receipts
        This should be called via signal after new purchase receipt
        """
        from django.db.models import Sum, F
        from apps.inventory.models import StockTransaction
        
        receipts = StockTransaction.objects.filter(
            item=self,
            transaction_type='receipt'
        ).aggregate(
            total_qty=Sum('quantity'),
            total_cost=Sum(F('quantity') * F('unit_price'))
        )
        
        total_qty = receipts['total_qty'] or Decimal('1')
        total_cost = receipts['total_cost'] or Decimal('0')
        
        if total_qty > 0:
            self.current_avg_cost = total_cost / total_qty
            self.save(update_fields=['current_avg_cost'])
        
        return self.current_avg_cost

    def adjust_stock(self, quantity, transaction_type, user=None, reference=''):
        """
        Adjust stock level and create transaction record
        """
        from apps.inventory.models import StockTransaction
        
        # Update current stock
        self.current_stock += quantity
        self.save(update_fields=['current_stock'])
        
        # Create transaction record
        transaction = StockTransaction.objects.create(
            transaction_type=transaction_type,
            item=self,
            quantity=quantity,
            reference=reference,
            created_by=user,
            notes=f"Stock adjustment for {self.code}"
        )
        
        return transaction