from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal
from apps.company.models import Customer
from apps.core.models import Item, Unit
from apps.inventory.models import Warehouse


class SalesOrder(models.Model):
    """Sales Order - customer order for products"""
    
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('processing', 'Processing'),
        ('ready_to_ship', 'Ready to Ship'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('invoiced', 'Invoiced'),
        ('closed', 'Closed'),
        ('cancelled', 'Cancelled'),
    )

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='sales_orders')
    order_number = models.CharField(max_length=30, unique=True, editable=False, db_index=True)
    order_date = models.DateField(default=timezone.now, db_index=True)
    expected_ship_date = models.DateField(null=True, blank=True)
    actual_ship_date = models.DateField(null=True, blank=True)
    delivery_date = models.DateField(null=True, blank=True)
    
    # Financials
    subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    discount_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=15.00)
    shipping_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', db_index=True)
    
    # Shipping
    shipping_address = models.TextField(blank=True)
    shipping_city = models.CharField(max_length=100, blank=True)
    shipping_country = models.CharField(max_length=100, blank=True, default="Ethiopia")
    
    # Invoicing
    invoice_generated = models.BooleanField(default=False, editable=False)
    invoice = models.OneToOneField('SalesInvoice', null=True, blank=True, on_delete=models.SET_NULL, related_name='order_invoice')
        
    # Metadata
    notes = models.TextField(blank=True)
    terms_conditions = models.TextField(blank=True)
    created_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, related_name='created_sales_orders')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-order_date', '-id']
        verbose_name = "Sales Order"
        verbose_name_plural = "Sales Orders"
        indexes = [
            models.Index(fields=['order_number']),
            models.Index(fields=['status', 'order_date']),
            models.Index(fields=['customer', 'order_date']),
        ]

    def __str__(self):
        return f"{self.order_number} - {self.customer.name}"

    def save(self, *args, **kwargs):
        if not self.order_number:
            last = SalesOrder.objects.order_by('-id').first()
            num = (last.id + 1) if last else 1
            self.order_number = f"SO-{timezone.now().strftime('%Y%m')}-{num:05d}"
        
        # Calculate totals
        self.calculate_totals()
        
        super().save(*args, **kwargs)

    def calculate_totals(self):
        """Calculate order totals"""
        subtotal = sum(line.total_price for line in self.lines.all())
        self.subtotal = subtotal
        
        # Apply discount
        if self.discount_percent > 0:
            self.discount_amount = subtotal * (self.discount_percent / 100)
        
        discounted_subtotal = subtotal - self.discount_amount
        
        # Calculate tax
        self.tax_amount = discounted_subtotal * (self.tax_rate / 100)
        
        # Final total
        self.total_amount = discounted_subtotal + self.tax_amount + self.shipping_amount
        
        # Update only if this is an existing instance
        if self.pk:
            self.save(update_fields=['subtotal', 'discount_amount', 'tax_amount', 'total_amount'])

    @property
    def is_fully_shipped(self):
        """Check if all items are shipped"""
        return all(line.quantity_shipped >= line.quantity for line in self.lines.all())

    @property
    def is_fully_invoiced(self):
        """Check if order is fully invoiced"""
        return self.invoice_generated and self.invoice


class SalesOrderLine(models.Model):
    """Line items for sales order"""
    
    order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name='lines')
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name='sales_order_lines')
    quantity = models.DecimalField(max_digits=12, decimal_places=4, validators=[MinValueValidator(0.0001)])
    quantity_shipped = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    quantity_invoiced = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    total_price = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    
    # Warehouse for picking
    warehouse = models.ForeignKey(
        Warehouse, 
        on_delete=models.PROTECT, 
        null=True, 
        blank=True,
        help_text="Warehouse to pick from"
    )
    
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "Sales Order Line"
        verbose_name_plural = "Sales Order Lines"
        ordering = ['id']

    def __str__(self):
        return f"{self.item.code} × {self.quantity}"

    def save(self, *args, **kwargs):
        # Calculate line total
        line_total = self.quantity * self.unit_price
        self.discount_amount = line_total * (self.discount_percent / 100)
        self.total_price = line_total - self.discount_amount
        
        super().save(*args, **kwargs)
        self.order.calculate_totals()

    @property
    def remaining_to_ship(self):
        """Calculate remaining quantity to ship"""
        return self.quantity - self.quantity_shipped

    @property
    def remaining_to_invoice(self):
        """Calculate remaining quantity to invoice"""
        return self.quantity - self.quantity_invoiced


