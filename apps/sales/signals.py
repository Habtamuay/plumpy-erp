from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from django.db import transaction
from django.core.exceptions import ValidationError
from decimal import Decimal
import logging

from apps.sales.models import SalesOrder, SalesInvoice, SalesInvoiceLine, SalesShipment, SalesPayment
from apps.production.models import ProductionRun
from apps.core.models import Item
from apps.accounting.models import JournalEntry, JournalLine, Account
from apps.company.models import Customer
from apps.inventory.models import StockTransaction, Lot, Warehouse

logger = logging.getLogger(__name__)


# ============================
# Sales Order Signals
# ============================

@receiver(pre_save, sender=SalesOrder)
def validate_sales_order(sender, instance, **kwargs):
    """Validate sales order before saving"""
    if instance.pk:  # Existing order
        old_instance = SalesOrder.objects.get(pk=instance.pk)
        
        # Prevent changing customer after order is confirmed
        if old_instance.status != 'draft' and old_instance.customer_id != instance.customer_id:
            raise ValidationError("Cannot change customer after order is confirmed")
        
        # Prevent reducing total after order is confirmed
        if old_instance.status != 'draft' and instance.total_amount < old_instance.total_amount:
            raise ValidationError("Cannot reduce order total after confirmation")


@receiver(post_save, sender=SalesOrder)
def handle_sales_order_status_change(sender, instance, created, **kwargs):
    """Handle sales order status changes"""
    if created:
        logger.info(f"Sales Order {instance.order_number} created")
        return
    
    try:
        old_instance = SalesOrder.objects.get(pk=instance.pk)
        
        # Status changed to confirmed
        if old_instance.status != 'confirmed' and instance.status == 'confirmed':
            handle_order_confirmed(instance)
        
        # Status changed to shipped
        elif old_instance.status != 'shipped' and instance.status == 'shipped':
            handle_order_shipped(instance)
        
        # Status changed to delivered
        elif old_instance.status != 'delivered' and instance.status == 'delivered':
            handle_order_delivered(instance)
        
        # Status changed to cancelled
        elif old_instance.status != 'cancelled' and instance.status == 'cancelled':
            handle_order_cancelled(instance)
            
    except SalesOrder.DoesNotExist:
        pass


def handle_order_confirmed(order):
    """Handle order confirmation"""
    # Check stock availability
    insufficient_items = []
    for line in order.lines.all():
        if line.item.current_stock < line.quantity:
            insufficient_items.append(f"{line.item.code}: need {line.quantity}, have {line.item.current_stock}")
    
    if insufficient_items:
        # Log warning but don't prevent confirmation
        logger.warning(f"Order {order.order_number} confirmed with insufficient stock: {', '.join(insufficient_items)}")
    
    # Could send notification to warehouse
    # send_picking_list_to_warehouse(order)
    
    logger.info(f"Order {order.order_number} confirmed")


def handle_order_shipped(order):
    """Handle order shipment"""
    # Update actual ship date
    order.actual_ship_date = timezone.now().date()
    order.save(update_fields=['actual_ship_date'])
    
    # Create stock transactions for shipped items
    with transaction.atomic():
        for line in order.lines.all():
            if line.quantity_shipped > 0:
                # Find warehouse (default to first available)
                warehouse = line.warehouse or Warehouse.objects.filter(is_active=True).first()
                
                if warehouse:
                    # Create stock transaction
                    StockTransaction.objects.create(
                        transaction_type='issue',
                        item=line.item,
                        quantity=-line.quantity_shipped,
                        warehouse_from=warehouse,
                        reference=f"SO-{order.order_number}",
                        notes=f"Shipped for order {order.order_number}"
                    )
                    
                    # Update item stock
                    line.item.current_stock -= line.quantity_shipped
                    line.item.save(update_fields=['current_stock'])
    
    logger.info(f"Order {order.order_number} shipped")


def handle_order_delivered(order):
    """Handle order delivery"""
    order.delivery_date = timezone.now().date()
    order.save(update_fields=['delivery_date'])
    logger.info(f"Order {order.order_number} delivered")


def handle_order_cancelled(order):
    """Handle order cancellation"""
    # Release any reserved stock
    logger.info(f"Order {order.order_number} cancelled")


