from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from django.db import transaction
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.db import models  # Add this import for F() expressions
from datetime import timedelta
import logging

from .models import (
    PurchaseOrder, PurchaseOrderApproval, PurchaseRequisition,
    GoodsReceipt, GoodsReceiptLine, Supplier, VendorPerformance
)
from apps.inventory.models import StockTransaction, Lot
from apps.core.models import Company

logger = logging.getLogger(__name__)
User = get_user_model()


# ============================
# Helper Functions
# ============================

def get_current_company(instance):
    """Helper to get company from instance or raise error"""
    if hasattr(instance, 'company') and instance.company:
        return instance.company
    
    # Try to get company from related objects
    if hasattr(instance, 'supplier') and instance.supplier:
        return instance.supplier.company
    
    if hasattr(instance, 'po') and instance.po and instance.po.company:
        return instance.po.company
    
    return None


# ============================
# Purchase Order Signals
# ============================

@receiver(pre_save, sender=PurchaseOrder)
def validate_purchase_order(sender, instance, **kwargs):
    """Validate purchase order before saving"""
    if instance.pk:  # Existing record
        try:
            old_instance = PurchaseOrder.objects.get(pk=instance.pk)
            
            # Prevent changing supplier after order is sent
            if old_instance.status in ['ordered', 'partial', 'received'] and old_instance.supplier_id != instance.supplier_id:
                raise ValidationError("Cannot change supplier after order has been sent to supplier")
            
            # Prevent reducing total amount after order is sent
            if old_instance.status in ['ordered', 'partial', 'received'] and instance.total_amount < old_instance.total_amount:
                raise ValidationError("Cannot reduce order total after order has been sent to supplier")
        
        except PurchaseOrder.DoesNotExist:
            pass  # New instance, no validation needed


@receiver(post_save, sender=PurchaseOrder)
def handle_purchase_order_creation(sender, instance, created, **kwargs):
    """Handle post-save actions for purchase orders"""
    try:
        if created:
            # New purchase order created
            handle_new_purchase_order(instance)
        else:
            # Existing purchase order updated
            handle_purchase_order_update(instance)
    except Exception as e:
        logger.error(f"Error in purchase order signal for PO {instance.po_number}: {e}")


def handle_new_purchase_order(instance):
    """Handle new purchase order creation"""
    # Create approval records if configured
    create_approval_records(instance)
    
    # Auto-generate PO number if not set (already handled in model save)
    
    # Log the creation
    logger.info(f"New purchase order created: {instance.po_number}")


def handle_purchase_order_update(instance):
    """Handle purchase order updates"""
    try:
        old_instance = PurchaseOrder.objects.get(pk=instance.pk)
        
        # Check if status changed to 'approved'
        if old_instance.status != 'approved' and instance.status == 'approved':
            handle_po_approved(instance)
        
        # Check if status changed to 'ordered'
        elif old_instance.status != 'ordered' and instance.status == 'ordered':
            handle_po_sent_to_supplier(instance)
        
        # Check if status changed to 'received'
        elif old_instance.status != 'received' and instance.status == 'received':
            handle_po_received(instance)
            
    except PurchaseOrder.DoesNotExist:
        pass


def create_approval_records(instance):
    """Create approval records for a purchase order"""
    try:
        # Get approval levels from company settings
        # This assumes you have an ApprovalLevel model - if not, you can skip
        # or implement a simpler approval workflow
        company = get_current_company(instance)
        
        if not company:
            logger.warning(f"No company found for PO {instance.po_number}, skipping approval records")
            return
        
        # Simple approval workflow - create one approval record
        # Modify this based on your actual approval workflow
        PurchaseOrderApproval.objects.create(
            po=instance,
            level=1,
            approver=None,  # Will be assigned later
            status='pending'
        )
        
        # Update approval status
        instance.update_approval_status()
        
    except Exception as e:
        logger.error(f"Error creating approval records for PO {instance.po_number}: {e}")


def handle_po_approved(instance):
    """Handle when a purchase order is approved"""
    logger.info(f"PO {instance.po_number} has been approved")
    # Send notification to procurement team
    # send_notification(f"PO {instance.po_number} has been approved")


def handle_po_sent_to_supplier(instance):
    """Handle when a purchase order is sent to supplier"""
    logger.info(f"PO {instance.po_number} has been sent to supplier")
    # Update expected delivery date based on supplier lead time
    # if instance.supplier and instance.supplier.average_lead_time:
    #     instance.expected_delivery_date = timezone.now().date() + timedelta(
    #         days=instance.supplier.average_lead_time
    #     )
    #     instance.save(update_fields=['expected_delivery_date'])


def handle_po_received(instance):
    """Handle when a purchase order is fully received"""
    logger.info(f"PO {instance.po_number} has been fully received")
    # Update vendor performance metrics
    update_vendor_performance(instance.supplier)


# ============================
# Purchase Order Approval Signals
# ============================

