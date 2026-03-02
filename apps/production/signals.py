from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from django.db import transaction
from django.core.exceptions import ValidationError
from decimal import Decimal

from .models import ProductionRun, ProductionCostVariance, BOMLine
from apps.inventory.models import StockTransaction, CurrentStock, Lot, Warehouse


@receiver(pre_save, sender=ProductionRun)
def validate_production_run(sender, instance, **kwargs):
    """Validate production run before saving"""
    if instance.pk:  # Only for existing runs
        old_instance = ProductionRun.objects.get(pk=instance.pk)
        
        # Prevent changing product or BOM after start
        if old_instance.status != 'planned' and instance.status != 'planned':
            if old_instance.bom_id != instance.bom_id:
                raise ValidationError("Cannot change BOM after production has started")
            if old_instance.product_id != instance.product_id:
                raise ValidationError("Cannot change product after production has started")


@receiver(post_save, sender=ProductionRun)
def handle_production_run_status_change(sender, instance, created, **kwargs):
    """Handle various status changes for production runs"""
    
    if created:
        # New production run created
        # Could send notification or create initial records
        pass
    else:
        # Existing run updated
        try:
            old_instance = ProductionRun.objects.get(pk=instance.pk)
            
            # Check if status changed
            if old_instance.status != instance.status:
                
                # Status changed to 'in_progress' - run started
                if instance.status == 'in_progress' and old_instance.status == 'planned':
                    handle_run_started(instance)
                
                # Status changed to 'completed' - run completed
                elif instance.status == 'completed' and old_instance.status == 'in_progress':
                    handle_run_completed(instance)
                
                # Status changed to 'cancelled' - run cancelled
                elif instance.status == 'cancelled' and old_instance.status not in ['completed', 'cancelled']:
                    handle_run_cancelled(instance)
                    
        except ProductionRun.DoesNotExist:
            # This shouldn't happen, but just in case
            pass


def handle_run_started(production_run):
    """Handle when a production run is started"""
    # Check stock availability
    try:
        production_run.check_component_stock(production_run.planned_quantity)
        
        # Optional: Reserve stock (could create a reservation system)
        # For now, just log that run has started
        print(f"Production Run #{production_run.id} started successfully")
        
    except ValidationError as e:
        # If stock check fails, revert status? This would require more complex logic
        # For now, just raise the error
        raise ValidationError(f"Cannot start run due to stock issues: {e}")


def handle_run_completed(production_run):
    """Handle when a production run is completed - deduct materials and add finished goods"""
    try:
        with transaction.atomic():
            # Get or create production warehouse
            production_warehouse, _ = Warehouse.objects.get_or_create(
                code='PROD-FLOOR',
                defaults={
                    'name': 'Production Floor',
                    'warehouse_type': 'wip',
                    'is_active': True
                }
            )
            
            # Get finished goods warehouse
            fg_warehouse, _ = Warehouse.objects.get_or_create(
                code='FG-WH',
                defaults={
                    'name': 'Finished Goods Warehouse',
                    'warehouse_type': 'finished',
                    'is_active': True
                }
            )
            
            # Deduct raw materials
            deduct_materials_from_bom(production_run, production_warehouse)
            
            # Add finished goods
            add_finished_goods(production_run, fg_warehouse)
            
            # Calculate cost variance
            calculate_cost_variance(production_run)
            
            print(f"Production Run #{production_run.id} completed successfully")
            
    except Exception as e:
        raise ValidationError(f"Failed to complete production run: {str(e)}")


