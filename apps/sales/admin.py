from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from .models import (
    SalesOrder, SalesOrderLine, SalesInvoice, SalesInvoiceLine,
    SalesShipment, SalesShipmentLine, SalesPayment
)


class SalesOrderLineInline(admin.TabularInline):
    """Inline for sales order lines"""
    model = SalesOrderLine
    extra = 1
    fields = ('item', 'quantity', 'unit', 'unit_price', 'discount_percent', 'total_price', 'warehouse', 'notes')
    readonly_fields = ('total_price',)
    autocomplete_fields = ['item', 'unit', 'warehouse']


class SalesInvoiceLineInline(admin.TabularInline):
    """Inline for sales invoice lines"""
    model = SalesInvoiceLine
    extra = 1
    fields = ('item', 'quantity', 'unit', 'unit_price', 'discount_percent', 'total_price', 'notes')
    readonly_fields = ('total_price',)
    autocomplete_fields = ['item', 'unit']


class SalesShipmentLineInline(admin.TabularInline):
    """Inline for shipment lines"""
    model = SalesShipmentLine
    extra = 1
    fields = ('sales_order_line', 'quantity', 'lot', 'notes')
    autocomplete_fields = ['sales_order_line', 'lot']


class SalesPaymentInline(admin.TabularInline):
    """Inline for payments"""
    model = SalesPayment
    extra = 0
    fields = ('payment_date', 'amount', 'payment_method', 'reference', 'created_by')
    readonly_fields = ('created_by',)
    can_delete = False