@receiver(post_save, sender=PurchaseOrderApproval)
def handle_approval_update(sender, instance, created, **kwargs):
    """Handle when an approval is created or updated"""
    try:
        if not created:
            # Approval was updated (approved/rejected)
            po = instance.po
            
            # Update PO approval status
            po.update_approval_status()
            
            # If rejected, notify requester
            if instance.status == 'rejected':
                logger.info(f"PO {po.po_number} rejected at level {instance.level}")
                # send_rejection_notification(po, instance)
            
            # If approved and all levels are done, notify procurement
            elif instance.status == 'approved':
                pending_approvals = po.approvals.filter(status='pending').exists()
                if not pending_approvals:
                    logger.info(f"PO {po.po_number} has been fully approved")
                    # send_notification(f"PO {po.po_number} has been fully approved")
    except Exception as e:
        logger.error(f"Error in approval signal: {e}")


# ============================
# Goods Receipt Signals
# ============================

@receiver(post_save, sender=GoodsReceipt)
def handle_goods_receipt(sender, instance, created, **kwargs):
    """Handle goods receipt creation"""
    try:
        if created:
            # Update PO status
            instance.update_po_status()
            
            # Update vendor performance metrics
            if instance.po and instance.po.supplier:
                update_vendor_performance(instance.po.supplier, instance)
    except Exception as e:
        logger.error(f"Error in goods receipt signal for {instance.receipt_number}: {e}")


@receiver(post_save, sender=GoodsReceiptLine)
def handle_goods_receipt_line(sender, instance, created, **kwargs):
    """Handle goods receipt line creation"""
    try:
        if created:
            # Stock transaction and lot creation are handled in model save
            # But we can add additional logic here if needed
            pass
    except Exception as e:
        logger.error(f"Error in goods receipt line signal: {e}")


# ============================
# Supplier Performance Signals
# ============================

def update_vendor_performance(supplier, goods_receipt=None):
    """Update vendor performance metrics"""
    try:
        if not supplier:
            logger.warning("No supplier provided for performance update")
            return
        
        # Get date range (last 90 days)
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=90)
        
        # Get all receipts for this supplier in the period
        receipts = GoodsReceipt.objects.filter(
            po__supplier=supplier,
            receipt_date__range=[start_date, end_date]
        ).select_related('po')
        
        # Calculate metrics
        total_orders = receipts.count()
        if total_orders == 0:
            logger.debug(f"No receipts for supplier {supplier.name} in last 90 days")
            return
        
        # On-time deliveries (received on or before expected date)
        on_time = receipts.filter(
            receipt_date__lte=models.F('po__expected_delivery_date')
        ).count()
        
        # Late deliveries
        late = receipts.filter(
            receipt_date__gt=models.F('po__expected_delivery_date')
        ).count()
        
        # Total value calculation - need to aggregate through lines
        total_value = 0
        for receipt in receipts:
            lines_total = receipt.lines.aggregate(
                total=models.Sum(models.F('quantity_received') * models.F('po_line__unit_price'))
            )['total'] or 0
            total_value += lines_total
        
        # Create or update performance record
        performance, created = VendorPerformance.objects.update_or_create(
            supplier=supplier,
            period_start=start_date,
            period_end=end_date,
            defaults={
                'orders_count': total_orders,
                'on_time_deliveries': on_time,
                'late_deliveries': late,
                'total_order_value': total_value,
                'quality_score': supplier.quality_rating or 0,
            }
        )
        
        logger.info(f"{'Created' if created else 'Updated'} performance record for {supplier.name}")
        
    except Exception as e:
        logger.error(f"Error updating vendor performance for {supplier.name}: {e}")


# ============================
# Purchase Requisition Signals
# ============================

@receiver(post_save, sender=PurchaseRequisition)
def handle_requisition_status_change(sender, instance, created, **kwargs):
    """Handle purchase requisition status changes"""
    try:
        if created:
            logger.info(f"New requisition created: {instance.requisition_number}")
            return
        
        try:
            old_instance = PurchaseRequisition.objects.get(pk=instance.pk)
            
            # Status changed to approved
            if old_instance.status != 'approved' and instance.status == 'approved':
                handle_requisition_approved(instance)
            
            # Status changed to rejected
            elif old_instance.status != 'rejected' and instance.status == 'rejected':
                handle_requisition_rejected(instance)
                
        except PurchaseRequisition.DoesNotExist:
            pass
            
    except Exception as e:
        logger.error(f"Error in requisition signal: {e}")


def handle_requisition_approved(instance):
    """Handle approved requisition"""
    logger.info(f"Requisition {instance.requisition_number} approved")
    # Notify requester
    if instance.requested_by:
        # send_notification(instance.requested_by, f"Requisition {instance.requisition_number} approved")
        pass


def handle_requisition_rejected(instance):
    """Handle rejected requisition"""
    logger.info(f"Requisition {instance.requisition_number} rejected")
    # Notify requester
    if instance.requested_by:
        # send_notification(instance.requested_by, f"Requisition {instance.requisition_number} rejected")
        pass


# ============================
# Company Model Signals (if needed)
# ============================

@receiver(pre_save, sender=Company)
def validate_company(sender, instance, **kwargs):
    """Validate company before saving"""
    if instance.pk:
        old_company = Company.objects.get(pk=instance.pk)
        # Add any company validation logic here
        pass