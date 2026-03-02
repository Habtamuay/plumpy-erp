from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.core.validators import MinValueValidator
from django.utils.html import format_html
from decimal import Decimal
from apps.core.models import Item


class BOM(models.Model):
    """Bill of Materials - defined per 1 kg of finished product"""
    product = models.ForeignKey(
        Item,
        on_delete=models.PROTECT,
        limit_choices_to={'category': 'finished'},
        related_name='boms'
    )
    version = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    effective_from = models.DateField(default=timezone.now)
    notes = models.TextField(blank=True, help_text="e.g. WHO compliant recipe v2.3 - March 2026")

    base_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        default=1.0000,
        help_text="BOM is defined per this many kg of product (usually 1)"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [['product', 'version']]
        ordering = ['-version']
        verbose_name = "Bill of Materials"
        verbose_name_plural = "Bills of Materials"
        indexes = [
            models.Index(fields=['product', 'is_active']),
            models.Index(fields=['effective_from']),
        ]

    def __str__(self):
        return f"{self.product.code} v{self.version} (per {self.base_quantity} kg)"

    @property
    def is_current(self):
        """Check if BOM is current (active and effective from <= today)"""
        return self.is_active and self.effective_from <= timezone.now().date()

    @property
    def total_material_cost_per_base(self):
        """Calculate total material cost per base quantity (usually 1 kg)"""
        total = Decimal('0.00')
        for line in self.lines.all():
            cost = line.quantity_per_kg * (line.component.unit_cost or Decimal('0.00'))
            total += cost
        return total

    @property
    def components_count(self):
        """Get number of components in this BOM"""
        return self.lines.count()


class BOMLine(models.Model):
    """One component (ingredient or packing) per BOM"""
    bom = models.ForeignKey(BOM, on_delete=models.CASCADE, related_name='lines')

    component = models.ForeignKey(
        Item,
        on_delete=models.PROTECT,
        limit_choices_to={'category__in': ['raw', 'packing']}
    )

    quantity_per_kg = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        validators=[MinValueValidator(0.000001)],
        help_text="Kg / Meters / Pcs per 1 kg of finished product"
    )

    unit = models.ForeignKey('core.Unit', on_delete=models.PROTECT)

    wastage_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.00,
        help_text="Standard wastage % from your BOM table"
    )

    sequence = models.PositiveSmallIntegerField(default=10)
    notes = models.CharField(max_length=250, blank=True)

    class Meta:
        ordering = ['sequence', 'id']
        unique_together = [['bom', 'component']]
        verbose_name = "BOM Line"
        verbose_name_plural = "BOM Lines"

    def __str__(self):
        return f"{self.component.code} → {self.quantity_per_kg} {self.unit} (w{self.wastage_percentage}%)"

    @property
    def quantity_with_wastage(self):
        """Calculate quantity including wastage percentage"""
        return self.quantity_per_kg * (1 + self.wastage_percentage / 100)

    @property
    def cost_per_kg(self):
        """Calculate cost contribution per kg of finished product"""
        return self.quantity_per_kg * (self.component.unit_cost or Decimal('0.00'))