@admin.register(SalesOrder)
class SalesOrderAdmin(admin.ModelAdmin):
    list_display = (
        'order_number', 'customer_link', 'order_date', 'expected_ship_date',
        'total_amount_display', 'status_colored', 'created_by'
    )
    list_filter = ('status', 'order_date', 'customer__company')
    search_fields = ('order_number', 'customer__name', 'customer__tin', 'notes')
    date_hierarchy = 'order_date'
    readonly_fields = (
        'order_number', 'subtotal', 'total_amount', 'created_at', 'updated_at',
        'invoice_generated', 'invoice_link'
    )
    autocomplete_fields = ['customer', 'created_by']
    inlines = [SalesOrderLineInline]
    list_per_page = 25
    save_on_top = True
    
    fieldsets = (
        ('Order Information', {
            'fields': ('customer', 'order_number', 'order_date', 'status')
        }),
        ('Dates', {
            'fields': ('expected_ship_date', 'actual_ship_date', 'delivery_date')
        }),
        ('Financial', {
            'fields': ('subtotal', 'discount_amount', 'discount_percent', 
                      'tax_amount', 'tax_rate', 'shipping_amount', 'total_amount_display')
        }),
        ('Shipping', {
            'fields': ('shipping_address', 'shipping_city', 'shipping_country')
        }),
        ('Invoicing', {
            'fields': ('invoice_generated', 'invoice_link')
        }),
        ('Additional Info', {
            'fields': ('notes', 'terms_conditions', 'created_by')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def customer_link(self, obj):
        url = reverse('admin:company_customer_change', args=[obj.customer.id])
        return format_html('<a href="{}">{}</a>', url, obj.customer.name)
    customer_link.short_description = 'Customer'
    customer_link.admin_order_field = 'customer__name'
    
    def total_amount_display(self, obj):
        return format_html('<span style="font-weight: bold;">{:,.2f}</span>', obj.total_amount)
    total_amount_display.short_description = 'Total'
    total_amount_display.admin_order_field = 'total_amount'
    
    def status_colored(self, obj):
        colors = {
            'draft': '#6c757d',
            'confirmed': '#007bff',
            'processing': '#17a2b8',
            'ready_to_ship': '#ffc107',
            'shipped': '#28a745',
            'delivered': '#20c997',
            'invoiced': '#6610f2',
            'closed': '#343a40',
            'cancelled': '#dc3545',
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_colored.short_description = 'Status'
    
    def invoice_link(self, obj):
        if obj.invoice:
            url = reverse('admin:sales_salesinvoice_change', args=[obj.invoice.id])
            return format_html('<a href="{}">{}</a>', url, obj.invoice.invoice_number)
        return '-'
    invoice_link.short_description = 'Invoice'
    
    actions = ['confirm_orders', 'process_orders', 'ship_orders', 'cancel_orders']
    
    def confirm_orders(self, request, queryset):
        updated = queryset.filter(status='draft').update(status='confirmed')
        self.message_user(request, f'{updated} order(s) confirmed.')
    confirm_orders.short_description = "Confirm selected orders"
    
    def process_orders(self, request, queryset):
        updated = queryset.filter(status='confirmed').update(status='processing')
        self.message_user(request, f'{updated} order(s) moved to processing.')
    process_orders.short_description = "Start processing orders"
    
    def ship_orders(self, request, queryset):
        from django.utils import timezone
        updated = queryset.filter(status='processing').update(status='shipped', actual_ship_date=timezone.now().date())
        self.message_user(request, f'{updated} order(s) marked as shipped.')
    ship_orders.short_description = "Mark as shipped"
    
    def cancel_orders(self, request, queryset):
        updated = queryset.exclude(status__in=['shipped', 'delivered', 'closed']).update(status='cancelled')
        self.message_user(request, f'{updated} order(s) cancelled.')
    cancel_orders.short_description = "Cancel orders"


@admin.register(SalesOrderLine)
class SalesOrderLineAdmin(admin.ModelAdmin):
    list_display = ('order_link', 'item', 'quantity', 'unit_price', 'total_price', 'quantity_shipped')
    list_filter = ('order__status', 'item__category')
    search_fields = ('order__order_number', 'item__code', 'item__name')
    autocomplete_fields = ['item', 'unit', 'warehouse', 'order']
    readonly_fields = ('total_price',)  # Only keep fields that exist in the model
    list_per_page = 25
    
    def order_link(self, obj):
        url = reverse('admin:sales_salesorder_change', args=[obj.order.id])
        return format_html('<a href="{}">{}</a>', url, obj.order.order_number)
    order_link.short_description = 'Order'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('order', 'item', 'unit')


@admin.register(SalesInvoice)
class SalesInvoiceAdmin(admin.ModelAdmin):
    list_display = (
        'invoice_number', 'customer_link', 'sales_order_link', 'invoice_date', 
        'due_date', 'total_amount_display', 'paid_amount_display', 'status_colored'
    )
    list_filter = ('status', 'invoice_date', 'customer__company')
    search_fields = ('invoice_number', 'customer__name', 'sales_order__order_number')
    date_hierarchy = 'invoice_date'
    readonly_fields = (
        'invoice_number', 'subtotal', 'tax_amount', 'total_amount', 
        'paid_amount', 'remaining_amount_display', 'payment_percentage_display',
        'created_at', 'updated_at', 'journal_entry_link'
    )
    autocomplete_fields = ['customer', 'sales_order', 'created_by']
    inlines = [SalesInvoiceLineInline, SalesPaymentInline]
    list_per_page = 25
    save_on_top = True
    
    fieldsets = (
        ('Invoice Information', {
            'fields': ('customer', 'sales_order', 'invoice_number', 'invoice_date', 'due_date', 'status')
        }),
        ('Financial', {
            'fields': ('subtotal', 'discount_amount', 'tax_amount', 'tax_rate', 
                      'shipping_amount', 'total_amount_display', 'paid_amount_display',
                      'remaining_amount_display', 'payment_percentage_display')
        }),
        ('Accounting', {
            'fields': ('journal_entry_link',),
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
    
    def customer_link(self, obj):
        url = reverse('admin:company_customer_change', args=[obj.customer.id])
        return format_html('<a href="{}">{}</a>', url, obj.customer.name)
    customer_link.short_description = 'Customer'
    
    def sales_order_link(self, obj):
        if obj.sales_order:
            url = reverse('admin:sales_salesorder_change', args=[obj.sales_order.id])
            return format_html('<a href="{}">{}</a>', url, obj.sales_order.order_number)
        return '-'
    sales_order_link.short_description = 'Sales Order'
    
    def total_amount_display(self, obj):
        return format_html('<span style="font-weight: bold;">{:,.2f}</span>', obj.total_amount)
    total_amount_display.short_description = 'Total'
    
    def paid_amount_display(self, obj):
        return format_html('<span style="color: green;">{:,.2f}</span>', obj.paid_amount)
    paid_amount_display.short_description = 'Paid'
    
    def remaining_amount_display(self, obj):
        remaining = obj.remaining_amount
        if remaining > 0:
            return format_html('<span style="color: red;">{:,.2f}</span>', remaining)
        return format_html('<span style="color: green;">0.00</span>')
    remaining_amount_display.short_description = 'Remaining'
    
    def payment_percentage_display(self, obj):
        pct = obj.payment_percentage
        color = 'green' if pct >= 100 else 'orange' if pct > 0 else 'gray'
        return format_html(
            '<div style="width:100px; background:#e9ecef;">'
            '<div style="background-color:{}; width:{}%; height:10px;"></div>'
            '</div> {:.1f}%',
            color, pct, pct
        )
    payment_percentage_display.short_description = 'Payment Progress'
    
    def status_colored(self, obj):
        colors = {
            'draft': '#6c757d',
            'posted': '#007bff',
            'sent': '#17a2b8',
            'partial': '#ffc107',
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
    status_colored.short_description = 'Status'
    
    def journal_entry_link(self, obj):
        if obj.journal_entry:
            url = reverse('admin:accounting_journalentry_change', args=[obj.journal_entry.id])
            return format_html('<a href="{}">JE-{}</a>', url, obj.journal_entry.id)
        return '-'
    journal_entry_link.short_description = 'Journal Entry'
    
    actions = ['post_invoices', 'send_invoices', 'mark_paid']
    
    def post_invoices(self, request, queryset):
        updated = queryset.filter(status='draft').update(status='posted')
        self.message_user(request, f'{updated} invoice(s) posted.')
    post_invoices.short_description = "Post selected invoices"
    
    def send_invoices(self, request, queryset):
        updated = queryset.filter(status='posted').update(status='sent')
        self.message_user(request, f'{updated} invoice(s) marked as sent.')
    send_invoices.short_description = "Mark as sent"
    
    def mark_paid(self, request, queryset):
        for invoice in queryset:
            invoice.paid_amount = invoice.total_amount
            invoice.status = 'paid'
            invoice.save()
        self.message_user(request, f'{queryset.count()} invoice(s) marked as paid.')
    mark_paid.short_description = "Mark as fully paid"


@admin.register(SalesShipment)
class SalesShipmentAdmin(admin.ModelAdmin):
    list_display = (
        'shipment_number', 'sales_order_link', 'shipment_date', 'delivery_date',
        'carrier', 'tracking_number', 'status_colored'
    )
    list_filter = ('status', 'shipment_date', 'carrier')
    search_fields = ('shipment_number', 'sales_order__order_number', 'tracking_number')
    date_hierarchy = 'shipment_date'
    readonly_fields = ('shipment_number', 'created_at', 'updated_at')
    autocomplete_fields = ['sales_order', 'warehouse', 'created_by']
    inlines = [SalesShipmentLineInline]
    list_per_page = 25
    
    fieldsets = (
        ('Shipment Information', {
            'fields': ('sales_order', 'shipment_number', 'shipment_date', 'delivery_date', 'status')
        }),
        ('Carrier Details', {
            'fields': ('carrier', 'tracking_number', 'shipping_cost')
        }),
        ('Warehouse', {
            'fields': ('warehouse',)
        }),
        ('Address', {
            'fields': ('shipping_address', 'shipping_city', 'shipping_country')
        }),
        ('Additional Info', {
            'fields': ('notes', 'created_by')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def sales_order_link(self, obj):
        url = reverse('admin:sales_salesorder_change', args=[obj.sales_order.id])
        return format_html('<a href="{}">{}</a>', url, obj.sales_order.order_number)
    sales_order_link.short_description = 'Sales Order'
    
    def status_colored(self, obj):
        colors = {
            'pending': '#6c757d',
            'picking': '#17a2b8',
            'packed': '#ffc107',
            'shipped': '#28a745',
            'delivered': '#20c997',
            'cancelled': '#dc3545',
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_colored.short_description = 'Status'


@admin.register(SalesPayment)
class SalesPaymentAdmin(admin.ModelAdmin):
    list_display = ('invoice_link', 'payment_date', 'amount_display', 'payment_method', 'reference', 'created_by')
    list_filter = ('payment_method', 'payment_date')
    search_fields = ('invoice__invoice_number', 'reference', 'notes')
    date_hierarchy = 'payment_date'
    readonly_fields = ('created_at',)
    autocomplete_fields = ['invoice', 'created_by', 'journal_entry']
    list_per_page = 25
    
    fieldsets = (
        ('Payment Information', {
            'fields': ('invoice', 'payment_date', 'amount', 'payment_method', 'reference')
        }),
        ('Accounting', {
            'fields': ('journal_entry',),
            'classes': ('collapse',)
        }),
        ('Additional Info', {
            'fields': ('notes', 'created_by')
        }),
    )
    
    def invoice_link(self, obj):
        url = reverse('admin:sales_salesinvoice_change', args=[obj.invoice.id])
        return format_html('<a href="{}">{}</a>', url, obj.invoice.invoice_number)
    invoice_link.short_description = 'Invoice'
    
    def amount_display(self, obj):
        return format_html('<span style="font-weight: bold;">{:,.2f}</span>', obj.amount)
    amount_display.short_description = 'Amount'