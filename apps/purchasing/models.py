from django.db import models
from django.conf import settings
from django.utils import timezone
from decimal import Decimal
from apps.core.models import Item, Unit, CompanyModel  # Import these from your core app


# =====================================================
# SUPPLIER
# =====================================================

class Supplier(CompanyModel):
    company = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50, unique=True)

    tin = models.CharField(max_length=50, blank=True, null=True)
    tax_id = models.CharField(max_length=50, blank=True, null=True)
    registration_number = models.CharField(max_length=100, blank=True, null=True)

    contact_person = models.CharField(max_length=255, blank=True, null=True)
    phone = models.CharField(max_length=50, blank=True, null=True)
    mobile = models.CharField(max_length=50, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    website = models.URLField(blank=True, null=True)

    address = models.TextField(blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True)

    payment_terms_days = models.IntegerField(default=30)
    credit_limit = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    currency = models.CharField(max_length=10, default="ETB")

    bank_name = models.CharField(max_length=255, blank=True, null=True)
    bank_account = models.CharField(max_length=100, blank=True, null=True)
    bank_branch = models.CharField(max_length=255, blank=True, null=True)
    swift_code = models.CharField(max_length=50, blank=True, null=True)

    performance_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    on_time_delivery_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    quality_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)

    total_purchase_orders = models.IntegerField(default=0)
    total_spend = models.DecimalField(max_digits=18, decimal_places=2, default=0)

    is_active = models.BooleanField(default=True)
    is_preferred = models.BooleanField(default=False)

    notes = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.code} - {self.name}"


# =====================================================
# PURCHASE REQUISITION
# =====================================================

class PurchaseRequisition(CompanyModel):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("submitted", "Submitted"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("converted", "Converted"),
    ]

    company = models.CharField(max_length=255)
    branch = models.CharField(max_length=255, blank=True, null=True)

    requisition_number = models.CharField(max_length=50, unique=True)
    requested_date = models.DateField(default=timezone.now)
    required_date = models.DateField(blank=True, null=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.PROTECT, 
        related_name='purchase_requisitions'
    )

    notes = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.requisition_number


class PurchaseRequisitionLine(CompanyModel):
    requisition = models.ForeignKey(
        PurchaseRequisition,
        related_name="lines",
        on_delete=models.CASCADE
    )

    # Changed from CharField to ForeignKey
    item = models.ForeignKey(
        Item, 
        on_delete=models.PROTECT,
        related_name='purchase_requisition_lines'
    )
    unit = models.ForeignKey(
        Unit, 
        on_delete=models.PROTECT,
        related_name='purchase_requisition_lines'
    )
    quantity = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    unit_price_estimate = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    notes = models.TextField(blank=True, null=True)

    @property
    def total_estimate(self):
        """Calculate total estimated value for this line"""
        return (self.quantity or 0) * (self.unit_price_estimate or 0)


# =====================================================
# PURCHASE ORDER
# =====================================================

class PurchaseOrder(CompanyModel):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("approved", "Approved"),
        ("ordered", "Ordered"),
        ("partial", "Partial"),
        ("received", "Received"),
        ("closed", "Closed"),
        ("cancelled", "Cancelled"),
    ]

    company = models.CharField(max_length=255)
    branch = models.CharField(max_length=255, blank=True, null=True)

    po_number = models.CharField(max_length=50, unique=True)
    
    def save(self, *args, **kwargs):
        if not self.po_number:
            # Generate a unique PO number
            last_po = PurchaseOrder.objects.order_by('-id').first()
            if last_po and last_po.po_number and last_po.po_number.startswith('PO-'):
                try:
                    last_num = int(last_po.po_number.split('-')[-1])
                    new_num = last_num + 1
                except:
                    new_num = 1
            else:
                new_num = 1
            
            # Format: PO-YYYYMMDD-001
            today = timezone.now().strftime('%Y%m%d')
            self.po_number = f"PO-{today}-{new_num:03d}"
        
        super().save(*args, **kwargs)

    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='purchase_orders')
    requisition = models.ForeignKey(
        PurchaseRequisition,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='purchase_orders'
    )

    order_date = models.DateField(default=timezone.now)
    expected_delivery_date = models.DateField(blank=True, null=True)
    received_date = models.DateField(blank=True, null=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")

    # Financial fields
    shipping_cost = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    currency = models.CharField(max_length=10, default="ETB")
    payment_terms = models.CharField(max_length=50, blank=True, null=True)
    terms = models.TextField(blank=True, null=True)
    shipping_method = models.CharField(max_length=50, blank=True, null=True)
    shipping_address = models.TextField(blank=True, null=True)
    billing_address = models.TextField(blank=True, null=True)

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="approved_purchase_orders",
        null=True,
        blank=True,
        on_delete=models.PROTECT
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="created_purchase_orders",
        on_delete=models.PROTECT
    )

    notes = models.TextField(blank=True, null=True)

    total_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.po_number

    @property
    def subtotal(self):
        """Calculate subtotal before tax"""
        if not hasattr(self, 'lines') or not self.lines.exists():
            return Decimal('0')
        total = sum(line.subtotal for line in self.lines.all())
        return total

    @property
    def tax_total(self):
        """Calculate total tax amount"""
        if not hasattr(self, 'lines') or not self.lines.exists():
            return Decimal('0')
        total = sum(line.tax_amount for line in self.lines.all())
        return total

    @property
    def grand_total(self):
        """Calculate grand total including all charges"""
        return self.subtotal + self.tax_total + self.shipping_cost - self.discount