class InventoryMovement(models.Model):
    """Stock Movement Log - tracks all inventory movements"""
    MOVEMENT_TYPES = [
        ('in_purchase', 'Received from Purchase'),
        ('in_production', 'Produced (Finished Goods)'),
        ('out_production', 'Consumed in Production'),
        ('transfer_in', 'Transfer In'),
        ('transfer_out', 'Transfer Out'),
        ('adjustment_add', 'Manual Add – Adjustment'),
        ('adjustment_remove', 'Manual Remove – Adjustment'),
        ('return', 'Return from Customer'),
        ('return_supplier', 'Return to Supplier'),
        ('scrap', 'Scrap / Waste'),
        ('sample', 'Quality Sample'),
    ]

    item = models.ForeignKey(
        'core.Item',
        on_delete=models.PROTECT,
        related_name='movements',
        verbose_name="Item"
    )
    quantity = models.DecimalField(
        max_digits=15,
        decimal_places=4,
        help_text="Positive = added to stock, Negative = removed from stock"
    )
    movement_type = models.CharField(
        max_length=30,
        choices=MOVEMENT_TYPES,
        verbose_name="Movement Type",
        db_index=True
    )
    reference = models.CharField(
        max_length=100, 
        blank=True, 
        verbose_name="Reference",
        db_index=True
    )
    notes = models.TextField(blank=True)
    
    # Warehouse tracking
    from_warehouse = models.ForeignKey(
        'inventory.Warehouse',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='outgoing_movements',
        verbose_name="From Warehouse"
    )
    to_warehouse = models.ForeignKey(
        'inventory.Warehouse',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='incoming_movements',
        verbose_name="To Warehouse"
    )
    
    # Balance tracking
    balance_before = models.DecimalField(
        max_digits=15,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Stock balance before this movement"
    )
    balance_after = models.DecimalField(
        max_digits=15,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Stock balance after this movement"
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    created_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_movements',
        verbose_name="Created By"
    )
    
    # Link back to the production run that caused this movement
    production_run = models.ForeignKey(
        'ProductionRun',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='movements',
        verbose_name="Production Run"
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Stock Movement"
        verbose_name_plural = "Stock Movements"
        indexes = [
            models.Index(fields=['movement_type', 'created_at']),
            models.Index(fields=['item', 'created_at']),
        ]

    def __str__(self):
        sign = '+' if self.quantity > 0 else '-'
        direction = ""
        if self.from_warehouse and self.to_warehouse:
            direction = f" {self.from_warehouse.code} → {self.to_warehouse.code}"
        elif self.from_warehouse:
            direction = f" from {self.from_warehouse.code}"
        elif self.to_warehouse:
            direction = f" to {self.to_warehouse.code}"
            
        return f"{sign}{abs(self.quantity)} {self.item.code}{direction} – {self.get_movement_type_display()}"


class ProductionRun(models.Model):
    """Production Run - tracks a batch of production"""
    
    STATUS_CHOICES = [
        ('planned', 'Planned'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('failed', 'Failed'),
    ]

    # Core fields
    bom = models.ForeignKey(
        BOM,
        on_delete=models.PROTECT,
        related_name='production_runs',
        verbose_name="Bill of Materials"
    )
    product = models.ForeignKey(
        Item,
        on_delete=models.PROTECT,
        related_name='produced_runs',
        limit_choices_to={'category': 'finished'},
        verbose_name="Finished Product"
    )
    
    # Quantities
    planned_quantity = models.DecimalField(
        max_digits=15,
        decimal_places=4,
        help_text="Planned production quantity (in product's unit, usually kg)",
        verbose_name="Planned Qty",
        validators=[MinValueValidator(0.0001)]
    )
    actual_quantity = models.DecimalField(
        max_digits=15,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Actual produced quantity (filled on completion)",
        verbose_name="Actual Qty"
    )
    waste_quantity = models.DecimalField(
        max_digits=15,
        decimal_places=4,
        null=True,
        blank=True,
        default=0,
        help_text="Quantity of waste/scrap generated",
        verbose_name="Waste Qty"
    )
    
    # Status and dates
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='planned',
        db_index=True
    )
    start_date = models.DateTimeField(
        default=timezone.now,
        help_text="When production was started / planned",
        db_index=True
    )
    end_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When production was completed or cancelled"
    )
    
    # Notes
    notes = models.TextField(blank=True)
    
    # Cost tracking (snapshots)
    estimated_material_cost = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Estimated material cost at planning time"
    )
    standard_material_cost = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Standard material cost from BOM"
    )
    actual_material_cost = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Actual material cost from consumption"
    )
    labor_cost = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        default=0,
        help_text="Labor cost for this run"
    )
    overhead_cost = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        default=0,
        help_text="Overhead cost for this run"
    )
    
    # Variances
    material_variance = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Material cost variance (actual - standard)"
    )
    total_variance = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Total cost variance"
    )
    
    # Yield
    yield_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Production yield percentage"
    )
    
    # Metadata
    created_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_runs'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_date']
        verbose_name = "Production Run"
        verbose_name_plural = "Production Runs"
        indexes = [
            models.Index(fields=['status', 'start_date']),
            models.Index(fields=['product', 'status']),
        ]

    def __str__(self):
        return f"Run #{self.id} — {self.product.code} × {self.planned_quantity}kg ({self.get_status_display()})"

    def clean(self):
        """Validate the production run"""
        if self.product != self.bom.product:
            raise ValidationError({
                'product': "Product must match the BOM's finished product"
            })

        if self.actual_quantity is not None and self.actual_quantity < 0:
            raise ValidationError({
                'actual_quantity': "Actual quantity cannot be negative"
            })

        if self.planned_quantity <= 0:
            raise ValidationError({
                'planned_quantity': "Planned quantity must be greater than zero"
            })

    def save(self, *args, **kwargs):
        """Auto-set fields on save"""
        if self.pk is None:
            # New run: auto-set product from BOM
            self.product = self.bom.product

            # Snapshot estimated cost
            if hasattr(self.bom, 'total_material_cost_per_base'):
                self.estimated_material_cost = self.bom.total_material_cost_per_base * self.planned_quantity

        # Calculate yield if both quantities are present
        if self.actual_quantity and self.planned_quantity:
            self.yield_percentage = (self.actual_quantity / self.planned_quantity) * 100

        super().save(*args, **kwargs)

    # ────────────────────────────────────────────────
    # Business methods
    # ────────────────────────────────────────────────

    def can_start(self):
        """Check if run can be started"""
        return self.status == 'planned'

    def start(self):
        """Start the production run"""
        if not self.can_start():
            raise ValidationError("Run cannot be started from current status")
        
        # Check stock availability
        self.check_component_stock(self.planned_quantity)
        
        self.status = 'in_progress'
        self.start_date = timezone.now()
        self.save()
        
        # Create movement records for reservation (optional)
        # This can be used to reserve stock without deducting yet
        return True

    def can_complete(self):
        """Check if run can be completed"""
        return self.status == 'in_progress'

    def check_component_stock(self, qty):
        """Raise ValidationError if any component has insufficient stock"""
        insufficient = []
        for line in self.bom.lines.all().select_related('component'):
            required = line.quantity_per_kg * qty
            required_with_wastage = required * (1 + line.wastage_percentage / 100)

            if line.component.current_stock < required_with_wastage:
                insufficient.append({
                    'code': line.component.code,
                    'name': line.component.name,
                    'required': required_with_wastage,
                    'available': line.component.current_stock,
                    'unit': line.unit.abbreviation
                })

        if insufficient:
            error_msg = "Insufficient stock for the following components:\n"
            for item in insufficient:
                error_msg += f"  • {item['code']}: need {item['required']:.2f} {item['unit']}, "
                error_msg += f"have {item['available']:.2f} {item['unit']}\n"
            raise ValidationError(error_msg)

    def complete(self, actual_qty=None, waste_qty=0):
        """
        Complete the run: deduct components, add finished goods, log movements
        """
        if not self.can_complete():
            raise ValidationError("Only 'in progress' runs can be completed")

        actual_qty = actual_qty or self.planned_quantity

        if actual_qty <= 0:
            raise ValidationError("Actual quantity must be positive")

        # Check stock availability first
        self.check_component_stock(actual_qty)

        # Calculate standard costs
        self.standard_material_cost = self.bom.total_material_cost_per_base * actual_qty
        self.standard_total_cost = self.standard_material_cost + (self.labor_cost or 0) + (self.overhead_cost or 0)

        # Calculate actual material cost from real consumption
        actual_material = Decimal('0.00')

        # ── Deduct components & log movements ──
        for line in self.bom.lines.all().select_related('component', 'unit'):
            required = line.quantity_per_kg * actual_qty
            required_with_wastage = required * (1 + line.wastage_percentage / 100)

            # Calculate cost
            line_cost = required_with_wastage * (line.component.unit_cost or Decimal('0.00'))
            actual_material += line_cost

            # Update stock
            line.component.current_stock -= required_with_wastage
            line.component.save(update_fields=['current_stock'])

            # Log consumption
            InventoryMovement.objects.create(
                item=line.component,
                quantity=-required_with_wastage,
                movement_type='out_production',
                reference=f"Run #{self.id}",
                notes=f"Consumed for {actual_qty} kg of {self.product.name}",
                production_run=self,
                created_by=self.created_by
            )

        # ── Add finished product & log movement ──
        produced = actual_qty * self.bom.base_quantity
        self.product.current_stock += produced
        self.product.save(update_fields=['current_stock'])

        InventoryMovement.objects.create(
            item=self.product,
            quantity=produced,
            movement_type='in_production',
            reference=f"Run #{self.id}",
            notes=f"Produced {produced} {self.product.unit} from run",
            production_run=self,
            created_by=self.created_by
        )

        # Update costs
        self.actual_material_cost = actual_material
        self.actual_total_cost = actual_material + (self.labor_cost or 0) + (self.overhead_cost or 0)

        # Calculate variances
        self.material_variance = self.actual_material_cost - self.standard_material_cost
        self.total_variance = self.actual_total_cost - self.standard_total_cost

        # Record waste if any
        if waste_qty > 0:
            self.waste_quantity = waste_qty
            InventoryMovement.objects.create(
                item=self.product,
                quantity=-waste_qty,
                movement_type='scrap',
                reference=f"Run #{self.id}",
                notes=f"Waste/Scrap from production run",
                production_run=self,
                created_by=self.created_by
            )

        # Finalize run
        self.actual_quantity = actual_qty
        self.status = 'completed'
        self.end_date = timezone.now()
        self.save()

        # Create cost variance record
        ProductionCostVariance.objects.create_from_run(self)

        return True

    def cancel(self):
        """Cancel the production run"""
        if self.status in ['completed', 'cancelled']:
            raise ValidationError("Cannot cancel completed or already cancelled runs")
        self.status = 'cancelled'
        self.end_date = timezone.now()
        self.save()

    # ────────────────────────────────────────────────
    # Calculated properties
    # ────────────────────────────────────────────────

    @property
    def required_components(self):
        """List of components with required qty for planned quantity"""
        return [
            {
                'component': line.component,
                'required_qty': line.quantity_per_kg * self.planned_quantity,
                'required_with_wastage': line.quantity_with_wastage * self.planned_quantity,
                'unit': line.unit,
                'available': line.component.current_stock,
                'cost': line.cost_per_kg * self.planned_quantity,
            }
            for line in self.bom.lines.all().select_related('component', 'unit')
        ]

    @property
    def is_stock_ready(self):
        """Check if all components have sufficient stock"""
        try:
            self.check_component_stock(self.planned_quantity)
            return True
        except ValidationError:
            return False

    @property
    def display_status(self):
        """Color-coded status for display"""
        colors = {
            'planned': '#17a2b8',    # blue
            'in_progress': '#ffc107',  # yellow
            'completed': '#28a745',    # green
            'cancelled': '#dc3545',    # red
            'failed': '#6c757d',       # gray
        }
        color = colors.get(self.status, '#6c757d')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            self.get_status_display()
        )

    @property
    def yield_value(self):
        """Calculate yield percentage"""
        if self.actual_quantity and self.planned_quantity:
            return (self.actual_quantity / self.planned_quantity) * 100
        return None