class SalesInvoice(models.Model):
    """Sales Invoice for customer billing"""
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('posted', 'Posted'),
        ('sent', 'Sent to Customer'),
        ('partial', 'Partially Paid'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
        ('cancelled', 'Cancelled'),
    ]

    # Relationships
    sales_order = models.ForeignKey(
        SalesOrder, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='invoices'
    )
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='sales_invoices')
    
    # Invoice details
    invoice_number = models.CharField(max_length=30, unique=True, editable=False, db_index=True)
    invoice_date = models.DateField(default=timezone.now, db_index=True)
    due_date = models.DateField()
    
    # Financials
    subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    discount_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=15.00)
    shipping_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    paid_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', db_index=True)
    
    # Accounting link
    journal_entry = models.OneToOneField(
        'accounting.JournalEntry', 
        null=True, 
        blank=True, 
        on_delete=models.SET_NULL,
        related_name='sales_invoice'
    )
    
    # Metadata
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, related_name='created_sales_invoices')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-invoice_date', '-id']
        verbose_name = "Sales Invoice"
        verbose_name_plural = "Sales Invoices"
        indexes = [
            models.Index(fields=['invoice_number']),
            models.Index(fields=['status', 'due_date']),
            models.Index(fields=['customer', 'invoice_date']),
        ]

    def __str__(self):
        return f"{self.invoice_number} - {self.customer.name}"

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            last = SalesInvoice.objects.order_by('-id').first()
            num = (last.id + 1) if last else 1
            self.invoice_number = f"INV-{timezone.now().strftime('%Y%m')}-{num:05d}"
        
        # Calculate totals if this is a new invoice
        if not self.pk:
            self.calculate_totals()
        
        # Auto-set overdue status
        if self.due_date and self.due_date < timezone.now().date():
            if self.status not in ['paid', 'cancelled']:
                self.status = 'overdue'
        
        super().save(*args, **kwargs)

    def calculate_totals(self):
        """Calculate invoice totals from lines"""
        subtotal = sum(line.total_price for line in self.lines.all())
        self.subtotal = subtotal
        self.tax_amount = subtotal * (self.tax_rate / 100)
        self.total_amount = subtotal + self.tax_amount + self.shipping_amount - self.discount_amount
        
        # Update only if this is an existing instance
        if self.pk:
            self.save(update_fields=['subtotal', 'tax_amount', 'total_amount'])

    @property
    def remaining_amount(self):
        """Calculate remaining amount to be paid"""
        return self.total_amount - self.paid_amount

    @property
    def is_fully_paid(self):
        """Check if invoice is fully paid"""
        return self.remaining_amount <= 0

    @property
    def payment_percentage(self):
        """Calculate payment percentage"""
        if self.total_amount == 0:
            return 0
        return (self.paid_amount / self.total_amount) * 100


class SalesInvoiceLine(models.Model):
    """Line items for sales invoice"""
    
    invoice = models.ForeignKey(SalesInvoice, on_delete=models.CASCADE, related_name='lines')
    sales_order_line = models.ForeignKey(
        SalesOrderLine, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='invoice_lines'
    )
    
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name='sales_invoice_lines')
    description = models.CharField(max_length=255, blank=True)
    quantity = models.DecimalField(max_digits=12, decimal_places=4, validators=[MinValueValidator(0.0001)])
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    total_price = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    
    # BOM reference fields
    std_composition_pct = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True)
    std_consumption_per_mt = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    std_wastage_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "Sales Invoice Line"
        verbose_name_plural = "Sales Invoice Lines"
        ordering = ['id']

    def __str__(self):
        return f"{self.item.code} × {self.quantity}"

    def save(self, *args, **kwargs):
        # Calculate line total
        line_total = self.quantity * self.unit_price
        self.discount_amount = line_total * (self.discount_percent / 100)
        self.total_price = line_total - self.discount_amount
        
        super().save(*args, **kwargs)
        self.invoice.calculate_totals()


