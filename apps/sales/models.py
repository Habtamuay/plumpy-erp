from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator
from django.contrib.auth.models import User
from decimal import Decimal

from apps.company.models import Customer
from apps.core.models import Item, Unit
from apps.inventory.models import Warehouse

# =====================================================
# SALES ORDER
# =====================================================

class SalesOrder(models.Model):
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('processing', 'Processing'),
        ('shipped', 'Shipped'),
        ('invoiced', 'Invoiced'),
        ('closed', 'Closed'),
        ('cancelled', 'Cancelled'),
    )

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='sales_orders')
    order_number = models.CharField(max_length=30, unique=True, editable=False)
    order_date = models.DateField(default=timezone.now)
    
    subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=15)
    tax_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    shipping_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-id']

    def __str__(self):
        return self.order_number or f"SO-{self.id}"

    def save(self, *args, **kwargs):
        if not self.order_number:
            last = SalesOrder.objects.order_by('-id').first()
            num = (last.id + 1) if last else 1
            self.order_number = f"SO-{timezone.now().strftime('%Y%m')}-{num:05d}"
        super().save(*args, **kwargs)

    def calculate_totals(self):
        self.subtotal = sum(line.total_price for line in self.lines.all())
        self.discount_amount = self.subtotal * (self.discount_percent / 100)
        discounted_val = self.subtotal - self.discount_amount
        self.tax_amount = discounted_val * (self.tax_rate / 100)
        self.total_amount = discounted_val + self.tax_amount + self.shipping_amount
        super().save(update_fields=["subtotal", "discount_amount", "tax_amount", "total_amount"])

    def create_invoice(self, user=None):
        """Method used by Admin buttons/Views to auto-generate invoice"""
        if self.invoices.exists():
            return self.invoices.first()

        invoice = SalesInvoice.objects.create(
            sales_order=self,
            customer=self.customer,
            due_date=timezone.now().date(),
            tax_rate=self.tax_rate
        )
        # Note: Line creation is now handled in SalesInvoice.save()
        self.status = "invoiced"
        self.save(update_fields=["status"])
        return invoice


class SalesOrderLine(models.Model):
    order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey(Item, on_delete=models.PROTECT)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, null=True, blank=True)
    quantity = models.DecimalField(max_digits=12, decimal_places=4, validators=[MinValueValidator(0.0001)])
    quantity_shipped = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    total_price = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)

    def save(self, *args, **kwargs):
        line_total = self.quantity * self.unit_price
        self.discount_amount = line_total * (self.discount_percent / 100)
        self.total_price = line_total - self.discount_amount
        super().save(*args, **kwargs)
        if self.order:
            self.order.calculate_totals()

# =====================================================
# SALES INVOICE
# =====================================================