class ProductionCostVariance(models.Model):
    """Tracks cost variances for production runs"""
    
    production_run = models.OneToOneField(
        ProductionRun,
        on_delete=models.CASCADE,
        related_name='cost_variance',
        verbose_name="Production Run"
    )
    calculated_at = models.DateTimeField(auto_now_add=True)
    
    # Summary
    standard_material_cost = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=0,
        verbose_name="Standard Material Cost"
    )
    actual_material_cost = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=0,
        verbose_name="Actual Material Cost"
    )
    material_variance = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=0,
        verbose_name="Material Variance"
    )
    
    standard_labor_cost = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=0,
        verbose_name="Standard Labor Cost"
    )
    actual_labor_cost = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=0,
        verbose_name="Actual Labor Cost"
    )
    labor_variance = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=0,
        verbose_name="Labor Variance"
    )
    
    standard_overhead_cost = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=0,
        verbose_name="Standard Overhead Cost"
    )
    actual_overhead_cost = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=0,
        verbose_name="Actual Overhead Cost"
    )
    overhead_variance = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=0,
        verbose_name="Overhead Variance"
    )
    
    # Totals
    standard_total_cost = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=0,
        verbose_name="Standard Total Cost"
    )
    actual_total_cost = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=0,
        verbose_name="Actual Total Cost"
    )
    total_variance = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=0,
        verbose_name="Total Variance"
    )
    variance_percentage = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name="Variance %"
    )

    # Detailed breakdown as JSON
    item_breakdown = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Item Breakdown",
        help_text="Detailed variance per component"
    )

    notes = models.TextField(blank=True, verbose_name="Notes")

    class Meta:
        verbose_name = "Production Cost Variance"
        verbose_name_plural = "Production Cost Variances"
        ordering = ['-calculated_at']
        indexes = [
            models.Index(fields=['production_run']),
            models.Index(fields=['calculated_at']),
        ]

    def __str__(self):
        return f"Cost Variance - Run #{self.production_run.id} ({self.variance_percentage:+.1f}%)"

    @classmethod
    def create_from_run(cls, production_run):
        """Create a cost variance record from a completed production run"""
        from django.db.models import Sum
        
        run = production_run
        bom = run.bom
        
        std_total = Decimal('0')
        act_total = Decimal('0')
        breakdown = {}

        for bom_line in bom.lines.all().select_related('component'):
            item = bom_line.component

            # Standard cost
            std_qty_per_kg = bom_line.quantity_per_kg * (1 + bom_line.wastage_percentage / 100)
            std_cost = std_qty_per_kg * run.actual_quantity * (item.std_unit_price or item.unit_cost or 0)
            std_total += std_cost

            # Actual cost (from stock transactions)
            actual_usage = run.movements.filter(
                item=item,
                movement_type='out_production'
            ).aggregate(total=Sum('quantity'))['total'] or 0
            
            act_cost = abs(actual_usage) * (item.current_avg_cost or item.unit_cost or 0)
            act_total += act_cost

            variance = act_cost - std_cost
            variance_pct = (variance / std_cost * 100) if std_cost else 0

            breakdown[item.code] = {
                'name': item.name,
                'std_qty': float(std_qty_per_kg * run.actual_quantity),
                'std_price': float(item.std_unit_price or item.unit_cost or 0),
                'std_cost': float(std_cost),
                'act_qty': float(abs(actual_usage)),
                'act_price': float(item.current_avg_cost or item.unit_cost or 0),
                'act_cost': float(act_cost),
                'variance': float(variance),
                'variance_pct': float(variance_pct),
            }

        # Create or update variance record
        variance, created = cls.objects.update_or_create(
            production_run=run,
            defaults={
                'standard_material_cost': std_total,
                'actual_material_cost': act_total,
                'material_variance': act_total - std_total,
                'standard_total_cost': std_total + (run.labor_cost or 0) + (run.overhead_cost or 0),
                'actual_total_cost': act_total + (run.labor_cost or 0) + (run.overhead_cost or 0),
                'total_variance': (act_total - std_total),
                'variance_percentage': ((act_total - std_total) / std_total * 100) if std_total else 0,
                'item_breakdown': breakdown,
            }
        )
        
        return variance