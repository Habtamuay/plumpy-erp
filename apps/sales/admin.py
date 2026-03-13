from django.contrib import admin
from django.urls import path
from django.shortcuts import get_object_or_404, redirect
from django.utils.html import format_html
from django.urls import reverse
from django import forms
from django.db import transaction
from django.contrib import messages
from django.http import HttpResponse
from django.utils import timezone
from django.db import models

from .models import (
    SalesOrder, SalesOrderLine,
    SalesInvoice, SalesInvoiceLine,
    SalesShipment, SalesShipmentLine,
    SalesPayment
)
from .forms import SalesPaymentForm, SalesInvoiceLineFormSet
from .utils.invoice_pdf import generate_invoice_pdf


# Register SalesOrderLine admin first
@admin.register(SalesOrderLine)
class SalesOrderLineAdmin(admin.ModelAdmin):
    list_display = ['id', 'order_link', 'item_link', 'quantity', 'unit_price', 'total_price']
    list_filter = ['order__order_date']
    search_fields = ['order__order_number', 'item__name', 'item__code']
    raw_id_fields = ['order', 'item', 'unit', 'warehouse']
    readonly_fields = ['total_price']
    autocomplete_fields = ['item', 'unit', 'warehouse']
    
    def order_link(self, obj):
        if obj.order:
            url = reverse('admin:sales_salesorder_change', args=[obj.order.id])
            return format_html('<a href="{}">{}</a>', url, obj.order.order_number)
        return '-'
    order_link.short_description = 'Order'
    
    def item_link(self, obj):
        if obj.item:
            url = reverse('admin:core_item_change', args=[obj.item.id])
            return format_html('<a href="{}">{}</a>', url, obj.item.name)
        return '-'
    item_link.short_description = 'Item'


class SalesOrderLineInline(admin.TabularInline):
    model = SalesOrderLine
    extra = 1
    fields = ['item', 'quantity', 'unit', 'unit_price', 'total_price']
    readonly_fields = ['total_price']
    autocomplete_fields = ['item', 'unit', 'warehouse']