class SalesInvoice(models.Model):
    STATUS_CHOICES = (('draft', 'Draft'), ('posted', 'Posted'), ('paid', 'Paid'), ('cancelled', 'Cancelled'))
    
    sales_order = models.ForeignKey(SalesOrder, on_delete=models.SET_NULL, null=True, blank=True, related_name='invoices')
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT)
    invoice_number = models.CharField(max_length=30, unique=True, editable=False)
    invoice_date = models.DateField(default=timezone.now)
    due_date = models.DateField()
    
    subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=15)
    tax_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    paid_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # additional references
    fs_number = models.CharField(max_length=15, unique=True, editable=False, null=True, blank=True)
    reference_number = models.CharField(max_length=20, unique=True, editable=False, null=True, blank=True)

    PAYMENT_METHODS = (('credit','Credit'), ('cash','Cash'))
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='credit')
    
    notes = models.TextField(blank=True, null=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')

    @property
    def remaining_amount(self):
        from decimal import Decimal
        rem = (self.total_amount or Decimal('0')) - (self.paid_amount or Decimal('0'))
        return rem if rem > 0 else Decimal('0')

    @property
    def is_fully_paid(self):
        return self.paid_amount >= self.total_amount

    # Use string reference to avoid circular imports
    journal_entry = models.ForeignKey('accounting.JournalEntry', on_delete=models.SET_NULL, null=True, blank=True)

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        
        # 1. Generate Invoice Number
        if not self.invoice_number:
            last = SalesInvoice.objects.order_by('-id').first()
            num = (last.id + 1) if last else 1
            self.invoice_number = f"INV-{timezone.now().strftime('%Y%m')}-{num:05d}"

        # 2. Autofill from Sales Order if selected but Customer is missing (Admin fix)
        if self.sales_order and not self.customer_id:
            self.customer = self.sales_order.customer
            self.tax_rate = self.sales_order.tax_rate

        # 1. Generate Invoice Number
        if not self.invoice_number:
            last = SalesInvoice.objects.order_by('-id').first()
            num = (last.id + 1) if last else 1
            self.invoice_number = f"INV-{timezone.now().strftime('%Y%m')}-{num:05d}"

        # 2. Autofill from Sales Order if selected but Customer is missing (Admin fix)
        if self.sales_order and not self.customer_id:
            self.customer = self.sales_order.customer
            self.tax_rate = self.sales_order.tax_rate

        # 3. Generate FS and reference numbers
        if not self.fs_number:
            last = SalesInvoice.objects.filter(fs_number__startswith='FS-').order_by('-id').first()
            if last and last.fs_number:
                try:
                    prev = int(last.fs_number.split('-')[1])
                except Exception:
                    prev = 0
            else:
                prev = 0
            self.fs_number = f"FS-{prev+1:08d}"

        if not self.reference_number:
            prefix = 'CRSI' if self.payment_method == 'credit' else 'CSI'
            last = SalesInvoice.objects.filter(reference_number__startswith=prefix).order_by('-id').first()
            if last and last.reference_number:
                try:
                    prev = int(last.reference_number.split('-')[1])
                except Exception:
                    prev = 0
            else:
                prev = 0
            self.reference_number = f"{prefix}-{prev+1:08d}"

        super().save(*args, **kwargs)

        # 4. Autofill Lines from Sales Order (The "Automatic Configuration" fix)
        if is_new and self.sales_order and not self.lines.exists():
            for line in self.sales_order.lines.all():
                SalesInvoiceLine.objects.create(
                    invoice=self,
                    item=line.item,
                    quantity=line.quantity,
                    unit=line.unit,
                    unit_price=line.unit_price,
                    discount_percent=line.discount_percent,
                )
            self.calculate_totals()

    def calculate_totals(self):
        self.subtotal = sum(line.total_price for line in self.lines.all())
        self.tax_amount = self.subtotal * (self.tax_rate / 100)
        self.total_amount = self.subtotal + self.tax_amount
        super().save(update_fields=['subtotal', 'tax_amount', 'total_amount'])

    def __str__(self):
        return self.invoice_number


class SalesInvoiceLine(models.Model):
    invoice = models.ForeignKey(SalesInvoice, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey(Item, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=4)
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    total_price = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)

    def save(self, *args, **kwargs):
        line_total = self.quantity * self.unit_price
        self.discount_amount = line_total * (self.discount_percent / 100)
        self.total_price = line_total - self.discount_amount
        super().save(*args, **kwargs)
        self.invoice.calculate_totals()

# =====================================================
# SALES SHIPMENT
# =====================================================

class SalesShipment(models.Model):
    STATUS_CHOICES = (('pending', 'Pending'), ('shipped', 'Shipped'), ('delivered', 'Delivered'))
    
    sales_order = models.ForeignKey(SalesOrder, on_delete=models.PROTECT, related_name="shipments")
    shipment_number = models.CharField(max_length=30, unique=True, editable=False)
    shipment_date = models.DateField(default=timezone.now)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    def save(self, *args, **kwargs):
        if not self.shipment_number:
            last = SalesShipment.objects.order_by('-id').first()
            num = (last.id + 1) if last else 1
            self.shipment_number = f"SHP-{timezone.now().strftime('%Y%m')}-{num:05d}"
        super().save(*args, **kwargs)


class SalesShipmentLine(models.Model):
    shipment = models.ForeignKey(SalesShipment, on_delete=models.CASCADE, related_name="lines")
    sales_order_line = models.ForeignKey(SalesOrderLine, on_delete=models.PROTECT, related_name="shipment_lines")
    quantity = models.DecimalField(max_digits=12, decimal_places=4)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        so_line = self.sales_order_line
        
        # Calculate shipped qty only from finalized shipments
        total_shipped = sum(l.quantity for l in so_line.shipment_lines.filter(shipment__status="shipped"))
        so_line.quantity_shipped = total_shipped
        so_line.save(update_fields=["quantity_shipped"])

        # Inventory Movement logic
        if self.shipment.status == "shipped":
            from apps.inventory.models_stock import StockMovement
            StockMovement.objects.get_or_create(
                reference=self.shipment.shipment_number,
                item=so_line.item,
                defaults={
                    'warehouse': self.shipment.warehouse,
                    'movement_type': "out",
                    'quantity': self.quantity,
                    'notes': f"Shipment {self.shipment.shipment_number}"
                }
            )

# =====================================================
# SALES PAYMENT
# =====================================================

class SalesPayment(models.Model):
    METHODS = (('cash', 'Cash'), ('bank', 'Bank'), ('mobile', 'Mobile'), ('check', 'Cheque'))
    
    invoice = models.ForeignKey(SalesInvoice, on_delete=models.PROTECT, related_name="payments")
    payment_date = models.DateField(default=timezone.now)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=METHODS)
    reference = models.CharField(max_length=100, blank=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        inv = self.invoice
        inv.paid_amount = sum(p.amount for p in inv.payments.all())
        if inv.paid_amount >= inv.total_amount:
            inv.status = 'paid'
        inv.save(update_fields=["paid_amount", "status"])