class SalesShipment(models.Model):
    """Shipment/delivery of sales order items"""
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('picking', 'Picking'),
        ('packed', 'Packed'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]

    sales_order = models.ForeignKey(SalesOrder, on_delete=models.PROTECT, related_name='shipments')
    shipment_number = models.CharField(max_length=30, unique=True, editable=False, db_index=True)
    shipment_date = models.DateField(default=timezone.now)
    delivery_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Shipping details
    carrier = models.CharField(max_length=100, blank=True)
    tracking_number = models.CharField(max_length=100, blank=True)
    shipping_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Warehouse
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='shipments')
    
    # Address
    shipping_address = models.TextField(blank=True)
    shipping_city = models.CharField(max_length=100, blank=True)
    shipping_country = models.CharField(max_length=100, blank=True, default="Ethiopia")
    
    # Metadata
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, related_name='created_shipments')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-shipment_date']
        verbose_name = "Sales Shipment"
        verbose_name_plural = "Sales Shipments"

    def __str__(self):
        return f"SHIP-{self.shipment_number} - {self.sales_order.order_number}"

    def save(self, *args, **kwargs):
        if not self.shipment_number:
            last = SalesShipment.objects.order_by('-id').first()
            num = (last.id + 1) if last else 1
            self.shipment_number = f"SHIP-{timezone.now().strftime('%Y%m')}-{num:05d}"
        super().save(*args, **kwargs)


class SalesShipmentLine(models.Model):
    """Line items for shipment"""
    
    shipment = models.ForeignKey(SalesShipment, on_delete=models.CASCADE, related_name='lines')
    sales_order_line = models.ForeignKey(SalesOrderLine, on_delete=models.PROTECT, related_name='shipment_lines')
    quantity = models.DecimalField(max_digits=12, decimal_places=4, validators=[MinValueValidator(0.0001)])
    
    # Lot tracking
    lot = models.ForeignKey('inventory.Lot', on_delete=models.SET_NULL, null=True, blank=True)
    
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "Shipment Line"
        verbose_name_plural = "Shipment Lines"
        unique_together = ['shipment', 'sales_order_line']

    def __str__(self):
        return f"{self.sales_order_line.item.code} × {self.quantity}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Update shipped quantity on sales order line
        line = self.sales_order_line
        line.quantity_shipped = sum(
            l.quantity for l in line.shipment_lines.filter(shipment__status='shipped')
        )
        line.save(update_fields=['quantity_shipped'])


class SalesPayment(models.Model):
    """Payment received against invoices"""
    
    PAYMENT_METHODS = [
        ('cash', 'Cash'),
        ('bank', 'Bank Transfer'),
        ('check', 'Cheque'),
        ('mobile', 'Mobile Money'),
        ('credit', 'Credit Note'),
    ]

    invoice = models.ForeignKey(SalesInvoice, on_delete=models.PROTECT, related_name='payments')
    payment_date = models.DateField(default=timezone.now)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS)
    reference = models.CharField(max_length=100, blank=True, help_text="Cheque number, transaction ID, etc.")
    
    # Accounting link
    journal_entry = models.OneToOneField(
        'accounting.JournalEntry',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='sales_payment'
    )
    
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-payment_date']
        verbose_name = "Sales Payment"
        verbose_name_plural = "Sales Payments"

    def __str__(self):
        return f"Payment for {self.invoice.invoice_number} - {self.amount}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Update paid amount on invoice
        self.invoice.paid_amount = sum(p.amount for p in self.invoice.payments.all())
        self.invoice.save(update_fields=['paid_amount'])