class PurchaseOrderLine(CompanyModel):
    po = models.ForeignKey(
        PurchaseOrder,
        related_name="lines",
        on_delete=models.CASCADE
    )

    # Keep both fields temporarily during migration
    item = models.CharField(max_length=255)  # Keep this for now
    item_id = models.IntegerField(null=True, blank=True)  # Add this temporarily
    unit = models.CharField(max_length=50)  # Keep this for now
    unit_id = models.IntegerField(null=True, blank=True)  # Add this temporarily

    quantity_ordered = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    quantity_received = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    unit_price = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    notes = models.TextField(blank=True, null=True)

    def save(self, *args, **kwargs):
        # If we have item_id but not item, populate item from the related object
        if self.item_id and not self.item:
            try:
                from apps.core.models import Item
                item_obj = Item.objects.get(id=self.item_id)
                self.item = f"{item_obj.code} - {item_obj.name}"
            except:
                pass
        
        # If we have unit_id but not unit, populate unit from the related object
        if self.unit_id and not self.unit:
            try:
                from apps.core.models import Unit
                unit_obj = Unit.objects.get(id=self.unit_id)
                self.unit = unit_obj.abbreviation
            except:
                pass
        
        super().save(*args, **kwargs)

    @property
    def subtotal(self):
        """Calculate subtotal for this line"""
        return (self.quantity_ordered or 0) * (self.unit_price or 0)

    @property
    def tax_amount(self):
        """Calculate tax amount for this line"""
        return self.subtotal * (self.tax_rate / 100)

    @property
    def total_price(self):
        """Calculate total price including tax"""
        return self.subtotal + self.tax_amount

    @property
    def remaining(self):
        """Calculate remaining quantity to receive"""
        return (self.quantity_ordered or 0) - (self.quantity_received or 0)


# =====================================================
# PURCHASE ORDER APPROVAL
# =====================================================

class PurchaseOrderApproval(CompanyModel):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]

    po = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='approvals')
    level = models.IntegerField()
    approver = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.PROTECT, 
        related_name='purchase_order_approvals'
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    comment = models.TextField(blank=True, null=True)

    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


# =====================================================
# GOODS RECEIPT
# =====================================================

class GoodsReceipt(CompanyModel):
    po = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, related_name='goods_receipts')
    receipt_number = models.CharField(max_length=50, unique=True)

    receipt_date = models.DateField(default=timezone.now)
    warehouse = models.CharField(max_length=255)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.PROTECT,
        related_name='goods_receipts',
        null=True
    )

    notes = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.receipt_number

    def save(self, *args, **kwargs):
        """Generate receipt number if not exists"""
        if not self.receipt_number:
            # Generate receipt number based on PO and date
            today = timezone.now()
            year = today.strftime('%Y')
            month = today.strftime('%m')
            
            # Get the last receipt for this month
            last_receipt = GoodsReceipt.objects.filter(
                receipt_number__startswith=f"GR-{year}{month}"
            ).order_by('-receipt_number').first()
            
            if last_receipt:
                # Extract the sequence number and increment
                try:
                    # Format: GR-202503-0001
                    last_num = int(last_receipt.receipt_number.split('-')[-1])
                    new_num = last_num + 1
                except (ValueError, IndexError):
                    new_num = 1
            else:
                new_num = 1
            
            # Format with leading zeros (4 digits)
            self.receipt_number = f"GR-{year}{month}-{new_num:04d}"
        
        super().save(*args, **kwargs)


class GoodsReceiptLine(CompanyModel):
    receipt = models.ForeignKey(
        GoodsReceipt,
        related_name="lines",
        on_delete=models.CASCADE
    )

    po_line = models.ForeignKey(
        PurchaseOrderLine, 
        on_delete=models.PROTECT,
        related_name='goods_receipt_lines'
    )
    quantity_received = models.DecimalField(max_digits=14, decimal_places=2)
    lot = models.CharField(max_length=100, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    @property
    def line_total(self):
        """Calculate line total value"""
        return self.quantity_received * self.po_line.unit_price

# =====================================================
# VENDOR PERFORMANCE
# =====================================================

class VendorPerformance(CompanyModel):
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name='performance_records')

    period_start = models.DateField()
    period_end = models.DateField()

    orders_count = models.IntegerField(default=0)
    on_time_deliveries = models.IntegerField(default=0)
    late_deliveries = models.IntegerField(default=0)
    damaged_orders = models.IntegerField(default=0)

    total_order_value = models.DecimalField(max_digits=18, decimal_places=2, default=0)

    quality_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    notes = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def on_time_rate(self):
        if self.orders_count == 0:
            return 0
        return (self.on_time_deliveries / self.orders_count) * 100