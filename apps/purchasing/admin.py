from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.contrib import messages
from django.shortcuts import redirect
from django.utils import timezone
from .models import (
    Supplier, PurchaseRequisition, PurchaseRequisitionLine,
    PurchaseOrder, PurchaseOrderLine, PurchaseOrderApproval,
    GoodsReceipt, GoodsReceiptLine, VendorPerformance
)


class PurchaseRequisitionLineInline(admin.TabularInline):
    """Inline for purchase requisition lines"""
    model = PurchaseRequisitionLine
    extra = 1
    fields = ('item', 'quantity', 'unit', 'unit_price_estimate', 'total_estimate', 'notes')
    readonly_fields = ('total_estimate',)
    # Remove autocomplete_fields temporarily
    
    def total_estimate(self, obj):
        if obj.quantity and obj.unit_price_estimate:
            total = float(obj.quantity) * float(obj.unit_price_estimate)
            return f"{total:.2f}"
        return '-'
    total_estimate.short_description = 'Est. Total'


class PurchaseOrderLineInline(admin.TabularInline):
    """Inline for purchase order lines"""
    model = PurchaseOrderLine
    extra = 1
    fields = ('item', 'quantity_ordered', 'unit', 'unit_price', 'tax_rate', 'total_price', 'quantity_received', 'remaining', 'notes')
    readonly_fields = ('total_price', 'remaining')
    # Remove autocomplete_fields temporarily
    
    def remaining(self, obj):
        remaining = obj.remaining
        if remaining > 0:
            return format_html('<span style="color: #856404;">{}</span>', str(remaining))
        return format_html('<span style="color: green;">0</span>')
    remaining.short_description = 'Remaining'


