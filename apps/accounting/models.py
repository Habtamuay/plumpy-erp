from django.db import models
from django.utils import timezone
from decimal import Decimal
from apps.core.models import CompanyModel


class AccountType(CompanyModel):
    """
    Flexible Account Type model that users can create/modify
    Examples: Asset, Liability, Equity, Income, Expense
    """
    name = models.CharField(max_length=50, unique=True)
    code_prefix = models.CharField(max_length=2, unique=True, help_text="Code prefix for accounts of this type (e.g., 1 for Assets)")
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['code_prefix']
        verbose_name = "Account Type"
        verbose_name_plural = "Account Types"

    def __str__(self):
        return f"{self.name} ({self.code_prefix})"


class AccountGroup(CompanyModel):
    """
    Grouping level for accounts (e.g., Current Assets, Fixed Assets, Current Liabilities)
    Users can create/modify these as needed
    """
    name = models.CharField(max_length=100, unique=True)
    account_type = models.ForeignKey(AccountType, on_delete=models.PROTECT, related_name='groups')
    code_range_start = models.CharField(max_length=10, help_text="Starting code range for this group")
    code_range_end = models.CharField(max_length=10, help_text="Ending code range for this group")
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['display_order', 'name']
        verbose_name = "Account Group"
        verbose_name_plural = "Account Groups"

    def __str__(self):
        return f"{self.name} ({self.code_range_start}-{self.code_range_end})"


class AccountCategory(CompanyModel):
    """
    Detailed category for reporting purposes
    """
    REPORT_CATEGORY_CHOICES = [
        ('balance_sheet', 'Balance Sheet'),
        ('income_statement', 'Income Statement'),
        ('cash_flow', 'Cash Flow'),
        ('other', 'Other'),
    ]

    name = models.CharField(max_length=100, unique=True)
    account_group = models.ForeignKey(AccountGroup, on_delete=models.PROTECT, related_name='categories')
    report_category = models.CharField(max_length=20, choices=REPORT_CATEGORY_CHOICES, default='balance_sheet')
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['display_order', 'name']
        verbose_name = "Account Category"
        verbose_name_plural = "Account Categories"

    def __str__(self):
        return self.name


class Account(CompanyModel):
    """
    Main Chart of Accounts model with flexible typing, grouping, and categorization
    """
    code = models.CharField(max_length=20, unique=True, db_index=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    
    # Hierarchical relationships
    account_type = models.ForeignKey(AccountType, on_delete=models.PROTECT, related_name='accounts')
    account_group = models.ForeignKey(AccountGroup, on_delete=models.PROTECT, related_name='accounts')
    account_category = models.ForeignKey(AccountCategory, on_delete=models.PROTECT, related_name='accounts')
    
    # Parent-child relationship for sub-accounts
    parent = models.ForeignKey(
        'self', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='children'
    )
    
    # Account status and settings
    is_active = models.BooleanField(default=True)
    is_control_account = models.BooleanField(default=False, help_text="Control accounts have sub-accounts")
    allow_manual_entries = models.BooleanField(default=True, help_text="Can users post manual entries to this account")
    
    # Financial tracking
    opening_balance = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    current_balance = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'), editable=False)
    foreign_currency = models.BooleanField(default=False)
    currency_code = models.CharField(max_length=3, blank=True, help_text="ISO currency code if foreign currency")
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['code']
        verbose_name = "Account"
        verbose_name_plural = "Chart of Accounts"
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['account_type', 'is_active']),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"

    def save(self, *args, **kwargs):
        """Auto-set current_balance from opening_balance on creation"""
        if not self.pk:
            self.current_balance = self.opening_balance
        super().save(*args, **kwargs)

    def update_balance(self):
        """Update current balance based on journal entries"""
        from django.db.models import Sum
        from .models import JournalLine  # Import here to avoid circular imports
    
        debit_total = JournalLine.objects.filter(
            account=self,
            debit__gt=0
        ).aggregate(total=Sum('debit'))['total'] or Decimal('0.00')
    
        credit_total = JournalLine.objects.filter(
            account=self,
            credit__gt=0
        ).aggregate(total=Sum('credit'))['total'] or Decimal('0.00')
    
        self.current_balance = self.opening_balance + debit_total - credit_total
        self.save(update_fields=['current_balance'])
    
    @property
    def has_children(self):
        """Check if account has sub-accounts"""
        return self.children.exists()
    
    @property
    def level(self):
        """Get account level in hierarchy (0 for top-level)"""
        level = 0
        parent = self.parent
        while parent:
            level += 1
            parent = parent.parent
        return level


