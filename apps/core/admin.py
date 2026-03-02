from django.contrib import admin
from django.utils.html import format_html
from .models import Unit, Item


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ('name', 'abbreviation', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'abbreviation')
    readonly_fields = ('created_at', 'updated_at')
    list_editable = ('abbreviation',)
    list_per_page = 25
    
    fieldsets = (
        ('Unit Information', {
            'fields': ('name', 'abbreviation', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).order_by('name')


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'category', 'product_type', 'unit', 'stock_status', 'is_active', 'shelf_life_days')
    list_filter = ('category', 'product_type', 'is_active', 'allergen_peanut')
    search_fields = ('code', 'name', 'peach_code', 'description')
    readonly_fields = ('created_at', 'updated_at', 'stock_status_display')
    list_editable = ('is_active',)
    list_per_page = 25
    autocomplete_fields = ['unit']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('code', 'peach_code', 'name', 'description', 'is_active')
        }),
        ('Classification', {
            'fields': ('category', 'product_type', 'unit')
        }),
        ('RUTF Specific', {
            'fields': ('shelf_life_days', 'min_shelf_life_on_receipt', 'allergen_peanut'),
            'classes': ('collapse',),
            'description': 'Fields specific to RUTF products (Plumpy\'Nut, Plumpy\'Sup)'
        }),
        ('Packaging', {
            'fields': ('pack_size_kg',),
            'classes': ('collapse',),
            'description': 'Packaging specifications'
        }),
        ('Cost & Stock', {
            'fields': ('unit_cost', 'current_stock', 'minimum_stock', 'reorder_point', 'reorder_quantity'),
            'classes': ('wide',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def stock_status(self, obj):
        """Display stock status with color coding"""
        if obj.current_stock <= 0:
            return format_html('<span style="color: red; font-weight: bold;">Out of Stock</span>')
        elif obj.current_stock <= obj.minimum_stock:
            return format_html('<span style="color: orange; font-weight: bold;">Low ({})</span>', obj.current_stock)
        elif obj.current_stock <= obj.reorder_point:
            return format_html('<span style="color: #856404; font-weight: bold;">Reorder ({})</span>', obj.current_stock)
        else:
            return format_html('<span style="color: green; font-weight: bold;">OK ({})</span>', obj.current_stock)
    stock_status.short_description = 'Stock Status'
    stock_status.admin_order_field = 'current_stock'
    
    def stock_status_display(self, obj):
        """Detailed stock information for readonly field"""
        return format_html("""
            <table style="width: 100%;">
                <tr><td>Current Stock:</td><td><strong>{}</strong></td></tr>
                <tr><td>Minimum Stock:</td><td>{}</td></tr>
                <tr><td>Reorder Point:</td><td>{}</td></tr>
                <tr><td>Reorder Quantity:</td><td>{}</td></tr>
                <tr><td>Unit Cost:</td><td>{}</td></tr>
            </table>
        """, 
            obj.current_stock,
            obj.minimum_stock,
            obj.reorder_point,
            obj.reorder_quantity,
            obj.unit_cost
        )
    stock_status_display.short_description = 'Stock Details'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('unit').order_by('code')
    
    actions = ['activate_items', 'deactivate_items', 'update_reorder_points']
    
    def activate_items(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} items activated successfully.')
    activate_items.short_description = "Activate selected items"
    
    def deactivate_items(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} items deactivated successfully.')
    deactivate_items.short_description = "Deactivate selected items"
    
    def update_reorder_points(self, request, queryset):
        for item in queryset:
            # Set reorder point to 150% of minimum stock if not set
            if item.reorder_point == 0 and item.minimum_stock > 0:
                item.reorder_point = item.minimum_stock * 1.5
                item.save()
        self.message_user(request, 'Reorder points updated for selected items.')
    update_reorder_points.short_description = "Update reorder points (150% of min stock)"