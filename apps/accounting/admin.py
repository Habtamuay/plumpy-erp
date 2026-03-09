from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from .models import (
    AccountType, AccountGroup, AccountCategory, Account,
    JournalEntry, JournalLine, PurchaseBill, PurchaseBillLine,
    Payment, ReconciliationAuditLog, FiscalPeriod
)


class AccountLineInline(admin.TabularInline):
    model = JournalLine
    extra = 1
    fields = ('account', 'debit', 'credit', 'narration')
    autocomplete_fields = ['account']


class PurchaseBillLineInline(admin.TabularInline):
    model = PurchaseBillLine
    extra = 1
    fields = ('item', 'description', 'quantity', 'unit', 'unit_price', 'line_total', 'notes')
    readonly_fields = ('line_total',)
    autocomplete_fields = ['item', 'unit']


@admin.register(AccountType)
class AccountTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'code_prefix', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'code_prefix', 'description')
    ordering = ('code_prefix',)

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'code_prefix', 'description', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    readonly_fields = ('created_at', 'updated_at')


@admin.register(AccountGroup)
class AccountGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'account_type', 'code_range_start', 'code_range_end', 'display_order', 'is_active')
    list_filter = ('account_type', 'is_active')
    search_fields = ('name', 'description')
    ordering = ('display_order', 'name')
    autocomplete_fields = ['account_type']

    fieldsets = (
        ('Group Information', {
            'fields': ('name', 'account_type', 'description', 'is_active')
        }),
        ('Code Range', {
            'fields': ('code_range_start', 'code_range_end'),
            'description': 'Define the code range for accounts in this group'
        }),
        ('Display', {
            'fields': ('display_order',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    readonly_fields = ('created_at', 'updated_at')


@admin.register(AccountCategory)
class AccountCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'account_group', 'report_category', 'display_order', 'is_active')
    list_filter = ('account_group', 'report_category', 'is_active')
    search_fields = ('name', 'description')
    ordering = ('display_order', 'name')
    autocomplete_fields = ['account_group']

    fieldsets = (
        ('Category Information', {
            'fields': ('name', 'account_group', 'description', 'is_active')
        }),
        ('Reporting', {
            'fields': ('report_category',)
        }),
        ('Display', {
            'fields': ('display_order',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'account_type', 'account_group', 'account_category', 'current_balance_display', 'is_active')
    list_filter = ('account_type', 'account_group', 'account_category', 'is_active', 'is_control_account')
    search_fields = ('code', 'name', 'description')
    ordering = ('code',)
    autocomplete_fields = ['account_type', 'account_group', 'account_category', 'parent']
    readonly_fields = ('current_balance', 'created_at', 'updated_at', 'balance_display')

    fieldsets = (
        ('Account Identification', {
            'fields': ('code', 'name', 'description', 'is_active')
        }),
        ('Classification', {
            'fields': ('account_type', 'account_group', 'account_category', 'parent')
        }),
        ('Account Settings', {
            'fields': ('is_control_account', 'allow_manual_entries')
        }),
        ('Financial', {
            'fields': ('opening_balance', 'current_balance', 'balance_display')
        }),
        ('Foreign Currency', {
            'fields': ('foreign_currency', 'currency_code'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def current_balance_display(self, obj):
        """Display current balance with color coding"""
        try:
            balance = float(obj.current_balance)
            color = 'green' if balance >= 0 else 'red'
            # Format the number first, then pass to format_html
            formatted_balance = f"{balance:,.2f}"
            return format_html(
                '<span style="color: {}; font-weight: bold;">{}</span>',
                color,
                formatted_balance
            )
        except (TypeError, ValueError):
            return obj.current_balance
    current_balance_display.short_description = 'Current Balance'
    current_balance_display.admin_order_field = 'current_balance'

    def balance_display(self, obj):
        """Simple balance display for readonly field"""
        try:
            return f"{float(obj.current_balance):,.2f}"
        except (TypeError, ValueError):
            return str(obj.current_balance)
    balance_display.short_description = 'Formatted Balance'


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ('id', 'entry_date', 'reference', 'journal_display', 'is_posted', 'created_by')
    list_filter = ('is_posted', 'entry_date', 'company')
    search_fields = ('reference', 'narration')
    date_hierarchy = 'entry_date'
    readonly_fields = ('posted_at', 'total_debit_display', 'total_credit_display', 'is_balanced_display')
    inlines = [AccountLineInline]
    autocomplete_fields = ['company', 'branch', 'posted_by', 'created_by']

    fieldsets = (
        ('Journal Information', {
            'fields': ('company', 'branch', 'entry_date', 'reference', 'narration')
        }),
        ('Status', {
            'fields': ('is_posted', 'posted_at', 'posted_by', 'created_by')
        }),
        ('Totals', {
            'fields': ('total_debit_display', 'total_credit_display', 'is_balanced_display'),
            'classes': ('collapse',)
        }),
    )

    def total_debit_display(self, obj):
        return format_html('<span style="font-weight: bold;">{:,.2f}</span>', obj.total_debit())
    total_debit_display.short_description = 'Total Debit'

    def total_credit_display(self, obj):
        return format_html('<span style="font-weight: bold;">{:,.2f}</span>', obj.total_credit())
    total_credit_display.short_description = 'Total Credit'

    def is_balanced_display(self, obj):
        if obj.is_balanced():
            return format_html('<span style="color: green;">✓ Balanced</span>')
        return format_html('<span style="color: red;">✗ Not Balanced</span>')
    is_balanced_display.short_description = 'Balance Status'

    def journal_display(self, obj):
        if obj.is_posted:
            return format_html('<span style="color: green;">{}</span>', obj.reference or f"JE-{obj.id}")
        return format_html('<span style="color: orange;">{}</span>', obj.reference or f"JE-{obj.id}")
    journal_display.short_description = 'Journal'


@admin.register(PurchaseBill)
class PurchaseBillAdmin(admin.ModelAdmin):
    list_display = ('bill_number', 'supplier_link', 'bill_date', 'due_date', 'total_amount_display', 'status_badge', 'journal_entry_link')
    list_filter = ('status', 'bill_date', 'supplier__company')
    search_fields = ('bill_number', 'supplier__name', 'notes')
    date_hierarchy = 'bill_date'
    readonly_fields = ('bill_number', 'total_amount', 'paid_amount', 'remaining_amount_display', 'created_at', 'updated_at')
    autocomplete_fields = ['supplier', 'journal_entry', 'purchase_order', 'created_by']
    inlines = [PurchaseBillLineInline]

    fieldsets = (
        ('Bill Information', {
            'fields': ('supplier', 'purchase_order', 'bill_number', 'bill_date', 'due_date', 'status')
        }),
        ('Financial', {
            'fields': ('total_amount', 'paid_amount', 'remaining_amount_display')
        }),
        ('Journal Entry', {
            'fields': ('journal_entry',),
            'classes': ('collapse',)
        }),
        ('Additional Info', {
            'fields': ('notes', 'created_by')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def supplier_link(self, obj):
        url = reverse('admin:purchasing_supplier_change', args=[obj.supplier.id])
        return format_html('<a href="{}">{}</a>', url, obj.supplier.name)
    supplier_link.short_description = 'Supplier'
    supplier_link.admin_order_field = 'supplier__name'

    def total_amount_display(self, obj):
        """Display total amount - FIXED"""
        try:
            amount = float(obj.total_amount)
            formatted_amount = f"{amount:,.2f}"
            return format_html('<span style="font-weight: bold;">{}</span>', formatted_amount)
        except (TypeError, ValueError):
            return str(obj.total_amount)
    total_amount_display.short_description = 'Total'
    total_amount_display.admin_order_field = 'total_amount'

    def remaining_amount_display(self, obj):
        """Display remaining amount - FIXED"""
        try:
            remaining = float(obj.remaining_amount)
            formatted_remaining = f"{remaining:,.2f}"
            if remaining > 0:
                return format_html('<span style="color: orange; font-weight: bold;">{}</span>', formatted_remaining)
            return format_html('<span style="color: green; font-weight: bold;">{}</span>', formatted_remaining)
        except (TypeError, ValueError):
            return str(obj.remaining_amount)
    remaining_amount_display.short_description = 'Remaining'

    def status_badge(self, obj):
        colors = {
            'draft': '#6c757d',
            'posted': '#007bff',
            'partial': '#fd7e14',
            'paid': '#28a745',
            'overdue': '#dc3545',
            'cancelled': '#6c757d',
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'

    def journal_entry_link(self, obj):
        if obj.journal_entry:
            url = reverse('admin:accounting_journalentry_change', args=[obj.journal_entry.id])
            return format_html('<a href="{}">JE-{}</a>', url, obj.journal_entry.id)
        return '-'
    journal_entry_link.short_description = 'Journal'


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('date', 'payment_type', 'party_display', 'amount_display', 'reference', 'reconciled_badge', 'journal_entry_link')
    list_filter = ('payment_type', 'date', 'reconciled_at')
    search_fields = ('reference', 'notes', 'customer__name', 'supplier__name')
    date_hierarchy = 'date'
    readonly_fields = ('created_at',)
    autocomplete_fields = ['customer', 'supplier', 'journal_entry', 'reconciled_by', 'created_by']

    fieldsets = (
        ('Payment Information', {
            'fields': ('payment_type', 'date', 'amount', 'reference')
        }),
        ('Party', {
            'fields': ('customer', 'supplier')
        }),
        ('Reconciliation', {
            'fields': ('reconciled_at', 'reconciled_by', 'notes')
        }),
        ('Journal Entry', {
            'fields': ('journal_entry',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )

    def party_display(self, obj):
        if obj.customer:
            return f"Customer: {obj.customer.name}"
        elif obj.supplier:
            return f"Supplier: {obj.supplier.name}"
        return "-"
    party_display.short_description = 'Party'

    def amount_display(self, obj):
        """Display amount with color coding - FIXED"""
        try:
            # Convert to float first, then format
            amount = float(obj.amount)
            color = 'green' if obj.payment_type == 'customer' else 'red'
            # Format the number first, then pass to format_html
            formatted_amount = f"{amount:,.2f}"
            return format_html(
                '<span style="color: {}; font-weight: bold;">{}</span>',
                color,
                formatted_amount
            )
        except (TypeError, ValueError):
            return str(obj.amount)
    amount_display.short_description = 'Amount'

    def reconciled_badge(self, obj):
        if obj.reconciled_at:
            return format_html('<span style="color: green;">✓ Reconciled</span>')
        return format_html('<span style="color: orange;">⏳ Pending</span>')
    reconciled_badge.short_description = 'Reconciliation'

    def journal_entry_link(self, obj):
        if obj.journal_entry:
            url = reverse('admin:accounting_journalentry_change', args=[obj.journal_entry.id])
            return format_html('<a href="{}">JE-{}</a>', url, obj.journal_entry.id)
        return '-'
    journal_entry_link.short_description = 'Journal'


@admin.register(ReconciliationAuditLog)
class ReconciliationAuditLogAdmin(admin.ModelAdmin):
    list_display = ('reconciled_at', 'payment', 'action', 'document_number', 'amount_applied', 'reconciled_by')
    list_filter = ('action', 'reconciled_at')
    search_fields = ('document_number', 'notes')
    readonly_fields = ('reconciled_at',)
    autocomplete_fields = ['payment', 'reconciled_by']

    fieldsets = (
        ('Audit Information', {
            'fields': ('payment', 'reconciled_by', 'reconciled_at', 'action')
        }),
        ('Transaction Details', {
            'fields': ('document_number', 'amount_applied', 'remaining_after', 'notes')
        }),
    )


@admin.register(FiscalPeriod)
class FiscalPeriodAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'period_type', 'start_date', 'end_date', 'status_badge', 'closing_balance', 'closed_at')
    list_filter = ('company', 'period_type', 'is_open', 'is_closed', 'start_date')
    search_fields = ('name', 'company__name', 'notes')
    date_hierarchy = 'start_date'
    readonly_fields = ('created_at', 'updated_at', 'closing_balance', 'total_debits', 'total_credits')
    autocomplete_fields = ['company', 'closed_by']

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'company', 'period_type', 'start_date', 'end_date')
        }),
        ('Status', {
            'fields': ('is_open', 'is_closed', 'closed_at', 'closed_by')
        }),
        ('Financial Summary', {
            'fields': ('total_debits', 'total_credits', 'closing_balance'),
            'classes': ('collapse',)
        }),
        ('Additional Info', {
            'fields': ('notes',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def status_badge(self, obj):
        if obj.is_closed:
            return format_html('<span style="color: red;">Closed</span>')
        elif obj.is_open:
            return format_html('<span style="color: green;">Open</span>')
        return format_html('<span style="color: orange;">Pending</span>')
    status_badge.short_description = 'Status'
