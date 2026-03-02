from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal
from apps.core.models import Item, Unit
from apps.company.models import Company, Branch
from apps.inventory.models import Warehouse, Lot, StockTransaction


class Supplier(models.Model):
    """Supplier/Vendor model with comprehensive vendor management fields"""
    
    # Core fields
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='suppliers')
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True, blank=True, null=True)
    
    # Tax & Registration
    tin = models.CharField(max_length=50, blank=True, verbose_name="TIN")
    tax_id = models.CharField(max_length=50, blank=True, verbose_name="Tax ID/VAT Number")
    registration_number = models.CharField(max_length=50, blank=True, help_text="Business registration number")
    
    # Contact Information
    contact_person = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    mobile = models.CharField(max_length=20, blank=True, help_text="Mobile phone for urgent contact")
    email = models.EmailField(blank=True)
    website = models.URLField(blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, default="Ethiopia")
    
    # Financial & Payment Terms
    payment_terms_days = models.PositiveIntegerField(default=30, help_text="Payment terms in days")
    credit_limit = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    credit_terms_days = models.PositiveIntegerField(default=30, help_text="Credit terms in days")
    currency = models.CharField(max_length=3, default="ETB", help_text="Transaction currency")
    
    # Banking Information
    bank_name = models.CharField(max_length=100, blank=True)
    bank_account = models.CharField(max_length=50, blank=True)
    bank_branch = models.CharField(max_length=100, blank=True)
    swift_code = models.CharField(max_length=20, blank=True, help_text="SWIFT/BIC code")
    
    # Performance & Rating
    performance_rating = models.DecimalField(
        max_digits=3, decimal_places=2, default=0,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
        help_text="Supplier performance rating (0-5)"
    )
    on_time_delivery_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Percentage of on-time deliveries"
    )
    quality_rating = models.DecimalField(
        max_digits=3, decimal_places=2, default=0,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
        help_text="Quality rating (0-5)"
    )
    
    # Status & Metadata
    is_active = models.BooleanField(default=True, db_index=True)
    is_preferred = models.BooleanField(default=False, help_text="Preferred supplier status")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_suppliers'
    )

    class Meta:
        ordering = ['name']
        verbose_name = "Supplier"
        verbose_name_plural = "Suppliers"
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['tin']),
            models.Index(fields=['is_active', 'is_preferred']),
            models.Index(fields=['performance_rating']),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.code:
            # Generate a unique code from name
            base_code = self.name[:3].upper()
            count = Supplier.objects.filter(code__startswith=base_code).count()
            self.code = f"{base_code}{count + 1:03d}"
        super().save(*args, **kwargs)

    @property
    def total_purchase_orders(self):
        """Get total number of purchase orders for this supplier"""
        return self.purchase_orders.count()

    @property
    def total_spend(self):
        """Calculate total spend with this supplier"""
        return self.purchase_orders.filter(
            status__in=['received', 'partial']
        ).aggregate(total=models.Sum('total_amount'))['total'] or 0

    @property
    def average_lead_time(self):
        """Calculate average lead time for this supplier"""
        from django.db.models import Avg, F
        result = self.purchase_orders.filter(
            status='received'
        ).aggregate(
            avg_lead=Avg(F('goods_receipts__receipt_date') - F('order_date'))
        )
        return result['avg_lead']


class PurchaseRequisition(models.Model):
    """Purchase Requisition - internal request to purchase items"""
    
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('converted', 'Converted to PO'),
    )

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='purchase_requisitions')
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, null=True, blank=True)
    requisition_number = models.CharField(max_length=30, unique=True, editable=False)
    requested_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, related_name='purchase_requisitions')
    requested_date = models.DateField(default=timezone.now, db_index=True)
    required_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', db_index=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-requested_date']
        verbose_name = "Purchase Requisition"
        verbose_name_plural = "Purchase Requisitions"
        indexes = [
            models.Index(fields=['requisition_number']),
            models.Index(fields=['status', 'requested_date']),
        ]

    def __str__(self):
        return self.requisition_number

    def save(self, *args, **kwargs):
        if not self.requisition_number:
            last = PurchaseRequisition.objects.order_by('-id').first()
            num = (last.id + 1) if last else 1
            self.requisition_number = f"PR-{timezone.now().strftime('%Y%m')}-{num:05d}"
        super().save(*args, **kwargs)
    
    @property
    def total_estimated_value(self):
        """Calculate total estimated value of requisition"""
        total = sum(line.total_estimate for line in self.lines.all())
        return total


