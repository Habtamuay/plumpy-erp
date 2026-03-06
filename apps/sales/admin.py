from django.contrib import admin, messages
from django.utils.html import format_html
from django.urls import path, reverse
from django.shortcuts import redirect, get_object_or_404

# FIX: Import the Customer model from the correct app
from apps.company.models import Customer

from .models import (
    SalesOrder, SalesOrderLine,
    SalesInvoice, SalesInvoiceLine,
    SalesShipment, SalesShipmentLine,
    SalesPayment
)
from .forms import SalesPaymentForm
from .utils.invoice_pdf import generate_invoice_pdf

# ============================================
# INLINES
# ============================================

class SalesOrderLineInline(admin.TabularInline):
    model = SalesOrderLine
    extra = 1
    min_num = 1
    fields = ("item", "quantity", "unit", "unit_price", "discount_percent", "warehouse", "total_price")
    readonly_fields = ("total_price",)

class SalesInvoiceLineInline(admin.TabularInline):
    model = SalesInvoiceLine
    extra = 1
    readonly_fields = ("total_price",)

class SalesShipmentLineInline(admin.TabularInline):
    model = SalesShipmentLine
    extra = 1

# ============================================
# MODEL ADMINS
# ============================================

@admin.register(SalesOrder)
class SalesOrderAdmin(admin.ModelAdmin):
    list_display = ("order_number", "customer", "order_date", "status", "total_amount", "create_invoice_button")
    list_filter = ("status", "order_date")
    search_fields = ("order_number", "customer__name")
    readonly_fields = ("order_number", "subtotal", "discount_amount", "tax_amount", "total_amount")
    inlines = [SalesOrderLineInline]

    def create_invoice_button(self, obj):
        """Displays a button to trigger invoice generation directly from the Admin."""
        if obj.status == "invoiced":
            return format_html('<span style="color: #28a745; font-weight: bold;">✓ Invoiced</span>')
        
        # Determine the correct URL based on where the button is being rendered
        url = reverse('admin:create_invoice', args=[obj.id])
        return format_html(
            '<a class="button" href="{}" style="background-color: #79aec8; color: white;">Create Invoice</a>',
            url
        )
    create_invoice_button.short_description = "Actions"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "create-invoice/<int:order_id>/", 
                self.admin_site.admin_view(self.create_invoice_view), 
                name="create_invoice"
            ),
        ]
        return custom_urls + urls

    def create_invoice_view(self, request, order_id):
        order = get_object_or_404(SalesOrder, pk=order_id)
        try:
            # Uses the model method we updated earlier
            invoice = order.create_invoice(request.user)
            
            # If accounting integration is present, trigger journal entry
            if hasattr(invoice, 'create_journal_entry'):
                invoice.create_journal_entry()
            
            messages.success(request, f"Invoice {invoice.invoice_number} created successfully.")
            return redirect(f"admin:sales_salesinvoice_change", invoice.id)
        except Exception as e:
            messages.error(request, f"Error creating invoice: {str(e)}")
            return redirect("admin:sales_salesorder_changelist")


@admin.register(SalesInvoice)
class SalesInvoiceAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "fs_number", "reference_number", "customer", "invoice_date", "status", "total_amount", "print_invoice_button")
    list_filter = ("status", "invoice_date")
    search_fields = ("invoice_number", "customer__name")
    readonly_fields = ("invoice_number", "fs_number", "reference_number", "subtotal", "tax_amount", "total_amount", "paid_amount")
    fields = ("sales_order", "customer", "invoice_date", "due_date", "payment_method", "tax_rate", "notes")
    inlines = [SalesInvoiceLineInline]

    def print_invoice_button(self, obj):
        url = reverse('admin:print_invoice', args=[obj.id])
        return format_html(
            '<a class="button" href="{}" target="_blank" style="background-color: #417690; color: white;">Print PDF</a>',
            url
        )
    print_invoice_button.short_description = "Invoice PDF"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "print-invoice/<int:invoice_id>/", 
                self.admin_site.admin_view(self.print_invoice_pdf_view), 
                name="print_invoice"
            ),
        ]
        return custom_urls + urls

    def print_invoice_pdf_view(self, request, invoice_id):
        invoice = get_object_or_404(SalesInvoice, pk=invoice_id)
        return generate_invoice_pdf(invoice)


@admin.register(SalesShipment)
class SalesShipmentAdmin(admin.ModelAdmin):
    list_display = ("shipment_number", "sales_order", "shipment_date", "status")
    list_filter = ("status", "shipment_date")
    readonly_fields = ("shipment_number",)
    inlines = [SalesShipmentLineInline]


@admin.register(SalesPayment)
class SalesPaymentAdmin(admin.ModelAdmin):
    form = SalesPaymentForm
    list_display = ("invoice", "payment_date", "amount", "payment_method")
    list_filter = ("payment_method", "payment_date")
    class Media:
        js = ('sales/js/payment_form.js',)