@receiver(post_save, sender=SalesOrder)
def auto_create_invoice_from_sales_order(sender, instance, created, **kwargs):
    """
    Automatically create invoice when sales order is confirmed
    """
    if created:
        return

    if instance.status == 'confirmed' and not instance.invoice_generated:
        with transaction.atomic():
            try:
                # Create invoice
                invoice = SalesInvoice.objects.create(
                    sales_order=instance,
                    customer=instance.customer,
                    invoice_date=timezone.now().date(),
                    due_date=timezone.now().date() + timezone.timedelta(days=30),
                    status='draft',
                    tax_rate=instance.tax_rate,
                    shipping_amount=instance.shipping_amount,
                    discount_amount=instance.discount_amount,
                    created_by=instance.created_by
                )

                # Copy lines from Sales Order
                for line in instance.lines.all():
                    SalesInvoiceLine.objects.create(
                        invoice=invoice,
                        sales_order_line=line,
                        item=line.item,
                        description=line.item.name,
                        quantity=line.quantity,
                        unit=line.unit,
                        unit_price=line.unit_price,
                        discount_percent=line.discount_percent,
                        std_composition_pct=getattr(line.item, 'std_composition_pct', None),
                        std_consumption_per_mt=getattr(line.item, 'std_consumption_per_mt', None),
                        std_wastage_pct=getattr(line.item, 'std_wastage_pct', None),
                    )

                # Calculate invoice totals
                invoice.calculate_totals()
                
                # Mark order as invoiced
                instance.invoice_generated = True
                instance.invoice = invoice
                instance.status = 'invoiced'
                instance.save(update_fields=['invoice_generated', 'invoice', 'status'])

                # Auto-post journal entry
                create_invoice_journal_entry(invoice)

                logger.info(f"Auto-created invoice {invoice.invoice_number} from SO {instance.order_number}")
                
            except Exception as e:
                logger.error(f"Failed to auto-create invoice for SO {instance.order_number}: {e}")
                raise


def create_invoice_journal_entry(invoice):
    """Create journal entry for invoice"""
    try:
        # Get accounts (with fallback creation if not exists)
        ar_account = Account.objects.filter(code='1100').first()
        sales_account = Account.objects.filter(code='4100').first()
        
        if not ar_account:
            ar_account = Account.objects.create(
                code='1100',
                name='Accounts Receivable',
                account_type='asset'
            )
        
        if not sales_account:
            sales_account = Account.objects.create(
                code='4100',
                name='Sales Revenue',
                account_type='revenue'
            )
        
        # Create journal entry
        je = JournalEntry.objects.create(
            company=invoice.customer.company,
            entry_date=invoice.invoice_date,
            reference=invoice.invoice_number,
            narration=f"Invoice {invoice.invoice_number} for {invoice.customer.name}",
            is_posted=True,
            posted_at=timezone.now()
        )
        
        # Dr Accounts Receivable
        JournalLine.objects.create(
            journal=je,
            account=ar_account,
            debit=invoice.total_amount,
            narration=f"Invoice {invoice.invoice_number}"
        )
        
        # Cr Sales Revenue
        JournalLine.objects.create(
            journal=je,
            account=sales_account,
            credit=invoice.total_amount - (invoice.tax_amount or 0),
            narration=f"Sales revenue - {invoice.invoice_number}"
        )
        
        # Cr VAT Payable if tax exists
        if invoice.tax_amount and invoice.tax_amount > 0:
            vat_account = Account.objects.filter(code='2200').first()
            if not vat_account:
                vat_account = Account.objects.create(
                    code='2200',
                    name='VAT Payable',
                    account_type='liability'
                )
            
            JournalLine.objects.create(
                journal=je,
                account=vat_account,
                credit=invoice.tax_amount,
                narration=f"VAT on {invoice.invoice_number}"
            )
        
        # Link journal entry to invoice
        invoice.journal_entry = je
        invoice.status = 'posted'
        invoice.save(update_fields=['journal_entry', 'status'])
        
    except Exception as e:
        logger.error(f"Failed to create journal entry for invoice {invoice.invoice_number}: {e}")
        raise


# ============================
# Production Run Signals
# ============================