class PurchaseRequisitionLine(models.Model):
    """Line items for purchase requisition"""
    
    requisition = models.ForeignKey(PurchaseRequisition, on_delete=models.CASCADE, related_name='lines')
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name='purchase_requisition_lines')
    quantity = models.DecimalField(max_digits=12, decimal_places=4, validators=[MinValueValidator(0.0001)])
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT)
    unit_price_estimate = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text="Estimated unit price"
    )
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "Purchase Requisition Line"
        verbose_name_plural = "Purchase Requisition Lines"
        ordering = ['id']

    def __str__(self):
        return f"{self.item.code} × {self.quantity}"

    @property
    def total_estimate(self):
        """Calculate total estimated value for this line"""
        return self.quantity * self.unit_price_estimate


class PurchaseOrder(models.Model):
    """Purchase Order - sent to supplier"""
    
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('approved', 'Approved'),
        ('ordered', 'Sent to Supplier'),
        ('partial', 'Partially Received'),
        ('received', 'Fully Received'),
        ('closed', 'Closed'),
        ('cancelled', 'Cancelled'),
    )

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='purchase_orders')
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, null=True, blank=True)
    po_number = models.CharField(max_length=30, unique=True, editable=False, db_index=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='purchase_orders')
    requisition = models.ForeignKey(
        PurchaseRequisition, on_delete=models.SET_NULL, 
        null=True, blank=True, related_name='purchase_orders'
    )
    order_date = models.DateField(default=timezone.now, db_index=True)
    expected_delivery_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', db_index=True)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    approved_by = models.ForeignKey(
        'auth.User', null=True, blank=True, 
        on_delete=models.SET_NULL, related_name='approved_purchase_orders'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_purchase_orders'
    )

    class Meta:
        ordering = ['-order_date']
        verbose_name = "Purchase Order"
        verbose_name_plural = "Purchase Orders"
        indexes = [
            models.Index(fields=['po_number']),
            models.Index(fields=['status']),
            models.Index(fields=['order_date']),
            models.Index(fields=['supplier', 'status']),
        ]

    def __str__(self):
        return self.po_number

    def save(self, *args, **kwargs):
        if not self.po_number:
            last = PurchaseOrder.objects.order_by('-id').first()
            num = (last.id + 1) if last else 1
            self.po_number = f"PO-{timezone.now().strftime('%Y%m')}-{num:05d}"
        super().save(*args, **kwargs)

    def update_total(self):
        """Update total amount from lines"""
        total = sum(line.total_price for line in self.lines.all())
        self.total_amount = total
        self.save(update_fields=['total_amount'])

    def update_approval_status(self):
        """Update approval status based on approval records"""
        approvals = self.approvals.all()
        if approvals.filter(status='rejected').exists():
            self.status = 'cancelled'
        elif approvals.filter(status='pending').exists():
            # Still pending approval
            pass
        elif approvals.count() > 0 and all(a.status == 'approved' for a in approvals):
            self.status = 'approved'
        self.save()
    
    @property
    def receipt_percentage(self):
        """Calculate percentage of order received"""
        if not self.lines.exists():
            return 0
        total_qty = sum(line.quantity_ordered for line in self.lines.all())
        received_qty = sum(line.quantity_received for line in self.lines.all())
        if total_qty == 0:
            return 0
        return (received_qty / total_qty) * 100
    
    @property
    def is_fully_received(self):
        """Check if order is fully received"""
        return all(line.remaining <= 0 for line in self.lines.all())


class PurchaseOrderLine(models.Model):
    """Line items for purchase order"""
    
    po = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='lines')
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name='purchase_order_lines')
    quantity_ordered = models.DecimalField(
        max_digits=12, decimal_places=4,
        validators=[MinValueValidator(0.0001)]
    )
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_price = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    quantity_received = models.DecimalField(
        max_digits=12, decimal_places=4, default=0,
        validators=[MinValueValidator(0)]
    )
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "Purchase Order Line"
        verbose_name_plural = "Purchase Order Lines"
        ordering = ['id']

    def __str__(self):
        return f"{self.item.code} × {self.quantity_ordered}"

    @property
    def remaining(self):
        """Calculate remaining quantity to receive"""
        return self.quantity_ordered - self.quantity_received

    def save(self, *args, **kwargs):
        self.total_price = self.quantity_ordered * self.unit_price
        super().save(*args, **kwargs)
        self.po.update_total()


class PurchaseOrderApproval(models.Model):
    """Approval levels for purchase orders"""
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    po = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='approvals')
    level = models.PositiveSmallIntegerField(help_text="Approval level (1, 2, 3...)")
    approver = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True,
        related_name='po_approvals'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    approved_at = models.DateTimeField(null=True, blank=True)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('po', 'level')
        ordering = ['level']
        verbose_name = "Purchase Order Approval"
        verbose_name_plural = "Purchase Order Approvals"
        indexes = [
            models.Index(fields=['status', 'level']),
        ]

    def __str__(self):
        return f"Level {self.level} - {self.status}"


