from django.contrib import admin
from django.utils.html import format_html
from django.core.exceptions import ValidationError
from django.contrib import messages
from django.utils import timezone
from django.urls import reverse
from django.shortcuts import redirect
from django.db import transaction
from decimal import Decimal
from .models import BOM, BOMLine, ProductionRun, InventoryMovement


class BOMLineInline(admin.TabularInline):
    """Inline for BOM lines"""
    model = BOMLine
    extra = 3
    fields = (
        'sequence',
        'component',
        'quantity_per_kg',
        'unit',
        'wastage_percentage',
        'cost_display',
        'notes',
    )
    readonly_fields = ('cost_display',)
    autocomplete_fields = ['component', 'unit']
    
    def cost_display(self, obj):
        """Display cost per kg for this component"""
        if obj.component and obj.component.unit_cost:
            cost = obj.quantity_per_kg * obj.component.unit_cost
            return format_html('{:,.2f} ETB', cost)
        return '-'
    cost_display.short_description = 'Cost/kg'


@admin.register(BOM)
class BOMAdmin(admin.ModelAdmin):
    list_display = (
        'product_link',
        'version',
        'is_active',
        'effective_from',
        'base_quantity',
        'components_count',
        'material_cost_display',
        'total_cost_display',
        'is_current',
    )
    list_filter = (
        'is_active',
        'effective_from',
        'product__category',
        'product__product_type',
    )
    search_fields = (
        'product__code',
        'product__name',
        'notes',
        'version',
    )
    ordering = ('-effective_from', '-version')
    date_hierarchy = 'effective_from'
    list_per_page = 25
    readonly_fields = ('created_at', 'updated_at', 'components_count')
    autocomplete_fields = ['product']

    fieldsets = (
        ('Basic Information', {
            'fields': (
                'product',
                'version',
                'is_active',
                'effective_from',
                'base_quantity',
                'notes',
            ),
            'classes': ('wide',),
        }),
        ('Cost Summary', {
            'fields': (
                'total_material_cost',
                'components_count',
            ),
            'classes': ('collapse',),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    inlines = [BOMLineInline]

    def product_link(self, obj):
        """Link to the product item"""
        url = reverse('admin:core_item_change', args=[obj.product.id])
        return format_html('<a href="{}">{}</a>', url, obj.product.code)
    product_link.short_description = 'Product'
    product_link.admin_order_field = 'product__code'

    def components_count(self, obj):
        """Count of components in this BOM"""
        return obj.lines.count()
    components_count.short_description = 'Components'

    def material_cost_display(self, obj):
        """Display material cost per base quantity"""
        try:
            cost = obj.total_material_cost_per_base
            return format_html('{:,.2f} ETB', cost)
        except (AttributeError, TypeError):
            return "—"
    material_cost_display.short_description = 'Material Cost'

    def total_cost_display(self, obj):
        """Display total cost (material + labor + overhead)"""
        try:
            cost = obj.total_material_cost_per_base
            return format_html('<span style="font-weight: bold;">{:,.2f} ETB</span>', cost)
        except (AttributeError, TypeError):
            return "—"
    total_cost_display.short_description = 'Total Cost'

    @admin.display(description="Current?", boolean=True)
    def is_current(self, obj):
        return obj.is_active and obj.effective_from <= timezone.now().date()

    actions = ['activate_boms', 'deactivate_boms', 'duplicate_bom']

    def activate_boms(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} BOM(s) activated successfully.')
    activate_boms.short_description = "Activate selected BOMs"

    def deactivate_boms(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} BOM(s) deactivated successfully.')
    deactivate_boms.short_description = "Deactivate selected BOMs"

    def duplicate_bom(self, request, queryset):
        """Create a copy of selected BOM with new version"""
        if queryset.count() != 1:
            self.message_user(request, 'Please select exactly one BOM to duplicate.', level=messages.ERROR)
            return
        
        original = queryset.first()
        new_version = original.version + 1
        
        # Create new BOM
        new_bom = BOM.objects.create(
            product=original.product,
            version=new_version,
            is_active=False,
            effective_from=timezone.now().date(),
            base_quantity=original.base_quantity,
            notes=f"Duplicated from v{original.version}"
        )
        
        # Copy lines
        for line in original.lines.all():
            BOMLine.objects.create(
                bom=new_bom,
                component=line.component,
                quantity_per_kg=line.quantity_per_kg,
                unit=line.unit,
                wastage_percentage=line.wastage_percentage,
                sequence=line.sequence,
                notes=line.notes
            )
        
        self.message_user(
            request, 
            f'BOM v{new_version} created successfully from v{original.version}.',
            level=messages.SUCCESS
        )
    duplicate_bom.short_description = "Duplicate selected BOM (new version)"


class MaterialRequirementInline(admin.TabularInline):
    """Inline to show material requirements for a production run"""
    model = BOMLine
    extra = 0
    fields = (
        'component',
        'quantity_per_kg',
        'required_quantity',
        'unit',
        'available_stock',
        'status',
        'wastage_percentage',
    )
    readonly_fields = ('required_quantity', 'available_stock', 'status')
    can_delete = False
    can_add = False
    max_num = 0
    verbose_name = "Material Requirement"
    verbose_name_plural = "Material Requirements"

    def required_quantity(self, obj):
        """Calculate required quantity based on planned production"""
        if hasattr(self, 'production_run') and self.production_run.planned_quantity:
            qty = obj.quantity_per_kg * self.production_run.planned_quantity
            qty_with_wastage = qty * (1 + obj.wastage_percentage / 100)
            return format_html(
                '<span title="Base: {} | With Wastage: {}">{} {}</span>',
                round(qty, 3),
                round(qty_with_wastage, 3),
                round(qty_with_wastage, 3),
                obj.unit.abbreviation
            )
        return '-'
    required_quantity.short_description = 'Required Qty (with wastage)'

    def available_stock(self, obj):
        """Show available stock for this component"""
        if obj.component:
            stock = obj.component.current_stock
            color = 'green' if stock >= 0 else 'red'
            return format_html(
                '<span style="color: {};">{} {}</span>',
                color,
                stock,
                obj.unit.abbreviation
            )
        return '-'
    available_stock.short_description = 'Available Stock'

    def status(self, obj):
        """Show if stock is sufficient"""
        if hasattr(self, 'production_run') and self.production_run.planned_quantity and obj.component:
            required = obj.quantity_per_kg * self.production_run.planned_quantity
            required_with_wastage = required * (1 + obj.wastage_percentage / 100)
            
            if obj.component.current_stock >= required_with_wastage:
                return format_html('<span style="color: green;">✓ Sufficient</span>')
            else:
                deficit = required_with_wastage - obj.component.current_stock
                return format_html(
                    '<span style="color: red;">✗ Insufficient (deficit: {} {})</span>',
                    round(deficit, 3),
                    obj.unit.abbreviation
                )
        return '-'
    status.short_description = 'Status'


@admin.register(ProductionRun)
class ProductionRunAdmin(admin.ModelAdmin):
    list_display = (
        'run_number',
        'product_link',
        'bom_link',
        'planned_quantity',
        'actual_quantity',
        'status_colored',
        'start_date',
        'end_date',
        'yield_percentage',
        'stock_readiness',
    )
    list_filter = (
        'status',
        'start_date',
        'product__product_type',
        'created_by',
    )
    search_fields = (
        'run_number',
        'product__code',
        'product__name',
        'notes',
        'bom__version',
    )
    date_hierarchy = 'start_date'
    readonly_fields = (
        'run_number',
        'estimated_material_cost',
        'standard_material_cost',
        'actual_material_cost',
        'material_variance',
        'total_variance',
        'created_at',
        'updated_at',
        'created_by',
        'material_requirements_summary',
        'stock_check_result',
    )
    autocomplete_fields = ['bom', 'product']
    list_per_page = 25
    save_on_top = True
    actions = ['start_runs', 'complete_runs', 'cancel_runs', 'transfer_materials']

    fieldsets = (
        ('Run Information', {
            'fields': (
                'run_number',
                'bom',
                'product',
                'status',
                'notes',
            ),
        }),
        ('Quantities', {
            'fields': (
                'planned_quantity',
                'actual_quantity',
                ('start_date', 'end_date'),
            ),
        }),
        ('Material Requirements Check', {
            'fields': (
                'stock_check_result',
                'material_requirements_summary',
            ),
            'classes': ('wide',),
        }),
        ('Cost Summary', {
            'fields': (
                'estimated_material_cost',
                'standard_material_cost',
                'actual_material_cost',
                'material_variance',
                'total_variance',
            ),
            'classes': ('collapse',),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'created_by'),
            'classes': ('collapse',),
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('product', 'bom', 'created_by')

    def get_inlines(self, request, obj):
        """Show material requirements inline when viewing/editing a production run"""
        if obj and obj.pk:  # Only show when editing existing run
            # Set the production_run attribute for the inline
            inline = MaterialRequirementInline
            inline.production_run = obj
            return [MaterialRequirementInline]
        return []

    def run_number(self, obj):
        return f"RUN-{obj.id:05d}"
    run_number.short_description = 'Run #'
    run_number.admin_order_field = 'id'

    def product_link(self, obj):
        url = reverse('admin:core_item_change', args=[obj.product.id])
        return format_html('<a href="{}">{}</a>', url, obj.product.code)
    product_link.short_description = 'Product'
    product_link.admin_order_field = 'product__code'

    def bom_link(self, obj):
        url = reverse('admin:production_bom_change', args=[obj.bom.id])
        return format_html('<a href="{}">v{}</a>', url, obj.bom.version)
    bom_link.short_description = 'BOM'

    def status_colored(self, obj):
        colors = {
            'planned': '#17a2b8',  # blue
            'in_progress': '#ffc107',  # yellow
            'completed': '#28a745',  # green
            'cancelled': '#dc3545',  # red
            'failed': '#6c757d',  # gray
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_colored.short_description = 'Status'
    status_colored.admin_order_field = 'status'

    def yield_percentage(self, obj):
        if obj.planned_quantity and obj.actual_quantity:
            pct = (obj.actual_quantity / obj.planned_quantity) * 100
            color = 'green' if pct >= 95 else 'orange' if pct >= 85 else 'red'
            return format_html(
                '<span style="color: {}; font-weight: bold;">{:.1f}%</span>',
                color,
                pct
            )
        return '-'
    yield_percentage.short_description = 'Yield'

    def stock_readiness(self, obj):
        """Show stock readiness with color coding"""
        if not obj.pk or not obj.bom:
            return '-'
            
        try:
            sufficient = True
            deficits = []
            
            for line in obj.bom.lines.all():
                required = line.quantity_per_kg * obj.planned_quantity
                required_with_wastage = required * (1 + line.wastage_percentage / 100)
                
                if line.component.current_stock < required_with_wastage:
                    sufficient = False
                    deficit = required_with_wastage - line.component.current_stock
                    deficits.append(f"{line.component.code}: {deficit:.2f}")
            
            if sufficient:
                return format_html('<span style="color: green;">✓ Ready</span>')
            else:
                return format_html(
                    '<span style="color: red;" title="{}">✗ Insufficient</span>',
                    ' | '.join(deficits)
                )
        except:
            return '-'
    stock_readiness.short_description = 'Stock Ready'

    def material_requirements_summary(self, obj):
        """Generate a summary table of material requirements"""
        if not obj.pk or not obj.bom or not obj.planned_quantity:
            return "Set planned quantity to see material requirements"
        
        html = ['<table style="width:100%; border-collapse: collapse;">']
        html.append('<tr style="background-color: #f2f2f2;">')
        html.append('<th style="padding: 8px; text-align: left;">Component</th>')
        html.append('<th style="padding: 8px; text-align: right;">Qty/kg</th>')
        html.append('<th style="padding: 8px; text-align: right;">Wastage %</th>')
        html.append('<th style="padding: 8px; text-align: right;">Required (with wastage)</th>')
        html.append('<th style="padding: 8px; text-align: right;">Available</th>')
        html.append('<th style="padding: 8px; text-align: right;">Status</th>')
        html.append('</tr>')
        
        all_sufficient = True
        total_cost = 0
        
        for line in obj.bom.lines.all().select_related('component', 'unit'):
            required = line.quantity_per_kg * obj.planned_quantity
            required_with_wastage = required * (1 + line.wastage_percentage / 100)
            available = line.component.current_stock
            
            if available >= required_with_wastage:
                status = '<span style="color: green;">✓</span>'
                status_color = 'green'
            else:
                all_sufficient = False
                deficit = required_with_wastage - available
                status = f'<span style="color: red;">✗ (deficit: {deficit:.2f})</span>'
                status_color = 'red'
            
            row_color = '#fff' if all_sufficient else '#fff0f0'
            total_cost += required_with_wastage * line.component.unit_cost
            
            html.append(f'<tr style="background-color: {row_color};">')
            html.append(f'<td style="padding: 5px;"><strong>{line.component.code}</strong><br><small>{line.component.name}</small></td>')
            html.append(f'<td style="padding: 5px; text-align: right;">{line.quantity_per_kg}</td>')
            html.append(f'<td style="padding: 5px; text-align: right;">{line.wastage_percentage}%</td>')
            html.append(f'<td style="padding: 5px; text-align: right;"><strong>{required_with_wastage:.2f}</strong> {line.unit.abbreviation}</td>')
            html.append(f'<td style="padding: 5px; text-align: right;">{available:.2f} {line.unit.abbreviation}</td>')
            html.append(f'<td style="padding: 5px; text-align: right;">{status}</td>')
            html.append('</tr>')
        
        # Add totals row
        html.append('<tr style="background-color: #e6e6e6; font-weight: bold;">')
        html.append('<td colspan="3" style="padding: 8px;">Total Material Cost</td>')
        html.append(f'<td style="padding: 8px; text-align: right;" colspan="3">{total_cost:,.2f} ETB</td>')
        html.append('</tr>')
        
        html.append('</table>')
        
        if not all_sufficient:
            html.append('<p style="color: red; margin-top: 10px;">⚠ Some materials have insufficient stock. Please procure before starting production.</p>')
        else:
            html.append('<p style="color: green; margin-top: 10px;">✓ All materials have sufficient stock. Ready to start production.</p>')
        
        return format_html(''.join(html))
    material_requirements_summary.short_description = 'Material Requirements'

    def stock_check_result(self, obj):
        """Quick stock check result"""
        if not obj.pk or not obj.bom or not obj.planned_quantity:
            return "Enter planned quantity to check stock availability"
        
        try:
            sufficient = True
            messages = []
            
            for line in obj.bom.lines.all():
                required = line.quantity_per_kg * obj.planned_quantity
                required_with_wastage = required * (1 + line.wastage_percentage / 100)
                
                if line.component.current_stock < required_with_wastage:
                    sufficient = False
                    messages.append(f"{line.component.code}: need {required_with_wastage:.2f}, have {line.component.current_stock:.2f}")
            
            if sufficient:
                return format_html('<span style="color: green; font-size: 1.1em;">✓ All materials are available in sufficient quantity.</span>')
            else:
                return format_html('<span style="color: red; font-size: 1.1em;">✗ Stock insufficiency detected:<br>{}</span>', '<br>'.join(messages))
        except Exception as e:
            return f"Error checking stock: {e}"
    stock_check_result.short_description = 'Stock Check'

    def save_model(self, request, obj, form, change):
        """Auto-set created_by on creation"""
        if not obj.pk:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    def start_runs(self, request, queryset):
        """Action to start selected production runs and transfer materials"""
        count = 0
        errors = 0
        insufficient_stock = 0
        
        for run in queryset:
            if run.status != 'planned':
                self.message_user(
                    request, 
                    f"Run #{run.id} cannot be started - status is {run.get_status_display()}", 
                    level=messages.WARNING
                )
                errors += 1
                continue
            
            # Check stock sufficiency
            try:
                run.check_component_stock(run.planned_quantity)
            except ValidationError as e:
                self.message_user(
                    request, 
                    f"Run #{run.id} cannot be started: {e}", 
                    level=messages.ERROR
                )
                insufficient_stock += 1
                continue
                
            try:
                with transaction.atomic():
                    # Start the run
                    run.start()
                    
                    # Transfer materials from warehouse to production (optional - can be done via separate action)
                    # This creates a material transfer record but doesn't deduct stock yet
                    # Stock will be deducted when production is completed
                    
                    count += 1
            except ValidationError as e:
                self.message_user(
                    request, 
                    f"Run #{run.id} ({run.product.code}) failed to start: {e}", 
                    level=messages.ERROR
                )
                errors += 1
            except Exception as e:
                self.message_user(
                    request, 
                    f"Unexpected error starting run #{run.id}: {str(e)}", 
                    level=messages.ERROR
                )
                errors += 1
        
        if count > 0:
            self.message_user(
                request, 
                f"Successfully started {count} production run(s). Materials reserved.", 
                level=messages.SUCCESS
            )
        if insufficient_stock > 0:
            self.message_user(
                request, 
                f"{insufficient_stock} run(s) cannot be started due to insufficient stock.", 
                level=messages.WARNING
            )
    
    start_runs.short_description = "Start selected runs (check stock first)"

    def transfer_materials(self, request, queryset):
        """Action to transfer materials from warehouse to production"""
        count = 0
        errors = 0
        
        for run in queryset:
            if run.status != 'in_progress':
                self.message_user(
                    request, 
                    f"Run #{run.id} must be in progress to transfer materials", 
                    level=messages.WARNING
                )
                errors += 1
                continue
                
            try:
                with transaction.atomic():
                    # Create inventory movements for each component
                    for line in run.bom.lines.all():
                        required = line.quantity_per_kg * run.planned_quantity
                        required_with_wastage = required * (1 + line.wastage_percentage / 100)
                        
                        # Create movement record (actual stock deduction will happen on completion)
                        InventoryMovement.objects.create(
                            item=line.component,
                            quantity=-required_with_wastage,  # Negative indicates out
                            movement_type='out_production',
                            reference=f"Production Run #{run.id}",
                            notes=f"Materials transferred for {run.product.name} production",
                            production_run=run,
                            created_by=request.user
                        )
                        
                        # Optionally update current stock (if you want real-time deduction)
                        # line.component.current_stock -= required_with_wastage
                        # line.component.save()
                    
                    count += 1
            except Exception as e:
                self.message_user(
                    request, 
                    f"Error transferring materials for run #{run.id}: {str(e)}", 
                    level=messages.ERROR
                )
                errors += 1
        
        if count > 0:
            self.message_user(
                request, 
                f"Materials transferred for {count} production run(s).", 
                level=messages.SUCCESS
            )
    
    transfer_materials.short_description = "Transfer materials to production"

    def complete_runs(self, request, queryset):
        """Action to complete selected production runs and update stock"""
        count = 0
        errors = 0
        
        for run in queryset:
            if run.status != 'in_progress':
                self.message_user(
                    request, 
                    f"Run #{run.id} cannot be completed - status is {run.get_status_display()}", 
                    level=messages.WARNING
                )
                errors += 1
                continue
                
            try:
                # Get actual quantity from request or use planned
                actual_qty = request.POST.get(f'actual_qty_{run.id}')
                if actual_qty:
                    from decimal import Decimal
                    actual_qty = Decimal(actual_qty)
                else:
                    actual_qty = None
                    
                run.complete(actual_qty)
                count += 1
                self.message_user(
                    request, 
                    f"Run #{run.id} ({run.product.code}) completed successfully. Stock updated.", 
                    level=messages.SUCCESS
                )
            except ValidationError as e:
                self.message_user(
                    request, 
                    f"Run #{run.id} failed to complete: {e}", 
                    level=messages.ERROR
                )
                errors += 1
            except Exception as e:
                self.message_user(
                    request, 
                    f"Unexpected error completing run #{run.id}: {str(e)}", 
                    level=messages.ERROR
                )
                errors += 1
        
        if count > 0:
            self.message_user(
                request, 
                f"Successfully completed {count} production run(s).", 
                level=messages.SUCCESS
            )
    
    complete_runs.short_description = "Complete selected runs (update stock)"

    def cancel_runs(self, request, queryset):
        """Action to cancel selected production runs"""
        count = 0
        errors = 0
        
        for run in queryset:
            if run.status in ['completed', 'cancelled']:
                self.message_user(
                    request, 
                    f"Run #{run.id} cannot be cancelled - already {run.get_status_display()}", 
                    level=messages.WARNING
                )
                errors += 1
                continue
                
            try:
                run.cancel()
                count += 1
            except ValidationError as e:
                self.message_user(
                    request, 
                    f"Run #{run.id} failed to cancel: {e}", 
                    level=messages.ERROR
                )
                errors += 1
            except Exception as e:
                self.message_user(
                    request, 
                    f"Unexpected error cancelling run #{run.id}: {str(e)}", 
                    level=messages.ERROR
                )
                errors += 1
        
        if count > 0:
            self.message_user(
                request, 
                f"Successfully cancelled {count} production run(s).", 
                level=messages.SUCCESS
            )
    
    cancel_runs.short_description = "Cancel selected runs"


@admin.register(InventoryMovement)
class InventoryMovementAdmin(admin.ModelAdmin):
    list_display = (
        'created_at',
        'item_link',
        'movement_type_colored',
        'quantity_colored',
        'reference',
        'production_run_link',
        'created_by',
        'notes_short',
    )
    list_filter = (
        'movement_type',
        'created_at',
        'item__category',
        'created_by',
    )
    search_fields = (
        'item__code',
        'item__name',
        'reference',
        'notes',
        'production_run__id',
    )
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at', 'created_by')
    autocomplete_fields = ['item', 'production_run']
    list_per_page = 25

    fieldsets = (
        ('Movement Information', {
            'fields': (
                'item',
                'movement_type',
                'quantity',
                'reference',
            ),
        }),
        ('Production Link', {
            'fields': ('production_run',),
        }),
        ('Additional Info', {
            'fields': ('notes', 'created_by'),
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',),
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'item', 'production_run', 'created_by'
        )

    def item_link(self, obj):
        url = reverse('admin:core_item_change', args=[obj.item.id])
        return format_html('<a href="{}">{}</a>', url, obj.item.code)
    item_link.short_description = 'Item'
    item_link.admin_order_field = 'item__code'

    def movement_type_colored(self, obj):
        colors = {
            'in_purchase': 'green',
            'in_production': 'teal',
            'out_production': 'orange',
            'adjustment_add': 'blue',
            'adjustment_remove': 'red',
        }
        color = colors.get(obj.movement_type, 'gray')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_movement_type_display()
        )
    movement_type_colored.short_description = 'Type'

    def quantity_colored(self, obj):
        color = 'green' if obj.quantity > 0 else 'red'
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.quantity
        )
    quantity_colored.short_description = 'Quantity'
    quantity_colored.admin_order_field = 'quantity'

    def production_run_link(self, obj):
        if obj.production_run:
            url = reverse('admin:production_productionrun_change', args=[obj.production_run.id])
            return format_html('<a href="{}">Run #{}</a>', url, obj.production_run.id)
        return "—"
    production_run_link.short_description = 'Production Run'

    def notes_short(self, obj):
        if obj.notes:
            return obj.notes[:50] + '...' if len(obj.notes) > 50 else obj.notes
        return '-'
    notes_short.short_description = 'Notes'

    def save_model(self, request, obj, form, change):
        """Auto-set created_by on creation"""
        if not obj.pk:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)