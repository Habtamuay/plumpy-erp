from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from .models import Warehouse, Lot, StockTransaction, CurrentStock


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'warehouse_type', 'location', 'is_active', 'stock_count')
    list_filter = ('is_active', 'warehouse_type')
    search_fields = ('name', 'code', 'location')
    ordering = ('name',)
    list_per_page = 25
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'code', 'warehouse_type', 'is_active')
        }),
        ('Location', {
            'fields': ('location', 'address', 'city', 'country')
        }),
        ('Contact', {
            'fields': ('phone', 'email', 'manager')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def warehouse_type(self, obj):
        return obj.get_warehouse_type_display() if hasattr(obj, 'warehouse_type') else 'Standard'
    warehouse_type.short_description = 'Type'
    
    def stock_count(self, obj):
        count = obj.current_stock.count()
        return format_html('<span style="color: {};">{}</span>', 'green' if count > 0 else 'gray', count)
    stock_count.short_description = 'Stock Items'


@admin.register(Lot)
class LotAdmin(admin.ModelAdmin):
    list_display = ('batch_number', 'item_link', 'quantity_display', 'expiry_status', 'is_active')
    list_filter = ('is_active', 'item__category')  # Remove 'warehouse'
    search_fields = ('batch_number', 'item__code', 'item__name', 'supplier__name')
    autocomplete_fields = ['item', 'supplier']  # Remove 'warehouse'
    readonly_fields = ('created_at', 'updated_at', 'days_to_expire', 'age_days')
    list_per_page = 25
    date_hierarchy = 'expiry_date'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('batch_number', 'item', 'supplier', 'warehouse', 'is_active')
        }),
        ('Dates', {
            'fields': ('manufacturing_date', 'expiry_date', 'received_date')
        }),
        ('Quantities', {
            'fields': ('initial_quantity', 'current_quantity', 'allocated_quantity', 'available_quantity')
        }),
        ('Status', {
            'fields': ('days_to_expire', 'age_days', 'quality_status', 'notes')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def item_link(self, obj):
        url = reverse('admin:core_item_change', args=[obj.item.id])
        return format_html('<a href="{}">{}</a>', url, obj.item.code)
    item_link.short_description = 'Item'
    item_link.admin_order_field = 'item__code'
    
    def quantity_display(self, obj):
        return format_html(
            '<span style="font-weight: bold;">{}</span> / {}',
            obj.current_quantity,
            obj.initial_quantity
        )
    quantity_display.short_description = 'Qty (Current/Initial)'
    
    def expiry_status(self, obj):
        days = obj.days_to_expire
        if days <= 0:
            return format_html('<span style="color: red; font-weight: bold;">⚠ Expired</span>')
        elif days <= 30:
            return format_html('<span style="color: orange; font-weight: bold;">⚠ {} days</span>', days)
        elif days <= 90:
            return format_html('<span style="color: #856404;">{} days</span>', days)
        else:
            return format_html('<span style="color: green;">{} days</span>', days)
    expiry_status.short_description = 'Expiry Status'
    expiry_status.admin_order_field = 'expiry_date'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('item', 'warehouse', 'supplier')


@admin.register(StockTransaction)
class StockTransactionAdmin(admin.ModelAdmin):
    list_display = ('transaction_date', 'transaction_type_colored', 'item_link', 'lot_link', 'quantity_colored', 'reference', 'created_by')
    list_filter = ('transaction_type', 'transaction_date', 'item__category')
    search_fields = ('reference', 'item__code', 'item__name', 'lot__batch_number', 'notes')
    date_hierarchy = 'transaction_date'
    readonly_fields = ('created_at', 'balance_after', 'unit_value')
    autocomplete_fields = ['item', 'lot', 'warehouse_from', 'warehouse_to', 'production_run', 'created_by']
    list_per_page = 25
    
    fieldsets = (
        ('Transaction Information', {
            'fields': ('transaction_type', 'transaction_date', 'reference')
        }),
        ('Item Details', {
            'fields': ('item', 'lot', 'quantity', 'unit_cost', 'unit_value')
        }),
        ('Warehouse', {
            'fields': ('warehouse_from', 'warehouse_to')
        }),
        ('Related Documents', {
            'fields': ('production_run', 'purchase_order', 'sales_order')
        }),
        ('Additional Info', {
            'fields': ('notes', 'created_by', 'balance_after')
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    def transaction_type_colored(self, obj):
        colors = {
            'receipt': 'green',
            'issue': 'red',
            'transfer': 'blue',
            'adjustment': 'orange',
            'return': 'purple',
            'scrap': 'darkred',
        }
        color = colors.get(obj.transaction_type, 'gray')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_transaction_type_display()
        )
    transaction_type_colored.short_description = 'Type'
    
    def item_link(self, obj):
        url = reverse('admin:core_item_change', args=[obj.item.id])
        return format_html('<a href="{}">{}</a>', url, obj.item.code)
    item_link.short_description = 'Item'
    
    def lot_link(self, obj):
        if obj.lot:
            url = reverse('admin:inventory_lot_change', args=[obj.lot.id])
            return format_html('<a href="{}">{}</a>', url, obj.lot.batch_number)
        return '-'
    lot_link.short_description = 'Lot'
    
    def quantity_colored(self, obj):
        color = 'green' if obj.quantity > 0 else 'red'
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.quantity
        )
    quantity_colored.short_description = 'Quantity'
    quantity_colored.admin_order_field = 'quantity'
    
    def unit_value(self, obj):
        return obj.quantity * (obj.unit_cost or 0)
    unit_value.short_description = 'Total Value'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'item', 'lot', 'warehouse_from', 'warehouse_to', 'production_run', 'created_by'
        )


@admin.register(CurrentStock)
class CurrentStockAdmin(admin.ModelAdmin):
    list_display = ('item_link', 'warehouse', 'lot_link', 'quantity_display', 'stock_status', 'value_display')
    list_filter = ('warehouse', 'item__category', 'lot__is_active')
    search_fields = ('item__code', 'item__name', 'warehouse__name', 'lot__batch_number')
    autocomplete_fields = ['item', 'warehouse', 'lot']
    readonly_fields = ('last_updated', 'stock_value')
    list_per_page = 25
    
    fieldsets = (
        ('Stock Information', {
            'fields': ('item', 'warehouse', 'lot', 'quantity')
        }),
        ('Valuation', {
            'fields': ('stock_value', 'last_updated')
        }),
    )
    
    def item_link(self, obj):
        url = reverse('admin:core_item_change', args=[obj.item.id])
        return format_html('<a href="{}">{}</a>', url, obj.item.code)
    item_link.short_description = 'Item'
    item_link.admin_order_field = 'item__code'
    
    def lot_link(self, obj):
        if obj.lot:
            url = reverse('admin:inventory_lot_change', args=[obj.lot.id])
            return format_html('<a href="{}">{}</a>', url, obj.lot.batch_number)
        return '-'
    lot_link.short_description = 'Lot'
    
    def quantity_display(self, obj):
        return format_html(
            '<span style="font-weight: bold;">{}</span> {}',
            obj.quantity,
            obj.item.unit.abbreviation if obj.item.unit else ''
        )
    quantity_display.short_description = 'Quantity'
    
    def stock_status(self, obj):
        if obj.quantity <= 0:
            return format_html('<span style="color: red;">Out of Stock</span>')
        elif obj.quantity < obj.item.minimum_stock:
            return format_html('<span style="color: orange;">Low Stock</span>')
        elif obj.quantity < obj.item.reorder_point:
            return format_html('<span style="color: #856404;">Reorder Needed</span>')
        else:
            return format_html('<span style="color: green;">OK</span>')
    stock_status.short_description = 'Status'
    
    def value_display(self, obj):
        value = obj.quantity * (obj.item.unit_cost or 0)
        return format_html('<span style="font-weight: bold;">{:,.2f}</span>', value)
    value_display.short_description = 'Value'
    value_display.admin_order_field = 'quantity'
    
    def stock_value(self, obj):
        value = obj.quantity * (obj.item.unit_cost or 0)
        return f"{value:,.2f} ETB"
    stock_value.short_description = 'Stock Value'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('item', 'warehouse', 'lot', 'item__unit')


# Custom admin site with additional links
class InventoryAdminSite(admin.AdminSite):
    def get_app_list(self, request):
        app_list = super().get_app_list(request)
        
        # Add custom links to inventory app
        for app in app_list:
            if app['app_label'] == 'inventory':
                # Add Stock Summary Report
                app['models'].append({
                    'name': '📊 Stock Summary Report',
                    'object_name': 'stock_summary',
                    'admin_url': reverse('inventory:stock_summary'),
                    'view_only': True,
                })
                # Add Low Stock Alerts
                app['models'].append({
                    'name': '⚠️ Low Stock Alerts',
                    'object_name': 'low_stock',
                    'admin_url': reverse('inventory:low_stock_alerts'),
                    'view_only': True,
                })
                # Add Inventory Analytics
                app['models'].append({
                    'name': '📈 Inventory Analytics',
                    'object_name': 'analytics',
                    'admin_url': reverse('inventory:inventory_analytics'),
                    'view_only': True,
                })
                # Add Consumption vs BOM Report
                app['models'].append({
                    'name': '📉 Consumption vs BOM',
                    'object_name': 'consumption',
                    'admin_url': reverse('inventory:consumption_vs_bom'),
                    'view_only': True,
                })
                # Add Inventory Trends
                app['models'].append({
                    'name': '📊 Inventory Trends',
                    'object_name': 'trends',
                    'admin_url': reverse('inventory:inventory_trends'),
                    'view_only': True,
                })
                break
        return app_list