@receiver(post_save, sender=ProductionRun)
def auto_create_invoice_from_production(sender, instance, created, **kwargs):
    """
    Automatically create invoice when production run is completed
    This is for internal transfers or direct sales from production
    """
    if created:
        return
        
    if instance.status == 'completed' and not hasattr(instance, 'invoice'):
        # Only for finished goods that are sold directly
        if instance.product.category == 'finished' and instance.product.product_type in ['plumpy_nut', 'plumpy_sup']:
            with transaction.atomic():
                try:
                    # Get default customer (you might want to make this configurable)
                    default_customer = Customer.objects.filter(is_active=True).first()
                    
                    if not default_customer:
                        logger.warning(f"No customer found for production invoice from run {instance.id}")
                        return
                    
                    # Create invoice
                    invoice = SalesInvoice.objects.create(
                        customer=default_customer,
                        invoice_date=timezone.now().date(),
                        due_date=timezone.now().date() + timezone.timedelta(days=30),
                        status='draft',
                        notes=f"Invoice from production run #{instance.id}",
                        created_by=instance.created_by
                    )

                    # Use BOM to create invoice lines (per produced kg)
                    bom = instance.bom
                    produced_kg = instance.actual_quantity or instance.planned_quantity

                    for bom_line in bom.lines.all():
                        # Calculate quantity with wastage
                        line_qty = bom_line.quantity_per_kg * produced_kg
                        line_qty_with_wastage = line_qty * (1 + bom_line.wastage_percentage / 100)
                        
                        # Get standard price or cost
                        unit_price = bom_line.component.unit_cost or Decimal('0.00')
                        
                        SalesInvoiceLine.objects.create(
                            invoice=invoice,
                            item=bom_line.component,
                            description=f"From production run #{instance.id}",
                            quantity=line_qty_with_wastage,
                            unit=bom_line.unit,
                            unit_price=unit_price,
                            std_composition_pct=getattr(bom_line, 'std_composition_pct', None),
                            std_consumption_per_mt=getattr(bom_line, 'std_consumption_per_mt', None),
                            std_wastage_pct=bom_line.wastage_percentage,
                        )

                    invoice.calculate_totals()
                    
                    # Link invoice to production run
                    # Note: You may need to add a production_run field to SalesInvoice
                    # instance.invoice = invoice
                    # instance.save(update_fields=['invoice'])

                    logger.info(f"Auto-created invoice {invoice.invoice_number} from production run #{instance.id}")
                    
                except Exception as e:
                    logger.error(f"Failed to create invoice from production run #{instance.id}: {e}")


# ============================
# Sales Invoice Signals
# ============================

@receiver(pre_save, sender=SalesInvoice)
def set_invoice_overdue(sender, instance, **kwargs):
    """Auto-set overdue status if due date passed"""
    if instance.pk:  # Only for existing invoices
        if instance.due_date and instance.due_date < timezone.now().date():
            if instance.status not in ['paid', 'cancelled']:
                instance.status = 'overdue'


@receiver(post_save, sender=SalesInvoice)
def handle_invoice_status_change(sender, instance, created, **kwargs):
    """Handle invoice status changes"""
    if created:
        logger.info(f"Invoice {instance.invoice_number} created")
        return
    
    try:
        old_instance = SalesInvoice.objects.get(pk=instance.pk)
        
        # Status changed to posted
        if old_instance.status != 'posted' and instance.status == 'posted':
            handle_invoice_posted(instance)
        
        # Status changed to paid
        elif old_instance.status != 'paid' and instance.status == 'paid':
            handle_invoice_paid(instance)
        
        # Status changed to cancelled
        elif old_instance.status != 'cancelled' and instance.status == 'cancelled':
            handle_invoice_cancelled(instance)
            
    except SalesInvoice.DoesNotExist:
        pass


def handle_invoice_posted(invoice):
    """Handle invoice being posted"""
    logger.info(f"Invoice {invoice.invoice_number} posted")
    
    # Create journal entry if not exists
    if not invoice.journal_entry:
        create_invoice_journal_entry(invoice)


def handle_invoice_paid(invoice):
    """Handle invoice being marked as paid"""
    logger.info(f"Invoice {invoice.invoice_number} marked as paid")
    
    # Update sales order status if all invoices are paid
    if invoice.sales_order:
        all_paid = all(inv.status == 'paid' for inv in invoice.sales_order.invoices.all())
        if all_paid:
            invoice.sales_order.status = 'closed'
            invoice.sales_order.save(update_fields=['status'])


def handle_invoice_cancelled(invoice):
    """Handle invoice cancellation"""
    logger.info(f"Invoice {invoice.invoice_number} cancelled")
    
    # Reverse journal entry if exists
    if invoice.journal_entry:
        # You might want to create a reversing entry
        pass


# ============================
# Sales Payment Signals
# ============================