class JournalEntry(CompanyModel):
    """Journal Entry header"""
    company = models.ForeignKey('company.Company', on_delete=models.PROTECT, related_name='journal_entries')
    branch = models.ForeignKey('company.Branch', on_delete=models.PROTECT, null=True, blank=True, related_name='journal_entries')
    entry_date = models.DateField(default=timezone.now, db_index=True)
    reference = models.CharField(max_length=100, blank=True, db_index=True)
    narration = models.TextField(blank=True)
    is_posted = models.BooleanField(default=False, db_index=True)
    posted_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='posted_journals')
    created_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='created_journals')

    class Meta:
        ordering = ['-entry_date', '-id']
        verbose_name = "Journal Entry"
        verbose_name_plural = "Journal Entries"
        indexes = [
            models.Index(fields=['company', 'entry_date']),
            models.Index(fields=['is_posted', 'entry_date']),
        ]

    def __str__(self):
        return f"JE-{self.id} | {self.entry_date} | {self.reference or 'No Ref'}"

    def total_debit(self):
        return self.lines.aggregate(total=models.Sum('debit'))['total'] or Decimal('0.00')

    def total_credit(self):
        return self.lines.aggregate(total=models.Sum('credit'))['total'] or Decimal('0.00')

    def is_balanced(self):
        return self.total_debit() == self.total_credit()


class JournalLine(CompanyModel):
    """Journal Entry lines"""
    journal = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name='lines')
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='journal_lines')  # Make sure this related_name is set
    debit = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    credit = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    narration = models.CharField(max_length=255, blank=True)
    item = models.ForeignKey('core.Item', null=True, blank=True, on_delete=models.SET_NULL, related_name='journal_lines')

    class Meta:
        ordering = ['id']
        verbose_name = "Journal Line"
        verbose_name_plural = "Journal Lines"
        indexes = [
            models.Index(fields=['account', 'journal']),
        ]

    def __str__(self):
        return f"{self.account.code} Dr {self.debit} Cr {self.credit}"


class PurchaseBill(CompanyModel):
    """Purchase Bill (Supplier Invoice)"""
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('posted', 'Posted'),
        ('partial', 'Partially Paid'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
        ('cancelled', 'Cancelled'),
    ]

    supplier = models.ForeignKey('purchasing.Supplier', on_delete=models.PROTECT, related_name='accounting_bills')
    bill_number = models.CharField(max_length=30, unique=True, editable=False, db_index=True)
    bill_date = models.DateField(default=timezone.now, db_index=True)
    due_date = models.DateField()
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    paid_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', db_index=True)
    journal_entry = models.OneToOneField(
        JournalEntry, 
        null=True, 
        blank=True, 
        on_delete=models.SET_NULL, 
        related_name='purchase_bill'
    )
    purchase_order = models.ForeignKey(
        'purchasing.PurchaseOrder', 
        null=True, 
        blank=True, 
        on_delete=models.SET_NULL, 
        related_name='accounting_bills'
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='created_purchase_bills')

    class Meta:
        ordering = ['-bill_date', '-id']
        verbose_name = "Purchase Bill"
        verbose_name_plural = "Purchase Bills"
        indexes = [
            models.Index(fields=['bill_number']),
            models.Index(fields=['status']),
            models.Index(fields=['due_date']),
            models.Index(fields=['supplier', 'bill_date']),
        ]

    def __str__(self):
        return f"{self.bill_number} - {self.supplier.name}"

    def save(self, *args, **kwargs):
        if not self.bill_number:
            last = PurchaseBill.objects.order_by('-id').first()
            num = (last.id + 1) if last else 1
            self.bill_number = f"BILL-{timezone.now().strftime('%Y%m')}-{num:05d}"
        super().save(*args, **kwargs)

    @property
    def remaining_amount(self):
        return self.total_amount - self.paid_amount

    @property
    def is_overdue(self):
        return self.due_date < timezone.now().date() and self.status not in ['paid', 'cancelled']