class GoodsReceipt(models.Model):
    """Goods receipt against a purchase order"""
    
    po = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, related_name='goods_receipts')
    receipt_number = models.CharField(max_length=30, unique=True, editable=False, db_index=True)
    receipt_date = models.DateField(default=timezone.now, db_index=True)
    received_by = models.ForeignKey(
        'auth.User', null=True, on_delete=models.SET_NULL,
        related_name='goods_receipts'
    )
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='goods_receipts')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-receipt_date']
        verbose_name = "Goods Receipt"
        verbose_name_plural = "Goods Receipts"
        indexes = [
            models.Index(fields=['receipt_number']),
            models.Index(fields=['po', 'receipt_date']),
        ]

    def __str__(self):
        return self.receipt_number

    def save(self, *args, **kwargs):
        if not self.receipt_number:
            last = GoodsReceipt.objects.order_by('-id').first()
            num = (last.id + 1) if last else 1
            self.receipt_number = f"GRN-{timezone.now().strftime('%Y%m')}-{num:05d}"
        super().save(*args, **kwargs)

    def update_po_status(self):
        """Update parent PO status based on receipt"""
        if self.po.is_fully_received:
            self.po.status = 'received'
        elif any(line.quantity_received > 0 for line in self.po.lines.all()):
            self.po.status = 'partial'
        self.po.save()
    
    @property
    def total_value(self):
        """Calculate total value of this receipt"""
        total = sum(line.line_total for line in self.lines.all())
        return total


class GoodsReceiptLine(models.Model):
    """Line items for goods receipt"""
    
    receipt = models.ForeignKey(GoodsReceipt, on_delete=models.CASCADE, related_name='lines')
    po_line = models.ForeignKey(PurchaseOrderLine, on_delete=models.PROTECT, related_name='goods_receipt_lines')
    quantity_received = models.DecimalField(
        max_digits=12, decimal_places=4,
        validators=[MinValueValidator(0.0001)]
    )
    lot = models.ForeignKey(Lot, on_delete=models.SET_NULL, null=True, blank=True, related_name='goods_receipt_lines')
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "Goods Receipt Line"
        verbose_name_plural = "Goods Receipt Lines"
        ordering = ['id']

    def __str__(self):
        return f"{self.po_line.item.code} × {self.quantity_received}"

    @property
    def line_total(self):
        """Calculate line total value"""
        return self.quantity_received * self.po_line.unit_price

    def save(self, *args, **kwargs):
        # Check if we're creating a new record
        is_new = not self.pk
        
        super().save(*args, **kwargs)
        
        # Auto-create stock transaction + lot if not exists
        if is_new and not self.lot:
            # Create new lot
            lot = Lot.objects.create(
                item=self.po_line.item,
                batch_number=f"REC-{self.receipt.receipt_number}-{self.id}",
                manufacturing_date=timezone.now().date(),
                expiry_date=timezone.now().date() + timezone.timedelta(days=self.po_line.item.shelf_life_days or 730),
                received_date=timezone.now().date(),
                initial_quantity=self.quantity_received,
                current_quantity=self.quantity_received,
                supplier=self.receipt.po.supplier,
                supplier_batch=f"SUP-{timezone.now().strftime('%Y%m')}"
            )
            self.lot = lot
            self.save(update_fields=['lot'])

        # Stock transaction
        StockTransaction.objects.create(
            transaction_type='receipt',
            item=self.po_line.item,
            lot=self.lot,
            warehouse_to=self.receipt.warehouse,
            quantity=self.quantity_received,
            unit_cost=self.po_line.unit_price,
            reference=self.receipt.receipt_number,
            notes=f"Receipt against {self.receipt.po.po_number}"
        )

        # Update PO line & status
        self.po_line.quantity_received += self.quantity_received
        self.po_line.save()
        self.receipt.update_po_status()


class VendorPerformance(models.Model):
    """
    Track vendor performance metrics over time
    """
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name='performance_records')
    period_start = models.DateField()
    period_end = models.DateField()
    
    # Performance metrics
    orders_count = models.PositiveIntegerField(default=0)
    on_time_deliveries = models.PositiveIntegerField(default=0)
    late_deliveries = models.PositiveIntegerField(default=0)
    damaged_orders = models.PositiveIntegerField(default=0)
    total_order_value = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Calculated metrics
    on_time_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    quality_score = models.DecimalField(
        max_digits=3, decimal_places=2, default=0,
        validators=[MinValueValidator(0), MaxValueValidator(5)]
    )
    
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-period_end']
        unique_together = ('supplier', 'period_start', 'period_end')
        verbose_name = "Vendor Performance"
        verbose_name_plural = "Vendor Performance Records"
        indexes = [
            models.Index(fields=['supplier', 'period_start']),
        ]

    def __str__(self):
        return f"{self.supplier.name} - {self.period_start} to {self.period_end}"

    def save(self, *args, **kwargs):
        # Calculate on-time delivery rate
        if self.orders_count > 0:
            self.on_time_rate = (self.on_time_deliveries / self.orders_count) * 100
        super().save(*args, **kwargs)