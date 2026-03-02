from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from django.db import transaction
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

from .models import (
    PurchaseOrder, PurchaseOrderApproval, PurchaseRequisition,
    GoodsReceipt, GoodsReceiptLine, Supplier, VendorPerformance
)
from apps.inventory.models import StockTransaction, CurrentStock, Lot

User = get_user_model()


# ============================
# Purchase Order Signals
# ============================

@receiver(pre_save, sender=PurchaseOrder)
def validate_purchase_order(sender, instance, **kwargs):
    """Validate purchase order before saving"""
    if instance.pk:  # Existing record
        old_instance = PurchaseOrder.objects.get(pk=instance.pk)
        
        # Prevent changing supplier after order is sent
        if old_instance.status in ['ordered', 'partial', 'received'] and old_instance.supplier_id != instance.supplier_id:
            raise ValidationError("Cannot change supplier after order has been sent to supplier")
        
        # Prevent reducing total amount after order is sent
        if old_instance.status in ['ordered', 'partial', 'received'] and instance.total_amount < old_instance.total_amount:
            raise ValidationError("Cannot reduce order total after order has been sent to supplier")


@receiver(post_save, sender=PurchaseOrder)
def handle_purchase_order_creation(sender, instance, created, **kwargs):
    """Handle post-save actions for purchase orders"""
    
    if created:
        # New purchase order created
        handle_new_purchase_order(instance)
    else:
        # Existing purchase order updated
        handle_purchase_order_update(instance)


def handle_new_purchase_order(instance):
    """Handle new purchase order creation"""
    # Create approval records if configured
    create_approval_records(instance)
    
    # Auto-generate PO number if not set (already handled in model save)
    
    # Send notification to approvers (optional)
    # send_approval_notification(instance)


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
        from .models import ApprovalLevel
        levels = ApprovalLevel.objects.filter(
            company=instance.company,
            is_active=True
        ).order_by('level')
        
        for level in levels:
            # Find approver based on role
            approver = User.objects.filter(
                userprofile__company=instance.company,
                userprofile__role=level.role,
                userprofile__is_active=True
            ).first()
            
            PurchaseOrderApproval.objects.create(
                po=instance,
                level=level.level,
                approver=approver,
                status='pending'
            )
        
        # Update approval status
        instance.update_approval_status()
        
    except Exception as e:
        # Log error but don't fail PO creation
        print(f"Error creating approval records for PO {instance.po_number}: {e}")


def handle_po_approved(instance):
    """Handle when a purchase order is approved"""
    # Send notification to procurement team
    # send_notification(f"PO {instance.po_number} has been approved")
    
    # Could automatically create a task to send to supplier
    pass


def handle_po_sent_to_supplier(instance):
    """Handle when a purchase order is sent to supplier"""
    # Update expected delivery date based on supplier lead time
    if instance.supplier.average_lead_time:
        # This would need to be implemented
        pass
    
    # Send confirmation email to supplier (optional)
    # send_po_to_supplier(instance)


def handle_po_received(instance):
    """Handle when a purchase order is fully received"""
    # Update vendor performance metrics
    update_vendor_performance(instance.supplier)
    
    # Send notification to requester
    if instance.requisition and instance.requisition.requested_by:
        # send_notification_to_requester(instance)
        pass


# ============================
# Purchase Order Approval Signals
# ============================

@receiver(post_save, sender=PurchaseOrderApproval)
def handle_approval_update(sender, instance, created, **kwargs):
    """Handle when an approval is created or updated"""
    if not created:
        # Approval was updated (approved/rejected)
        po = instance.po
        
        # Update PO approval status
        po.update_approval_status()
        
        # If rejected, notify requester
        if instance.status == 'rejected':
            # send_rejection_notification(po, instance)
            pass
        
        # If approved and all levels are done, notify procurement
        elif instance.status == 'approved':
            pending_approvals = po.approvals.filter(status='pending').exists()
            if not pending_approvals:
                # All approvals complete
                # send_notification(f"PO {po.po_number} has been fully approved")
                pass


# ============================
# Goods Receipt Signals
# ============================

@receiver(post_save, sender=GoodsReceipt)
def handle_goods_receipt(sender, instance, created, **kwargs):
    """Handle goods receipt creation"""
    if created:
        # Update PO status
        instance.update_po_status()
        
        # Update vendor performance metrics
        update_vendor_performance(instance.po.supplier, instance)


@receiver(post_save, sender=GoodsReceiptLine)
def handle_goods_receipt_line(sender, instance, created, **kwargs):
    """Handle goods receipt line creation"""
    if created:
        # Stock transaction and lot creation are handled in model save
        pass


# ============================
# Supplier Performance Signals
# ============================

def update_vendor_performance(supplier, goods_receipt=None):
    """Update vendor performance metrics"""
    from django.db.models import Avg, Count, Sum, Q
    from datetime import timedelta
    
    # Get date range (last 90 days)
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=90)
    
    # Get all receipts for this supplier in the period
    receipts = GoodsReceipt.objects.filter(
        po__supplier=supplier,
        receipt_date__range=[start_date, end_date]
    )
    
    # Calculate metrics
    total_orders = receipts.count()
    if total_orders == 0:
        return
    
    # On-time deliveries (received on or before expected date)
    on_time = receipts.filter(
        receipt_date__lte=models.F('po__expected_delivery_date')
    ).count()
    
    # Late deliveries
    late = receipts.filter(
        receipt_date__gt=models.F('po__expected_delivery_date')
    ).count()
    
    # Total value
    total_value = receipts.aggregate(
        total=Sum('lines__quantity_received' * models.F('lines__po_line__unit_price'))
    )['total'] or 0
    
    # Create or update performance record
    VendorPerformance.objects.update_or_create(
        supplier=supplier,
        period_start=start_date,
        period_end=end_date,
        defaults={
            'orders_count': total_orders,
            'on_time_deliveries': on_time,
            'late_deliveries': late,
            'total_order_value': total_value,
            'quality_score': supplier.quality_rating,  # This would come from QC inspections
        }
    )


# ============================
# Purchase Requisition Signals
# ============================

@receiver(post_save, sender=PurchaseRequisition)
def handle_requisition_status_change(sender, instance, **kwargs):
    """Handle purchase requisition status changes"""
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


def handle_requisition_approved(instance):
    """Handle approved requisition"""
    # Notify requester
    if instance.requested_by:
        # send_notification(instance.requested_by, f"Requisition {instance.requisition_number} approved")
        pass
    
    # Could auto-create purchase order (optional)
    # auto_create_po_from_requisition(instance)


def handle_requisition_rejected(instance):
    """Handle rejected requisition"""
    # Notify requester
    if instance.requested_by:
        # send_notification(instance.requested_by, f"Requisition {instance.requisition_number} rejected")
        pass


# ============================
# Helper Functions (Optional)
# ============================

def send_approval_notification(po):
    """Send notification to approvers"""
    # Implementation would depend on your notification system
    pass


def send_po_to_supplier(po):
    """Send PO to supplier via email"""
    # Implementation would depend on your email system
    pass


def auto_create_po_from_requisition(requisition):
    """Automatically create PO from approved requisition"""
    # This would be implemented if you want auto-PO creation
    pass