def deduct_materials_from_bom(production_run, from_warehouse):
    """
    Deduct raw and packing materials based on actual produced quantity
    Uses FIFO method (oldest lots first)
    """
    bom = production_run.bom
    produced_kg = production_run.actual_quantity or production_run.planned_quantity
    
    if produced_kg <= 0:
        raise ValidationError("Produced quantity must be positive")

    for line in bom.lines.all().select_related('component', 'unit'):
        component = line.component
        qty_per_kg = line.quantity_per_kg
        wastage_factor = 1 + (line.wastage_percentage / 100)
        
        required_qty = produced_kg * qty_per_kg * wastage_factor

        if required_qty <= 0:
            continue

        # Find available lots (non-expired, with stock)
        available_lots = Lot.objects.filter(
            item=component,
            expiry_date__gte=timezone.now().date(),
            is_active=True,
            current_quantity__gt=0
        ).order_by('expiry_date', 'received_date')  # FIFO by expiry date

        if not available_lots.exists():
            raise ValidationError(
                f"No available lots found for {component.code}"
            )

        remaining_to_deduct = required_qty
        total_deducted = Decimal('0')

        for lot in available_lots:
            if remaining_to_deduct <= 0:
                break

            # Get current lot quantity
            lot_qty = lot.current_quantity
            if lot_qty <= 0:
                continue

            deduct_from_this_lot = min(remaining_to_deduct, lot_qty)
            
            if deduct_from_this_lot <= 0:
                continue

            # Create stock transaction
            transaction = StockTransaction.objects.create(
                transaction_type='issue',
                item=component,
                lot=lot,
                warehouse_from=from_warehouse,
                quantity=deduct_from_this_lot,
                unit_cost=component.unit_cost,  # Store cost at time of transaction
                transaction_date=timezone.now(),
                reference=f"PR-{production_run.id:05d}",
                production_run=production_run,
                notes=f"Consumed for {produced_kg}kg of {production_run.product.name}"
            )

            # Update lot quantity (through model's save method)
            lot.current_quantity -= deduct_from_this_lot
            lot.save(update_fields=['current_quantity'])

            # Update or create CurrentStock record
            current_stock, _ = CurrentStock.objects.get_or_create(
                item=component,
                warehouse=from_warehouse,
                lot=lot,
                defaults={'quantity': 0}
            )
            current_stock.quantity -= deduct_from_this_lot
            current_stock.last_transaction = transaction
            current_stock.save()

            remaining_to_deduct -= deduct_from_this_lot
            total_deducted += deduct_from_this_lot

        if remaining_to_deduct > 0:
            raise ValidationError(
                f"Insufficient stock for {component.code}. "
                f"Needed {required_qty:.2f} {component.unit.abbreviation}, "
                f"only {total_deducted:.2f} available."
            )


def add_finished_goods(production_run, to_warehouse):
    """
    Add finished goods to inventory after production completion
    """
    product = production_run.product
    produced_qty = production_run.actual_quantity or production_run.planned_quantity
    
    # Create new lot for finished goods
    lot = Lot.objects.create(
        item=product,
        batch_number=f"PROD-{production_run.id:05d}-{timezone.now().strftime('%Y%m%d')}",
        manufacturing_date=production_run.end_date or timezone.now().date(),
        expiry_date=(production_run.end_date or timezone.now().date()) + 
                    timezone.timedelta(days=product.shelf_life_days or 730),
        received_date=timezone.now().date(),
        initial_quantity=produced_qty,
        current_quantity=produced_qty,
        is_active=True,
        notes=f"Produced from run #{production_run.id}"
    )

    # Create stock transaction
    transaction = StockTransaction.objects.create(
        transaction_type='receipt',
        item=product,
        lot=lot,
        warehouse_to=to_warehouse,
        quantity=produced_qty,
        unit_cost=production_run.actual_material_cost / produced_qty if production_run.actual_material_cost else product.unit_cost,
        transaction_date=timezone.now(),
        reference=f"PR-{production_run.id:05d}",
        production_run=production_run,
        notes=f"Finished goods from production run #{production_run.id}"
    )

    # Update or create CurrentStock record
    current_stock, _ = CurrentStock.objects.get_or_create(
        item=product,
        warehouse=to_warehouse,
        lot=lot,
        defaults={'quantity': 0}
    )
    current_stock.quantity += produced_qty
    current_stock.last_transaction = transaction
    current_stock.save()

    # Update product's current stock
    product.current_stock += produced_qty
    product.save(update_fields=['current_stock'])


def calculate_cost_variance(production_run):
    """
    Calculate and create cost variance record for completed production run
    """
    if production_run.status == 'completed' and not hasattr(production_run, 'cost_variance'):
        try:
            variance = ProductionCostVariance.create_from_run(production_run)
            
            # Optional: Send notification if variance exceeds threshold
            if variance and abs(variance.variance_percentage) > 10:  # 10% threshold
                # Could send email or create alert here
                print(f"High variance detected for Run #{production_run.id}: {variance.variance_percentage:+.1f}%")
            
            return variance
        except Exception as e:
            # Log error but don't fail the completion
            print(f"Error calculating cost variance for Run #{production_run.id}: {e}")
            return None


def handle_run_cancelled(production_run):
    """Handle when a production run is cancelled"""
    # Optional: Release any reserved stock
    # For now, just log the cancellation
    print(f"Production Run #{production_run.id} cancelled")


@receiver(post_save, sender=ProductionRun)
def update_inventory_on_completion(sender, instance, **kwargs):
    """
    Legacy signal handler - kept for backward compatibility
    """
    if instance.status == 'completed' and instance.actual_quantity:
        # This is now handled by handle_run_completed
        pass


@receiver(post_save, sender=ProductionRun)
def auto_create_cost_variance(sender, instance, **kwargs):
    """
    Automatically create cost variance when run is completed
    """
    if instance.status == 'completed' and not hasattr(instance, 'cost_variance'):
        calculate_cost_variance(instance)