class GoodsReceiptLineInline(admin.TabularInline):
    """Inline for goods receipt lines"""
    model = GoodsReceiptLine
    extra = 1
    fields = ('po_line', 'quantity_received', 'lot', 'notes')
    # Remove autocomplete_fields to fix the error
    # autocomplete_fields = ['po_line']


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'company', 'phone', 'email', 'payment_terms_days', 'performance_rating_display', 'status_badge')
    list_filter = ('company', 'is_active', 'is_preferred', 'country')
    search_fields = ('name', 'code', 'tin', 'tax_id', 'email', 'phone', 'contact_person')
    readonly_fields = ('created_at', 'updated_at', 'total_purchase_orders', 'total_spend')
    list_editable = ('payment_terms_days',)
    list_per_page = 25
    save_on_top = True
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('company', 'name', 'code', 'is_active', 'is_preferred')
        }),
        ('Tax & Registration', {
            'fields': ('tin', 'tax_id', 'registration_number')
        }),
        ('Contact Details', {
            'fields': ('contact_person', 'phone', 'mobile', 'email', 'website', 'address', 'city', 'country')
        }),
        ('Financial', {
            'fields': ('payment_terms_days', 'credit_limit', 'currency')
        }),
        ('Banking', {
            'fields': ('bank_name', 'bank_account', 'bank_branch', 'swift_code'),
            'classes': ('collapse',)
        }),
        ('Performance', {
            'fields': ('performance_rating', 'on_time_delivery_rate', 'quality_rating'),
            'classes': ('collapse',)
        }),
        ('Statistics', {
            'fields': ('total_purchase_orders', 'total_spend'),
            'classes': ('collapse',)
        }),
        ('Notes', {
            'fields': ('notes',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def performance_rating_display(self, obj):
        rating = float(obj.performance_rating or 0)
        stars = '★' * int(rating) + '☆' * (5 - int(rating))
        color = 'green' if rating >= 4 else 'orange' if rating >= 3 else 'red'
        return format_html('<span style="color: {};">{}</span>', color, stars)
    performance_rating_display.short_description = 'Rating'
    
    def status_badge(self, obj):
        if not obj.is_active:
            return format_html('<span style="background-color: #dc3545; color: white; padding: 3px 8px; border-radius: 3px;">Inactive</span>')
        if obj.is_preferred:
            return format_html('<span style="background-color: #28a745; color: white; padding: 3px 8px; border-radius: 3px;">⭐ Preferred</span>')
        return format_html('<span style="background-color: #17a2b8; color: white; padding: 3px 8px; border-radius: 3px;">Active</span>')
    status_badge.short_description = 'Status'
    
    actions = ['activate_suppliers', 'deactivate_suppliers', 'mark_preferred']
    
    def activate_suppliers(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} supplier(s) activated.')
    activate_suppliers.short_description = "Activate selected suppliers"
    
    def deactivate_suppliers(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} supplier(s) deactivated.')
    deactivate_suppliers.short_description = "Deactivate selected suppliers"
    
    def mark_preferred(self, request, queryset):
        updated = queryset.update(is_preferred=True)
        self.message_user(request, f'{updated} supplier(s) marked as preferred.')
    mark_preferred.short_description = "Mark as preferred"


@admin.register(PurchaseRequisition)
class PurchaseRequisitionAdmin(admin.ModelAdmin):
    list_display = ('requisition_number', 'company', 'requested_date', 'required_date', 'item_count', 'total_estimate_display', 'status_badge', 'requested_by')
    list_filter = ('status', 'company', 'requested_date', 'required_date')
    search_fields = ('requisition_number', 'notes', 'requested_by__username')
    date_hierarchy = 'requested_date'
    readonly_fields = ('requisition_number', 'created_at', 'updated_at', 'item_count', 'total_estimate_display')
    raw_id_fields = ['requested_by']
    inlines = [PurchaseRequisitionLineInline]
    list_per_page = 25
    save_on_top = True
    
    fieldsets = (
        ('Requisition Information', {
            'fields': ('company', 'branch', 'requisition_number', 'status')
        }),
        ('Dates', {
            'fields': ('requested_date', 'required_date')
        }),
        ('Summary', {
            'fields': ('item_count', 'total_estimate_display')
        }),
        ('Additional Info', {
            'fields': ('requested_by', 'notes')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def item_count(self, obj):
        return obj.lines.count()
    item_count.short_description = 'Items'
    
    def total_estimate_display(self, obj):
        total = sum(float(line.quantity or 0) * float(line.unit_price_estimate or 0) for line in obj.lines.all())
        return f"{total:.2f}"
    total_estimate_display.short_description = 'Est. Total'
    
    def status_badge(self, obj):
        colors = {
            'draft': '#6c757d',
            'submitted': '#007bff',
            'approved': '#28a745',
            'rejected': '#dc3545',
            'converted': '#fd7e14',
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    actions = ['submit_requisitions', 'approve_requisitions', 'convert_to_po']
    
    def submit_requisitions(self, request, queryset):
        updated = queryset.exclude(status='draft').update(status='submitted')
        self.message_user(request, f'{updated} requisition(s) submitted.')
    submit_requisitions.short_description = "Submit selected requisitions"
    
    def approve_requisitions(self, request, queryset):
        updated = queryset.filter(status='submitted').update(status='approved')
        self.message_user(request, f'{updated} requisition(s) approved.')
    approve_requisitions.short_description = "Approve selected requisitions"
    
    def convert_to_po(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, 'Please select exactly one requisition to convert.', level=messages.ERROR)
            return
        req = queryset.first()
        return redirect(f'/admin/purchasing/purchaseorder/add/?requisition={req.id}')
    convert_to_po.short_description = "Convert to Purchase Order"


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ('po_number', 'supplier_link', 'order_date', 'expected_delivery_date', 'total_amount_display', 'receipt_status', 'status_badge')
    list_filter = ('status', 'company', 'order_date')
    search_fields = ('po_number', 'supplier__name', 'supplier__code', 'notes')
    date_hierarchy = 'order_date'
    readonly_fields = ('po_number', 'total_amount', 'created_at', 'updated_at', 'total_amount_display', 'receipt_progress')
    raw_id_fields = ['supplier', 'requisition', 'approved_by', 'created_by']
    inlines = [PurchaseOrderLineInline]
    list_per_page = 25
    save_on_top = True
    actions = ['send_to_supplier', 'mark_received', 'close_orders', 'cancel_orders']
    
    fieldsets = (
        ('Order Information', {
            'fields': ('company', 'branch', 'po_number', 'supplier', 'requisition', 'status')
        }),
        ('Dates', {
            'fields': ('order_date', 'expected_delivery_date')
        }),
        ('Financial', {
            'fields': ('total_amount_display', 'receipt_progress')
        }),
        ('Approval', {
            'fields': ('approved_by',)
        }),
        ('Additional Info', {
            'fields': ('notes', 'created_by')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if not change:  # If creating new object
            # Auto-generate PO number if not provided
            if not obj.po_number:
                last_po = PurchaseOrder.objects.order_by('-id').first()
                if last_po and last_po.po_number and last_po.po_number.startswith('PO-'):
                    try:
                        last_num = int(last_po.po_number.split('-')[-1])
                        new_num = last_num + 1
                    except:
                        new_num = 1
                else:
                    new_num = 1
                
                today = timezone.now().strftime('%Y%m%d')
                obj.po_number = f"PO-{today}-{new_num:03d}"
            
            # Set created_by to current user
            if not obj.created_by:
                obj.created_by = request.user
        
        super().save_model(request, obj, form, change)
    
    def supplier_link(self, obj):
        url = reverse('admin:purchasing_supplier_change', args=[obj.supplier.id])
        return format_html('<a href="{}">{}</a>', url, obj.supplier.name)
    supplier_link.short_description = 'Supplier'
    supplier_link.admin_order_field = 'supplier__name'
    
    def total_amount_display(self, obj):
        return f"{float(obj.total_amount or 0):.2f}"
    total_amount_display.short_description = 'Total Amount'
    
    def receipt_status(self, obj):
        lines = obj.lines.all()
        if not lines:
            return '-'
        
        total_qty = sum(float(line.quantity_ordered or 0) for line in lines)
        received_qty = sum(float(line.quantity_received or 0) for line in lines)
        
        if total_qty == 0:
            return '-'
        
        percentage = (received_qty / total_qty) * 100 if total_qty > 0 else 0
        
        if percentage >= 100:
            return format_html('<span style="color: green;">✓ Fully Received</span>')
        elif percentage > 0:
            return format_html('<span style="color: orange;">⬇ {:.0f}% Received</span>', percentage)
        return format_html('<span style="color: #6c757d;">⏳ Pending</span>')
    receipt_status.short_description = 'Receipt Status'
    
    def receipt_progress(self, obj):
        lines = obj.lines.all()
        if not lines:
            return "No lines"
        
        html = []
        html.append('<table style="width:100%">')
        html.append('<thead><tr><th>Item</th><th>Progress</th><th>Status</th></tr></thead>')
        html.append('<tbody>')
        
        for line in lines:
            if line.quantity_ordered > 0:
                percentage = (float(line.quantity_received or 0) / float(line.quantity_ordered or 1)) * 100
                color = 'green' if percentage >= 100 else 'orange' if percentage > 0 else 'gray'
                
                html.append('<tr>')
                html.append(f'<td>{line.item}</td>')
                html.append(f'<td>{line.quantity_received} / {line.quantity_ordered}</td>')
                html.append('<td>')
                html.append('<div style="background-color: #e9ecef; width:100px; height:10px; border-radius:5px;">')
                html.append(f'<div style="background-color: {color}; width:{percentage:.0f}%; height:10px; border-radius:5px;"></div>')
                html.append('</div>')
                html.append('</td>')
                html.append('</tr>')
        
        html.append('</tbody>')
        html.append('</table>')
        return format_html(''.join(html))
    receipt_progress.short_description = 'Receipt Progress'
    
    def status_badge(self, obj):
        colors = {
            'draft': '#6c757d',
            'approved': '#28a745',
            'ordered': '#007bff',
            'partial': '#fd7e14',
            'received': '#6610f2',
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
    
    def send_to_supplier(self, request, queryset):
        updated = queryset.filter(status='approved').update(status='ordered')
        self.message_user(request, f'{updated} PO(s) marked as sent to supplier.')
    send_to_supplier.short_description = "Mark as sent to supplier"
    
    def mark_received(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, 'Please select exactly one PO to receive.', level=messages.ERROR)
            return
        po = queryset.first()
        return redirect(f'/admin/purchasing/goodsreceipt/add/?po={po.id}')
    mark_received.short_description = "Create goods receipt"
    
    def close_orders(self, request, queryset):
        updated = queryset.filter(status='received').update(status='closed')
        self.message_user(request, f'{updated} PO(s) closed.')
    close_orders.short_description = "Close orders"
    
    def cancel_orders(self, request, queryset):
        updated = queryset.exclude(status__in=['received', 'closed']).update(status='cancelled')
        self.message_user(request, f'{updated} PO(s) cancelled.')
    cancel_orders.short_description = "Cancel orders"


# Register PurchaseOrderLineAdmin to fix the autocomplete error
@admin.register(PurchaseOrderLine)
class PurchaseOrderLineAdmin(admin.ModelAdmin):
    list_display = ('po_link', 'item', 'quantity_ordered', 'unit_price', 'total_price', 'quantity_received', 'remaining', 'status_indicator')
    list_filter = ('po__supplier', 'po__status')
    search_fields = ('item', 'po__po_number')
    readonly_fields = ('total_price', 'remaining')
    list_per_page = 25
    
    def po_link(self, obj):
        url = reverse('admin:purchasing_purchaseorder_change', args=[obj.po.id])
        return format_html('<a href="{}">{}</a>', url, obj.po.po_number)
    po_link.short_description = 'PO'
    
    def total_price(self, obj):
        return f"{float(obj.total_price or 0):.2f}"
    total_price.short_description = 'Total Price'
    
    def remaining(self, obj):
        return f"{float(obj.remaining or 0):.2f}"
    remaining.short_description = 'Remaining'
    
    def status_indicator(self, obj):
        if obj.remaining <= 0:
            return format_html('<span style="color: green;">✓ Complete</span>')
        elif obj.quantity_received > 0:
            return format_html('<span style="color: orange;">Partial</span>')
        return format_html('<span style="color: #6c757d;">Pending</span>')
    status_indicator.short_description = 'Status'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('po')


@admin.register(PurchaseOrderApproval)
class PurchaseOrderApprovalAdmin(admin.ModelAdmin):
    list_display = ('po', 'level', 'approver', 'status_badge', 'approved_at', 'response_time')
    list_filter = ('status', 'level')
    search_fields = ('po__po_number', 'approver__username', 'comment')
    raw_id_fields = ['po', 'approver']
    readonly_fields = ('approved_at', 'created_at', 'response_time')
    list_per_page = 25
    
    def status_badge(self, obj):
        colors = {
            'pending': '#ffc107',
            'approved': '#28a745',
            'rejected': '#dc3545',
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: {}; padding: 3px 8px; border-radius: 3px;">{}</span>',
            color,
            'black' if obj.status == 'pending' else 'white',
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    def response_time(self, obj):
        if obj.approved_at and obj.created_at:
            delta = obj.approved_at - obj.created_at
            hours = delta.total_seconds() / 3600
            return f'{hours:.1f} hours'
        return '-'


@admin.register(GoodsReceipt)
class GoodsReceiptAdmin(admin.ModelAdmin):
    list_display = ('receipt_number', 'po_link', 'receipt_date', 'warehouse', 'items_count', 'total_value', 'received_by')
    list_filter = ('receipt_date', 'warehouse')
    search_fields = ('receipt_number', 'po__po_number', 'notes')
    date_hierarchy = 'receipt_date'
    readonly_fields = ('receipt_number', 'created_at', 'items_count', 'total_value')
    raw_id_fields = ['po', 'received_by']
    inlines = [GoodsReceiptLineInline]
    list_per_page = 25
    
    fieldsets = (
        ('Receipt Information', {
            'fields': ('po', 'receipt_number', 'receipt_date', 'warehouse')
        }),
        ('Summary', {
            'fields': ('items_count', 'total_value')
        }),
        ('Additional Info', {
            'fields': ('received_by', 'notes')
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    def po_link(self, obj):
        url = reverse('admin:purchasing_purchaseorder_change', args=[obj.po.id])
        return format_html('<a href="{}">{}</a>', url, obj.po.po_number)
    po_link.short_description = 'Purchase Order'
    
    def items_count(self, obj):
        return obj.lines.count()
    items_count.short_description = 'Items'
    
    def total_value(self, obj):
        total = sum(float(line.quantity_received or 0) * float(line.po_line.unit_price or 0) for line in obj.lines.all())
        return f"{total:.2f}"
    total_value.short_description = 'Total Value'


@admin.register(GoodsReceiptLine)
class GoodsReceiptLineAdmin(admin.ModelAdmin):
    list_display = ('receipt', 'po_line', 'item_info', 'quantity_received', 'unit_price', 'line_total', 'lot_link')
    list_filter = ('receipt__receipt_date',)
    search_fields = ('receipt__receipt_number', 'po_line__po__po_number', 'lot')
    raw_id_fields = ['receipt', 'po_line']
    readonly_fields = ('line_total',)
    list_per_page = 25
    
    def item_info(self, obj):
        return obj.po_line.item
    item_info.short_description = 'Item'
    
    def unit_price(self, obj):
        return f"{float(obj.po_line.unit_price or 0):.2f}"
    unit_price.short_description = 'Unit Price'
    
    def line_total(self, obj):
        total = float(obj.quantity_received or 0) * float(obj.po_line.unit_price or 0)
        return f"{total:.2f}"
    line_total.short_description = 'Total'
    
    def lot_link(self, obj):
        if obj.lot:
            return obj.lot
        return '-'


@admin.register(VendorPerformance)
class VendorPerformanceAdmin(admin.ModelAdmin):
    list_display = ('supplier', 'period_start', 'period_end', 'orders_count', 'on_time_rate', 'quality_score')
    list_filter = ('period_start',)
    search_fields = ('supplier__name', 'notes')
    readonly_fields = ('on_time_rate', 'created_at')
    raw_id_fields = ['supplier']
    list_per_page = 25
    
    fieldsets = (
        ('Period', {
            'fields': ('supplier', 'period_start', 'period_end')
        }),
        ('Performance Metrics', {
            'fields': ('orders_count', 'on_time_deliveries', 'late_deliveries', 'damaged_orders', 'total_order_value')
        }),
        ('Calculated', {
            'fields': ('on_time_rate', 'quality_score')
        }),
        ('Notes', {
            'fields': ('notes',)
        }),
    )
    
    def on_time_rate(self, obj):
        rate = obj.on_time_rate
        return f"{rate:.1f}%"
    on_time_rate.short_description = 'On-Time Rate'