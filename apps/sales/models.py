from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator
from django.contrib.auth.models import User
from decimal import Decimal
from datetime import timedelta

from apps.company.models import Customer
from apps.core.models import Item, Unit, CompanyModel
from apps.inventory.models import Warehouse

# =====================================================
# SALES ORDER
# =====================================================

class SalesOrder(CompanyModel):
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
    expected_ship_date = models.DateField(null=True, blank=True)
    
    # Financial fields
    subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'), editable=False)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('15.00'))
    tax_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'), editable=False)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'), editable=False)
    
    notes = models.TextField(blank=True, null=True)
    terms_conditions = models.TextField(blank=True, null=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-id']

    def __str__(self):
        return self.order_number or f"SO-{self.id}"

    def save(self, *args, **kwargs):
        if not self.order_number:
            last = SalesOrder.objects.order_by('-id').first()
            last_id = last.id if last else 0
            self.order_number = f"SO-{timezone.now().strftime('%Y%m')}-{last_id + 1:05d}"
        super().save(*args, **kwargs)

    def calculate_totals(self):
        lines = self.lines.all()
        self.subtotal = sum(line.total_price for line in lines) if lines.exists() else Decimal('0.00')
        self.tax_amount = self.subtotal * (self.tax_rate / Decimal('100'))
        self.total_amount = self.subtotal + self.tax_amount
        super().save(update_fields=["subtotal", "tax_amount", "total_amount"])

    def update_status_from_lines(self):
        lines = self.lines.all()
        if not lines.exists(): return
        
        total_quantity = sum(line.quantity for line in lines)
        total_shipped = sum(line.quantity_shipped for line in lines)
        
        if total_shipped == 0:
            new_status = 'confirmed' if self.status == 'confirmed' else self.status
        elif total_shipped < total_quantity:
            new_status = 'processing'
        else:
            new_status = 'shipped'
        
        if new_status != self.status:
            self.status = new_status
            self.save(update_fields=['status'])

    def create_invoice(self, user=None):
        if self.status == 'cancelled' or self.invoices.exists():
            return self.invoices.first() if self.invoices.exists() else None

        invoice = SalesInvoice.objects.create(
            company=self.company,
            sales_order=self,
            due_date=timezone.now().date() + timedelta(days=30),
            created_by=user or self.created_by,
        )
        invoice.status = 'posted'
        invoice.save(update_fields=['status'])
        self.status = "invoiced"
        self.save(update_fields=['status'])
        return invoice

class SalesOrderLine(CompanyModel):
    order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey(Item, on_delete=models.PROTECT)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, null=True, blank=True)
    quantity = models.DecimalField(max_digits=12, decimal_places=4, validators=[MinValueValidator(0.0001)])
    quantity_shipped = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    total_price = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    
    @property
    def quantity_remaining(self):
        return self.quantity - self.quantity_shipped

    def save(self, *args, **kwargs):
        self.total_price = self.quantity * self.unit_price
        order = self.order
        super().save(*args, **kwargs)
        if order: order.calculate_totals()

    def delete(self, *args, **kwargs):
        order = self.order
        super().delete(*args, **kwargs)
        if order: order.calculate_totals()

# =====================================================
# SALES INVOICE
# =====================================================

class SalesInvoice(CompanyModel):
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
    fs_number = models.CharField(max_length=15, unique=True, editable=False, null=True, blank=True)
    reference_number = models.CharField(max_length=20, unique=True, editable=False, null=True, blank=True)
    payment_method = models.CharField(max_length=20, choices=(('credit','Credit'), ('cash','Cash')), default='credit')
    notes = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['-invoice_date', '-id']

    def __str__(self):
        return self.invoice_number

    @property
    def remaining_amount(self):
        rem = self.total_amount - self.paid_amount
        return rem if rem > 0 else Decimal('0.00')

    def _generate_sequential_number(self, field_name, prefix, padding):
        if getattr(self, field_name): return
        last_obj = self.__class__.objects.filter(**{f"{field_name}__startswith": prefix}).order_by('-id').first()
        last_val = 0
        if last_obj:
            last_full_number = getattr(last_obj, field_name)
            try:
                last_val = int(last_full_number.split('-')[-1])
            except (ValueError, IndexError):
                last_val = 0
        setattr(self, field_name, f"{prefix}{last_val + 1:0{padding}d}")

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        if is_new:
            prefix = f"INV-{timezone.now().strftime('%Y%m')}-"
            self._generate_sequential_number('invoice_number', prefix, 5)
            self._generate_sequential_number('fs_number', 'FS-', 8)
            ref_prefix = 'CRSI-' if self.payment_method == 'credit' else 'CSI-'
            self._generate_sequential_number('reference_number', ref_prefix, 8)
            if self.sales_order and not self.customer_id:
                self.customer = self.sales_order.customer
                self.tax_rate = self.sales_order.tax_rate

        super().save(*args, **kwargs)

        if is_new and self.sales_order and not self.lines.exists():
            lines_to_create = [
                SalesInvoiceLine(
                    company=self.company, invoice=self, item=line.item,
                    quantity=line.quantity_shipped if line.quantity_shipped > 0 else line.quantity,
                    unit=line.unit, unit_price=line.unit_price
                ) for line in self.sales_order.lines.all()
            ]
            SalesInvoiceLine.objects.bulk_create(lines_to_create)
            self.calculate_totals()

    def calculate_totals(self):
        from django.db.models import Sum
        self.subtotal = self.lines.aggregate(total=Sum('total_price'))['total'] or Decimal('0.00')
        self.tax_amount = self.subtotal * (Decimal(self.tax_rate) / Decimal('100'))
        self.total_amount = self.subtotal + self.tax_amount
        self.save(update_fields=['subtotal', 'tax_amount', 'total_amount'])

class SalesInvoiceLine(CompanyModel):
    invoice = models.ForeignKey(SalesInvoice, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey(Item, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=4)
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    total_price = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)

    def save(self, *args, **kwargs):
        self.total_price = self.quantity * self.unit_price
        inv = self.invoice
        super().save(*args, **kwargs)
        if inv: inv.calculate_totals()

# =====================================================
# SALES SHIPMENT
# =====================================================

class SalesShipment(CompanyModel):
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

class SalesShipmentLine(CompanyModel):
    shipment = models.ForeignKey(SalesShipment, on_delete=models.CASCADE, related_name="lines")
    sales_order_line = models.ForeignKey(SalesOrderLine, on_delete=models.PROTECT, related_name="shipment_lines")
    quantity = models.DecimalField(max_digits=12, decimal_places=4)

# =====================================================
# SALES PAYMENT (Updated name to SalesPayment)
# =====================================================

class SalesPayment(CompanyModel):
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