@receiver(post_save, sender=SalesPayment)
def handle_payment_received(sender, instance, created, **kwargs):
    """Handle payment received"""
    if created:
        logger.info(f"Payment of {instance.amount} received for invoice {instance.invoice.invoice_number}")
        
        # Check if invoice is now fully paid
        if instance.invoice.is_fully_paid:
            instance.invoice.status = 'paid'
            instance.invoice.save(update_fields=['status'])
            
            # Create journal entry for payment
            create_payment_journal_entry(instance)


def create_payment_journal_entry(payment):
    """Create journal entry for payment"""
    try:
        # Get accounts
        cash_account = Account.objects.filter(code='1010').first()
        ar_account = Account.objects.filter(code='1100').first()
        
        if not cash_account:
            cash_account = Account.objects.create(
                code='1010',
                name='Cash/Bank',
                account_type='asset'
            )
        
        if not ar_account:
            ar_account = Account.objects.create(
                code='1100',
                name='Accounts Receivable',
                account_type='asset'
            )
        
        # Create journal entry
        je = JournalEntry.objects.create(
            company=payment.invoice.customer.company,
            entry_date=payment.payment_date,
            reference=f"PAY-{payment.id}",
            narration=f"Payment received for {payment.invoice.invoice_number}",
            is_posted=True,
            posted_at=timezone.now()
        )
        
        # Dr Cash/Bank
        JournalLine.objects.create(
            journal=je,
            account=cash_account,
            debit=payment.amount,
            narration=f"Payment from {payment.invoice.customer.name}"
        )
        
        # Cr Accounts Receivable
        JournalLine.objects.create(
            journal=je,
            account=ar_account,
            credit=payment.amount,
            narration=f"Payment for {payment.invoice.invoice_number}"
        )
        
        # Link journal entry to payment
        payment.journal_entry = je
        payment.save(update_fields=['journal_entry'])
        
    except Exception as e:
        logger.error(f"Failed to create journal entry for payment {payment.id}: {e}")


# ============================
# Sales Shipment Signals - FIXED VERSION
# ============================

@receiver(post_save, sender=SalesShipment)
def handle_shipment_status_change(sender, instance, created, **kwargs):
    """Handle shipment status changes - FIXED to handle missing status field"""
    if created:
        logger.info(f"Shipment {instance.shipment_number} created")
        return
    
    try:
        old_instance = SalesShipment.objects.get(pk=instance.pk)
        
        # Check if the status field exists - if not, skip status comparison
        if not hasattr(instance, 'status'):
            logger.debug(f"Shipment {instance.shipment_number} has no 'status' field")
            return
            
        # Only proceed if both instances have the status field
        if hasattr(old_instance, 'status') and hasattr(instance, 'status'):
            # Status changed to shipped
            if old_instance.status != 'shipped' and instance.status == 'shipped':
                handle_shipment_shipped(instance)
            
            # Status changed to delivered
            elif old_instance.status != 'delivered' and instance.status == 'delivered':
                handle_shipment_delivered(instance)
        else:
            logger.debug(f"Shipment {instance.shipment_number} status field missing on old or new instance")
            
    except SalesShipment.DoesNotExist:
        pass
    except AttributeError as e:
        logger.error(f"AttributeError in shipment signal for {instance.shipment_number}: {e}")
        # Don't re-raise the exception - this prevents the error from breaking the save


def handle_shipment_shipped(shipment):
    """Handle shipment being marked as shipped"""
    logger.info(f"Shipment {shipment.shipment_number} shipped")
    
    # Update sales order status if all items shipped
    order = shipment.sales_order
    if hasattr(order, 'is_fully_shipped') and order.is_fully_shipped:
        if hasattr(order, 'status'):
            order.status = 'shipped'
            order.save(update_fields=['status'])


def handle_shipment_delivered(shipment):
    """Handle shipment being marked as delivered"""
    logger.info(f"Shipment {shipment.shipment_number} delivered")
    
    if hasattr(shipment, 'delivery_date'):
        shipment.delivery_date = timezone.now().date()
        shipment.save(update_fields=['delivery_date'])
    
    # Update sales order status if all shipments delivered
    order = shipment.sales_order
    if order and hasattr(order, 'shipments'):
        all_delivered = all(
            hasattr(s, 'status') and s.status == 'delivered' 
            for s in order.shipments.all()
        )
        if all_delivered and hasattr(order, 'status'):
            order.status = 'delivered'
            order.save(update_fields=['status'])