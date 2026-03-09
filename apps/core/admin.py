from django.contrib import admin
from django.utils.html import format_html
from django.contrib import messages
from django.db.models import F
from .models import Item, Permission, Role, RolePermission, Unit, UserRole


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
    list_display = ('code', 'name', 'category', 'product_type', 'unit', 'stock_status', 'is_active')
    list_filter = ('category', 'product_type', 'is_active')
    search_fields = ('code', 'name', 'peach_code')
    readonly_fields = ('created_at', 'updated_at')
    list_editable = ('is_active',)
    list_per_page = 25
    autocomplete_fields = ['unit']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('code', 'peach_code', 'name', 'category', 'product_type', 'is_active')
        }),
        ('Unit & Pricing', {
            'fields': ('unit', 'unit_cost')
        }),
        ('Stock Levels', {
            'fields': ('current_stock', 'minimum_stock', 'reorder_point', 'reorder_quantity')
        }),
        ('Additional Info', {
            'fields': ('shelf_life_days', 'allergen_peanut', 'pack_size_kg', 'description'),
            'classes': ('collapse',)
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
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('unit').order_by('code')
    
    # Define actions as simple functions
    actions = ['activate_selected', 'deactivate_selected']
    
    def activate_selected(self, request, queryset):
        """Activate selected items"""
        count = queryset.update(is_active=True)
        self.message_user(request, f'{count} item(s) activated successfully.', messages.SUCCESS)
    activate_selected.short_description = "Activate selected items"
    
    def deactivate_selected(self, request, queryset):
        """Deactivate selected items"""
        count = queryset.update(is_active=False)
        self.message_user(request, f'{count} item(s) deactivated successfully.', messages.SUCCESS)
    deactivate_selected.short_description = "Deactivate selected items"

        
    def update_reorder_points(self, request, queryset):
        """Update reorder points for selected items"""
        count = 0
        for item in queryset:
            # Set reorder point to 150% of minimum stock
            new_reorder_point = item.minimum_stock * 1.5
            if item.reorder_point != new_reorder_point:
                item.reorder_point = new_reorder_point
                item.save()
                count += 1
        
        if count > 0:
            self.message_user(request, f'Updated reorder points for {count} item(s).', messages.SUCCESS)
        else:
            self.message_user(request, 'No items needed reorder point updates.', messages.INFO)
    update_reorder_points.short_description = "Update reorder points (150% of min stock)"


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'is_system_role', 'updated_at')
    list_filter = ('is_system_role', 'company')
    search_fields = ('name', 'description')


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ('module', 'action', 'company', 'updated_at')
    list_filter = ('module', 'action', 'company')
    search_fields = ('module', 'action')


@admin.register(RolePermission)
class RolePermissionAdmin(admin.ModelAdmin):
    list_display = ('role', 'permission')
    list_filter = ('role', 'permission')
    search_fields = ('role__name', 'permission__module', 'permission__action')


@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    list_display = ('user', 'company', 'role', 'updated_at')
    list_filter = ('company', 'role')
    search_fields = ('user__username', 'role__name')