@admin.register(SalesOrder)
class SalesOrderAdmin(admin.ModelAdmin):
    list_display = ['order_number', 'customer_link', 'order_date', 'total_amount', 'status_badge']
    list_filter = ['status', 'order_date']
    search_fields = ['order_number', 'customer__name', 'notes']
    date_hierarchy = 'order_date'
    readonly_fields = ['order_number', 'subtotal', 'tax_amount', 'total_amount']
    raw_id_fields = ['customer', 'created_by']
    inlines = [SalesOrderLineInline]
    list_per_page = 25
    
    fieldsets = (
        ('Order Information', {
            'fields': ('order_number', 'customer', 'order_date', 'expected_ship_date', 'status')
        }),
        ('Financial', {
            'fields': ('subtotal', 'tax_rate', 'tax_amount', 'total_amount')
        }),
        ('Additional Info', {
            'fields': ('notes', 'terms_conditions', 'created_by')
        }),
    )
    
    def customer_link(self, obj):
        if obj.customer:
            url = reverse('admin:company_customer_change', args=[obj.customer.id])
            return format_html('<a href="{}">{}</a>', url, obj.customer.name)
        return '-'
    customer_link.short_description = 'Customer'
    
    def status_badge(self, obj):
        colors = {
            'draft': '#6c757d',
            'confirmed': '#007bff',
            'processing': '#fd7e14',
            'shipped': '#17a2b8',
            'delivered': '#28a745',
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
    status_badge.short_description = 'Status'
    
    actions = ['confirm_orders', 'cancel_orders']
    
    def confirm_orders(self, request, queryset):
        updated = queryset.update(status='confirmed')
        self.message_user(request, f'{updated} orders confirmed.')
    confirm_orders.short_description = "Confirm selected orders"
    
    def cancel_orders(self, request, queryset):
        updated = queryset.update(status='cancelled')
        self.message_user(request, f'{updated} orders cancelled.')
    cancel_orders.short_description = "Cancel selected orders"


class SalesInvoiceLineInline(admin.TabularInline):
    model = SalesInvoiceLine
    formset = SalesInvoiceLineFormSet
    extra = 1
    fields = ['item', 'quantity', 'unit', 'unit_price', 'total_price']
    readonly_fields = ['total_price']
    autocomplete_fields = ['item', 'unit']


# Register SalesInvoiceLine admin
@admin.register(SalesInvoiceLine)
class SalesInvoiceLineAdmin(admin.ModelAdmin):
    list_display = ['id', 'invoice_link', 'item_link', 'quantity', 'unit_price', 'total_price']
    list_filter = ['invoice__invoice_date']
    search_fields = ['invoice__invoice_number', 'item__name', 'item__code']
    raw_id_fields = ['invoice', 'item', 'unit']
    readonly_fields = ['total_price']
    autocomplete_fields = ['item', 'unit']
    
    def invoice_link(self, obj):
        if obj.invoice:
            url = reverse('admin:sales_salesinvoice_change', args=[obj.invoice.id])
            return format_html('<a href="{}">{}</a>', url, obj.invoice.invoice_number)
        return '-'
    invoice_link.short_description = 'Invoice'
    
    def item_link(self, obj):
        if obj.item:
            url = reverse('admin:core_item_change', args=[obj.item.id])
            return format_html('<a href="{}">{}</a>', url, obj.item.name)
        return '-'
    item_link.short_description = 'Item'


class SalesInvoiceAdminForm(forms.ModelForm):
    """Custom form for SalesInvoice admin to handle paid amount manually"""
    
    class Meta:
        model = SalesInvoice
        fields = '__all__'
        widgets = {
            'invoice_date': forms.DateInput(attrs={'type': 'date'}),
            'due_date': forms.DateInput(attrs={'type': 'date'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make paid_amount manually editable
        self.fields['paid_amount'].help_text = "Enter advance payment amount"
    
    def clean(self):
        cleaned_data = super().clean()
        total_amount = cleaned_data.get('total_amount') or 0
        paid_amount = cleaned_data.get('paid_amount') or 0
        
        if paid_amount > total_amount:
            raise forms.ValidationError(f"Paid amount cannot exceed total amount ({total_amount})")
        
        return cleaned_data


@admin.register(SalesInvoice)
class SalesInvoiceAdmin(admin.ModelAdmin):
    form = SalesInvoiceAdminForm
    list_display = ['invoice_number', 'customer_link', 'invoice_date', 'due_date', 'total_amount_display', 'paid_amount_display', 'remaining_display', 'status_badge', 'payment_method_display']
    list_filter = ['status', 'invoice_date', 'due_date', 'payment_method']
    search_fields = ['invoice_number', 'customer__name', 'notes']
    date_hierarchy = 'invoice_date'
    readonly_fields = ['invoice_number', 'subtotal', 'tax_amount', 'total_amount', 'remaining_calculation']
    raw_id_fields = ['customer', 'sales_order']
    inlines = [SalesInvoiceLineInline]
    list_per_page = 25
    save_on_top = True
    
    fieldsets = (
        ('Invoice Information', {
            'fields': ('invoice_number', 'customer', 'sales_order', 'invoice_date', 'due_date', 'payment_method')
        }),
        ('Financial', {
            'fields': ('subtotal', 'tax_rate', 'tax_amount', 'total_amount'),
            'description': 'Subtotal is sum of line items before tax. Tax is calculated at {tax_rate}%. Total includes tax.'
        }),
        ('Payment', {
            'fields': ('paid_amount', 'remaining_calculation', 'status'),
            'description': 'Enter advance payment amount in the "Paid amount" field. Remaining balance will be calculated automatically.'
        }),
        ('Additional Info', {
            'fields': ('notes',)
        }),
    )
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('print-invoice/<int:invoice_id>/',
                 self.admin_site.admin_view(self.print_invoice_pdf_view),
                 name='sales_salesinvoice_print_invoice'),
        ]
        return custom_urls + urls
    
    def print_invoice_pdf_view(self, request, invoice_id):
        """View to print invoice as PDF"""
        invoice = get_object_or_404(SalesInvoice, id=invoice_id)
        
        try:
            # Generate PDF bytes
            pdf_bytes = generate_invoice_pdf(invoice)
            
            # Create proper HttpResponse
            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = f'inline; filename="invoice_{invoice.invoice_number}.pdf"'
            response['Content-Length'] = len(pdf_bytes)
            response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
            
            return response
            
        except Exception as e:
            messages.error(request, f"Error generating PDF: {str(e)}")
            return redirect('admin:sales_salesinvoice_change', object_id=invoice_id)
    
    def customer_link(self, obj):
        if obj.customer:
            url = reverse('admin:company_customer_change', args=[obj.customer.id])
            return format_html('<a href="{}">{}</a>', url, obj.customer.name)
        return '-'
    customer_link.short_description = 'Customer'
    
    def total_amount_display(self, obj):
        return format_html('<span style="font-weight: bold;">{}</span>', f"{obj.total_amount:,.2f}")
    total_amount_display.short_description = 'Total'
    total_amount_display.admin_order_field = 'total_amount'
    
    def paid_amount_display(self, obj):
        color = 'green' if obj.paid_amount >= obj.total_amount else 'orange'
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, f"{obj.paid_amount:,.2f}")
    paid_amount_display.short_description = 'Paid'
    paid_amount_display.admin_order_field = 'paid_amount'
    
    def remaining_display(self, obj):
        remaining = obj.total_amount - obj.paid_amount
        if remaining <= 0:
            return format_html('<span style="color: green;">Fully Paid</span>')
        return format_html('<span style="color: red; font-weight: bold;">{}</span>', f"{remaining:,.2f}")
    remaining_display.short_description = 'Remaining'
    
    def remaining_calculation(self, obj):
        remaining = obj.total_amount - obj.paid_amount
        if remaining <= 0:
            return format_html(
                '<span style="color: green; font-weight: bold;">Fully Paid</span><br>'
                '<small>Total: {} | Paid: {}</small>',
                f"{obj.total_amount:,.2f}", f"{obj.paid_amount:,.2f}"
            )
        return format_html(
            '<span style="color: red; font-weight: bold;">Remaining: {}</span><br>'
            '<small>Total: {} - Paid: {} = {}</small>',
            f"{remaining:,.2f}",
            f"{obj.total_amount:,.2f}",
            f"{obj.paid_amount:,.2f}",
            f"{remaining:,.2f}"
        )
    remaining_calculation.short_description = 'Remaining Balance'
    
    def payment_method_display(self, obj):
        if obj.payment_method:
            return dict(SalesInvoice.PAYMENT_METHODS).get(obj.payment_method, obj.payment_method)
        return '-'
    payment_method_display.short_description = 'Payment Method'
    
    def status_badge(self, obj):
        colors = {
            'draft': '#6c757d',
            'sent': '#17a2b8',
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
    
    actions = ['mark_as_paid', 'mark_as_partial', 'mark_as_cancelled', 'print_invoices']
    
    def mark_as_paid(self, request, queryset):
        for invoice in queryset:
            invoice.paid_amount = invoice.total_amount
            invoice.status = 'paid'
            invoice.save()
        self.message_user(request, f'{queryset.count()} invoices marked as paid.')
    mark_as_paid.short_description = "Mark selected as paid"
    
    def mark_as_partial(self, request, queryset):
        queryset.update(status='partial')
        self.message_user(request, f'{queryset.count()} invoices marked as partial.')
    mark_as_partial.short_description = "Mark selected as partial"
    
    def mark_as_cancelled(self, request, queryset):
        queryset.update(status='cancelled')
        self.message_user(request, f'{queryset.count()} invoices cancelled.')
    mark_as_cancelled.short_description = "Cancel selected invoices"
    
    def print_invoices(self, request, queryset):
        if queryset.count() == 1:
            return redirect('admin:sales_salesinvoice_print_invoice', invoice_id=queryset.first().id)
        else:
            messages.warning(request, 'Please select only one invoice to print.')
    print_invoices.short_description = "Print selected invoice"
    
    def save_model(self, request, obj, form, change):
        """Save the invoice and calculate remaining balance"""
        if not obj.invoice_number:
            obj.invoice_number = self.generate_invoice_number()
        super().save_model(request, obj, form, change)
    
    def generate_invoice_number(self):
        """Generate a unique invoice number"""
        last_invoice = SalesInvoice.objects.order_by('-id').first()
        if last_invoice:
            try:
                last_num = int(last_invoice.invoice_number.split('-')[-1])
                new_num = last_num + 1
            except (ValueError, AttributeError):
                new_num = 1
        else:
            new_num = 1
        today = timezone.now()
        return f"INV-{today.strftime('%Y%m')}-{new_num:05d}"


class SalesShipmentLineInline(admin.TabularInline):
    model = SalesShipmentLine
    extra = 1
    fields = ['sales_order_line', 'quantity']
    autocomplete_fields = ['sales_order_line']


@admin.register(SalesShipment)
class SalesShipmentAdmin(admin.ModelAdmin):
    list_display = ['shipment_number', 'sales_order_link', 'shipment_date', 'warehouse', 'status_badge']
    list_filter = ['status', 'shipment_date']
    search_fields = ['shipment_number', 'sales_order__order_number', 'tracking_number']
    date_hierarchy = 'shipment_date'
    readonly_fields = ['shipment_number']
    raw_id_fields = ['sales_order', 'warehouse']
    inlines = [SalesShipmentLineInline]
    list_per_page = 25
    
    fieldsets = (
        ('Shipment Information', {
            'fields': ('shipment_number', 'sales_order', 'warehouse', 'shipment_date', 'status')
        }),
        ('Delivery Details', {
            'fields': ('carrier', 'tracking_number', 'delivery_date')
        }),
        ('Additional Info', {
            'fields': ('notes',)
        }),
    )
    
    def sales_order_link(self, obj):
        if obj.sales_order:
            url = reverse('admin:sales_salesorder_change', args=[obj.sales_order.id])
            return format_html('<a href="{}">{}</a>', url, obj.sales_order.order_number)
        return '-'
    sales_order_link.short_description = 'Sales Order'
    
    def status_badge(self, obj):
        colors = {
            'draft': '#6c757d',
            'shipped': '#17a2b8',
            'delivered': '#28a745',
            'cancelled': '#dc3545',
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    actions = ['mark_as_shipped', 'mark_as_delivered']
    
    def mark_as_shipped(self, request, queryset):
        queryset.update(status='shipped')
        self.message_user(request, f'{queryset.count()} shipments marked as shipped.')
    mark_as_shipped.short_description = "Mark selected as shipped"
    
    def mark_as_delivered(self, request, queryset):
        queryset.update(status='delivered', delivery_date=timezone.now().date())
        self.message_user(request, f'{queryset.count()} shipments marked as delivered.')
    mark_as_delivered.short_description = "Mark selected as delivered"


@admin.register(SalesShipmentLine)
class SalesShipmentLineAdmin(admin.ModelAdmin):
    list_display = ['id', 'shipment_link', 'order_line_link', 'quantity']
    search_fields = ['shipment__shipment_number', 'sales_order_line__order__order_number']
    raw_id_fields = ['shipment', 'sales_order_line']
    
    def shipment_link(self, obj):
        if obj.shipment:
            url = reverse('admin:sales_saleshipment_change', args=[obj.shipment.id])
            return format_html('<a href="{}">{}</a>', url, obj.shipment.shipment_number)
        return '-'
    shipment_link.short_description = 'Shipment'
    
    def order_line_link(self, obj):
        if obj.sales_order_line:
            url = reverse('admin:sales_salesorderline_change', args=[obj.sales_order_line.id])
            return format_html('<a href="{}">Order Line #{}</a>', url, obj.sales_order_line.id)
        return '-'
    order_line_link.short_description = 'Order Line'


@admin.register(SalesPayment)
class SalesPaymentAdmin(admin.ModelAdmin):
    form = SalesPaymentForm
    list_display = ['id', 'invoice_link', 'payment_date', 'amount_display', 'payment_method', 'reference']
    list_filter = ['payment_method', 'payment_date']
    search_fields = ['invoice__invoice_number', 'reference', 'notes']
    date_hierarchy = 'payment_date'
    readonly_fields = []
    raw_id_fields = ['invoice']
    list_per_page = 25
    
    fieldsets = (
        ('Payment Information', {
            'fields': ('invoice', 'payment_date', 'amount', 'payment_method', 'reference')
        }),
        ('Additional Info', {
            'fields': ('notes',)
        }),
    )
    
    def invoice_link(self, obj):
        if obj.invoice:
            url = reverse('admin:sales_salesinvoice_change', args=[obj.invoice.id])
            return format_html('<a href="{}">{}</a>', url, obj.invoice.invoice_number)
        return '-'
    invoice_link.short_description = 'Invoice'
    
    def amount_display(self, obj):
        return format_html('<span style="font-weight: bold;">{}</span>', f"{obj.amount:,.2f}")
    amount_display.short_description = 'Amount'
    
    def save_model(self, request, obj, form, change):
        """Save payment and update invoice paid amount"""
        with transaction.atomic():
            super().save_model(request, obj, form, change)
            
            # Update invoice paid amount
            if obj.invoice:
                invoice = obj.invoice
                # Recalculate total paid from all payments
                total_paid = invoice.payments.aggregate(total=models.Sum('amount'))['total'] or 0
                invoice.paid_amount = total_paid
                
                if invoice.paid_amount >= invoice.total_amount:
                    invoice.status = 'paid'
                elif invoice.paid_amount > 0:
                    invoice.status = 'partial'
                invoice.save()