class PurchaseBillLine(CompanyModel):
    """Line items for Purchase Bill"""
    bill = models.ForeignKey(PurchaseBill, on_delete=models.CASCADE, related_name='lines')
    item = models.ForeignKey('core.Item', on_delete=models.PROTECT, related_name='purchase_bill_lines')
    description = models.CharField(max_length=255, blank=True)
    quantity = models.DecimalField(max_digits=12, decimal_places=4)
    unit = models.ForeignKey('core.Unit', on_delete=models.PROTECT, related_name='purchase_bill_lines')
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=15, decimal_places=2, editable=False)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "Purchase Bill Line"
        verbose_name_plural = "Purchase Bill Lines"
        ordering = ['id']

    def __str__(self):
        return f"{self.item.code} × {self.quantity}"

    def save(self, *args, **kwargs):
        self.line_total = self.quantity * self.unit_price
        super().save(*args, **kwargs)


class Payment(CompanyModel):
    """Payment received from customer or paid to supplier"""
    PAYMENT_TYPE_CHOICES = [
        ('customer', 'Customer Receipt'),
        ('supplier', 'Supplier Payment'),
    ]

    payment_type = models.CharField(max_length=10, choices=PAYMENT_TYPE_CHOICES, db_index=True)
    date = models.DateField(default=timezone.now, db_index=True)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    reference = models.CharField(max_length=100, blank=True, db_index=True)
    customer = models.ForeignKey('company.Customer', null=True, blank=True, on_delete=models.PROTECT, related_name='accounting_payments')
    supplier = models.ForeignKey('purchasing.Supplier', null=True, blank=True, on_delete=models.PROTECT, related_name='accounting_payments')
    journal_entry = models.OneToOneField(
        JournalEntry, 
        null=True, 
        blank=True, 
        on_delete=models.SET_NULL, 
        related_name='accounting_payment'
    )
    reconciled_at = models.DateTimeField(null=True, blank=True)
    reconciled_by = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='reconciled_payments')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='created_accounting_payments')

    class Meta:
        ordering = ['-date', '-id']
        verbose_name = "Payment"
        verbose_name_plural = "Payments"
        indexes = [
            models.Index(fields=['payment_type', 'date']),
            models.Index(fields=['customer']),
            models.Index(fields=['supplier']),
        ]

    def __str__(self):
        if self.payment_type == 'customer' and self.customer:
            return f"Receipt from {self.customer.name} - {self.amount}"
        elif self.payment_type == 'supplier' and self.supplier:
            return f"Payment to {self.supplier.name} - {self.amount}"
        return f"{self.get_payment_type_display()} - {self.amount}"


class ReconciliationAuditLog(CompanyModel):
    """Audit log for payment reconciliation actions"""
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='audit_logs')
    reconciled_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True)
    reconciled_at = models.DateTimeField(auto_now_add=True)
    action = models.CharField(max_length=50, help_text="e.g. 'applied_to_invoice', 'applied_to_bill', 'fully_reconciled'")
    document_number = models.CharField(max_length=50, help_text="Invoice # or Bill #")
    amount_applied = models.DecimalField(max_digits=15, decimal_places=2)
    remaining_after = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-reconciled_at']
        verbose_name = "Reconciliation Audit Log"
        verbose_name_plural = "Reconciliation Audit Logs"
        indexes = [
            models.Index(fields=['reconciled_at']),
            models.Index(fields=['action']),
            models.Index(fields=['payment']),
        ]

    def __str__(self):
        return f"{self.reconciled_at.strftime('%Y-%m-%d %H:%M')} - {self.action} by {self.reconciled_by}"