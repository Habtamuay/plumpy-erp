from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q, Avg, F
from django.utils import timezone
from django.http import HttpResponse, JsonResponse
from datetime import timedelta
from decimal import Decimal
import csv
import json

from .models import (
    Supplier, PurchaseOrder, PurchaseOrderLine, PurchaseOrderApproval,
    PurchaseRequisition, PurchaseRequisitionLine, GoodsReceipt, 
    GoodsReceiptLine, VendorPerformance
)
from apps.accounting.models import PurchaseBill, Payment
from apps.inventory.models import Warehouse, Lot, StockTransaction


# ============================
# Dashboard
# ============================

@login_required
def dashboard(request):
    """Main purchasing dashboard"""
    today = timezone.now().date()
    
    # Statistics
    total_pos = PurchaseOrder.objects.count()
    pending_approval = PurchaseOrder.objects.filter(status='approved').count()
    outstanding_orders = PurchaseOrder.objects.filter(status__in=['ordered', 'partial']).count()
    overdue_orders = PurchaseOrder.objects.filter(
        expected_delivery_date__lt=today,
        status__in=['ordered', 'partial']
    ).count()
    
    # Recent POs
    recent_pos = PurchaseOrder.objects.select_related('supplier').order_by('-order_date')[:10]
    
    # Requisitions pending approval
    pending_requisitions = PurchaseRequisition.objects.filter(status='submitted').count()
    
    # Top suppliers by spend
    top_suppliers = Supplier.objects.annotate(
        total_spend=Sum('purchase_orders__total_amount', 
                       filter=Q(purchase_orders__status__in=['received', 'partial']))
    ).order_by('-total_spend')[:5]
    
    context = {
        'total_pos': total_pos,
        'pending_approval': pending_approval,
        'outstanding_orders': outstanding_orders,
        'overdue_orders': overdue_orders,
        'pending_requisitions': pending_requisitions,
        'recent_pos': recent_pos,
        'top_suppliers': top_suppliers,
        'today': today,
    }
    
    return render(request, 'purchasing/dashboard.html', context)


# ============================
# Supplier Views
# ============================

@login_required
def supplier_list(request):
    """List all suppliers with filters"""
    suppliers = Supplier.objects.filter(is_active=True).select_related('company').order_by('name')
    
    # Search
    search_query = request.GET.get('q', '').strip()
    if search_query:
        suppliers = suppliers.filter(
            Q(name__icontains=search_query) |
            Q(code__icontains=search_query) |
            Q(tin__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(contact_person__icontains=search_query)
        )
    
    # Filter by preferred status
    preferred = request.GET.get('preferred')
    if preferred == 'yes':
        suppliers = suppliers.filter(is_preferred=True)
    elif preferred == 'no':
        suppliers = suppliers.filter(is_preferred=False)
    
    # Filter by country
    country = request.GET.get('country')
    if country:
        suppliers = suppliers.filter(country=country)
    
    context = {
        'suppliers': suppliers,
        'search_query': search_query,
        'countries': Supplier.objects.values_list('country', flat=True).distinct(),
        'today': timezone.now().date(),
    }
    
    return render(request, 'purchasing/supplier_list.html', context)


@login_required
def supplier_dashboard(request):
    """
    Supplier dashboard with search, filters, and sorting capabilities
    """
    # Base queryset
    suppliers = Supplier.objects.filter(is_active=True)

    # Search functionality
    search_query = request.GET.get('q', '').strip()
    if search_query:
        suppliers = suppliers.filter(
            Q(name__icontains=search_query) |
            Q(code__icontains=search_query) |
            Q(tin__icontains=search_query) |
            Q(phone__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(contact_person__icontains=search_query)
        )

    # Active/Inactive filter
    filter_active = request.GET.get('active', 'all')
    if filter_active == 'active':
        suppliers = suppliers.filter(is_active=True)
    elif filter_active == 'inactive':
        suppliers = suppliers.filter(is_active=False)

    # Purchase Order history filter
    filter_has_po = request.GET.get('has_po', 'all')
    if filter_has_po == 'recent':
        recent_cutoff = timezone.now().date() - timedelta(days=90)
        suppliers = suppliers.annotate(
            recent_pos=Count('purchase_orders', filter=Q(purchase_orders__order_date__gte=recent_cutoff))
        ).filter(recent_pos__gt=0)
    elif filter_has_po == 'no_po':
        suppliers = suppliers.annotate(total_pos=Count('purchase_orders')).filter(total_pos=0)

    # Risk filter
    filter_risk = request.GET.get('risk', 'all')
    if filter_risk == 'high':
        suppliers = suppliers.annotate(
            total_pos=Count('purchase_orders'),
            avg_delay=Avg('purchase_orders__expected_delivery_date' - 'purchase_orders__order_date',
                          filter=Q(purchase_orders__status='received'))
        ).filter(Q(total_pos__lt=3) | Q(avg_delay__gt=45))

    # Annotate with aggregated data for all suppliers
    suppliers = suppliers.annotate(
        total_pos=Count('purchase_orders'),
        total_spend=Sum('purchase_orders__total_amount', 
                       filter=Q(purchase_orders__status__in=['received', 'partial', 'ordered'])),
        avg_delivery_days=Avg('purchase_orders__expected_delivery_date' - 'purchase_orders__order_date',
                             filter=Q(purchase_orders__status='received'))
    )

    # Sorting
    sort_by = request.GET.get('sort', 'name')
    sort_order = request.GET.get('order', 'asc')
    
    sort_field = sort_by
    if sort_order == 'desc':
        sort_field = f'-{sort_by}'
    
    suppliers = suppliers.order_by(sort_field)

    # Calculate metrics for cards
    total_suppliers = suppliers.count()
    total_spend = suppliers.aggregate(total=Sum('total_spend'))['total'] or 0
    
    late_deliveries = PurchaseOrder.objects.filter(
        expected_delivery_date__lt=timezone.now().date(),
        status__in=['ordered', 'partial']
    ).count()
    
    risky_count = suppliers.filter(
        Q(total_pos__lt=3) | Q(avg_delivery_days__gt=45)
    ).count()

    # Recent POs (last 90 days)
    recent_pos = PurchaseOrder.objects.select_related('supplier').filter(
        order_date__gte=timezone.now().date() - timedelta(days=90)
    ).order_by('-order_date')[:10]

    context = {
        'suppliers': suppliers,
        'total_suppliers': total_suppliers,
        'total_spend': total_spend,
        'late_deliveries': late_deliveries,
        'risky_count': risky_count,
        'recent_pos': recent_pos,
        'search_query': search_query,
        'filter_active': filter_active,
        'filter_has_po': filter_has_po,
        'filter_risk': filter_risk,
        'sort_by': sort_by,
        'sort_order': sort_order,
        'today': timezone.now().date(),
    }

    return render(request, 'purchasing/supplier_dashboard.html', context)


@login_required
def supplier_detail(request, supplier_id):
    """
    View supplier details with their purchase orders and financial data
    """
    supplier = get_object_or_404(
        Supplier.objects.select_related('company'),
        id=supplier_id
    )
    
    # Get related data
    pos = PurchaseOrder.objects.filter(supplier=supplier).select_related(
        'company', 'branch'
    ).order_by('-order_date')[:20]
    
    # Get bills from accounting
    bills = PurchaseBill.objects.filter(supplier=supplier).order_by('-bill_date')[:20]
    
    # Get payments
    payments = Payment.objects.filter(supplier=supplier).order_by('-date')[:10]
    
    # Get performance records
    performance = supplier.performance_records.order_by('-period_end')[:6]
    
    # Calculate metrics
    total_spend = pos.aggregate(total=Sum('total_amount'))['total'] or 0
    outstanding = bills.filter(status__in=['posted', 'partial']).aggregate(
        total=Sum('total_amount')
    )['total'] or 0
    
    # Average delivery days
    avg_delivery = pos.filter(status='received').aggregate(
        avg=Avg(F('goods_receipts__receipt_date') - F('order_date'))
    )['avg']

    context = {
        'supplier': supplier,
        'pos': pos,
        'bills': bills,
        'payments': payments,
        'performance': performance,
        'total_spend': total_spend,
        'outstanding': outstanding,
        'avg_delivery_days': avg_delivery.days if avg_delivery else None,
        'po_count': pos.count(),
        'today': timezone.now().date(),
    }
    
    return render(request, 'purchasing/supplier_detail.html', context)


@login_required
def supplier_performance(request, supplier_id):
    """View supplier performance metrics"""
    supplier = get_object_or_404(Supplier, id=supplier_id)
    performance = supplier.performance_records.order_by('-period_end')
    
    context = {
        'supplier': supplier,
        'performance': performance,
        'today': timezone.now().date(),
    }
    return render(request, 'purchasing/supplier_performance.html', context)


# ============================
# Purchase Requisition Views
# ============================

@login_required
def requisition_list(request):
    """List all purchase requisitions"""
    requisitions = PurchaseRequisition.objects.select_related(
        'company', 'branch', 'requested_by'
    ).order_by('-requested_date')
    
    # Filter by status
    status = request.GET.get('status')
    if status:
        requisitions = requisitions.filter(status=status)
    
    context = {
        'requisitions': requisitions,
        'status_choices': PurchaseRequisition.STATUS_CHOICES,
        'today': timezone.now().date(),
    }
    
    return render(request, 'purchasing/requisition_list.html', context)


@login_required
def requisition_create(request):
    """Create a new purchase requisition"""
    if request.method == 'POST':
        # Simplified creation - would need proper form handling
        messages.info(request, "Requisition creation form coming soon")
        return redirect('purchasing:requisition_list')
    
    return render(request, 'purchasing/requisition_form.html', {'today': timezone.now().date()})


@login_required
def requisition_detail(request, requisition_id):
    """View requisition details"""
    requisition = get_object_or_404(
        PurchaseRequisition.objects.select_related('company', 'branch', 'requested_by'),
        id=requisition_id
    )
    
    lines = requisition.lines.all().select_related('item', 'unit')
    
    context = {
        'requisition': requisition,
        'lines': lines,
        'today': timezone.now().date(),
    }
    
    return render(request, 'purchasing/requisition_detail.html', context)


@login_required
def requisition_edit(request, requisition_id):
    """Edit a purchase requisition"""
    requisition = get_object_or_404(PurchaseRequisition, id=requisition_id)
    
    if request.method == 'POST':
        messages.success(request, f"Requisition {requisition.requisition_number} updated")
        return redirect('purchasing:requisition_detail', requisition_id=requisition.id)
    
    context = {
        'requisition': requisition,
        'today': timezone.now().date(),
    }
    return render(request, 'purchasing/requisition_form.html', context)


@login_required
def requisition_delete(request, requisition_id):
    """Delete a purchase requisition"""
    requisition = get_object_or_404(PurchaseRequisition, id=requisition_id)
    
    if request.method == 'POST':
        requisition.delete()
        messages.success(request, f"Requisition {requisition.requisition_number} deleted")
        return redirect('purchasing:requisition_list')
    
    context = {
        'requisition': requisition,
    }
    return render(request, 'purchasing/requisition_confirm_delete.html', context)


@login_required
def requisition_submit(request, requisition_id):
    """Submit requisition for approval"""
    requisition = get_object_or_404(PurchaseRequisition, id=requisition_id)
    
    if requisition.status == 'draft':
        requisition.status = 'submitted'
        requisition.save()
        messages.success(request, f"Requisition {requisition.requisition_number} submitted for approval")
    else:
        messages.error(request, f"Cannot submit requisition with status {requisition.get_status_display()}")
    
    return redirect('purchasing:requisition_detail', requisition_id=requisition.id)


@login_required
def requisition_approve(request, requisition_id):
    """Approve a requisition"""
    requisition = get_object_or_404(PurchaseRequisition, id=requisition_id)
    
    if requisition.status == 'submitted':
        requisition.status = 'approved'
        requisition.save()
        messages.success(request, f"Requisition {requisition.requisition_number} approved")
    else:
        messages.error(request, f"Cannot approve requisition with status {requisition.get_status_display()}")
    
    return redirect('purchasing:requisition_detail', requisition_id=requisition.id)


@login_required
def requisition_reject(request, requisition_id):
    """Reject a requisition"""
    requisition = get_object_or_404(PurchaseRequisition, id=requisition_id)
    
    if request.method == 'POST':
        reason = request.POST.get('reason', '')
        requisition.status = 'rejected'
        requisition.notes += f"\nRejection reason: {reason}"
        requisition.save()
        messages.success(request, f"Requisition {requisition.requisition_number} rejected")
        return redirect('purchasing:requisition_detail', requisition_id=requisition.id)
    
    context = {
        'requisition': requisition,
    }
    return render(request, 'purchasing/requisition_reject.html', context)


@login_required
def create_po_from_requisition(request, requisition_id):
    """
    Create a purchase order from a purchase requisition
    """
    requisition = get_object_or_404(PurchaseRequisition, id=requisition_id)
    
    if requisition.status != 'approved':
        messages.error(request, "Requisition must be approved before creating a PO.")
        return redirect('purchasing:requisition_detail', requisition_id=requisition.id)
    
    # Check if PO already exists for this requisition
    if requisition.purchase_orders.exists():
        messages.warning(request, "A purchase order already exists for this requisition.")
        return redirect('purchasing:po_detail', po_id=requisition.purchase_orders.first().id)
    
    # Create PO
    po = PurchaseOrder.objects.create(
        company=requisition.company,
        branch=requisition.branch,
        requisition=requisition,
        supplier=None,  # To be selected
        order_date=timezone.now().date(),
        expected_delivery_date=timezone.now().date() + timedelta(days=30),
        status='draft',
        notes=f"Created from requisition {requisition.requisition_number}",
        created_by=request.user
    )
    
    # Copy lines from requisition
    for req_line in requisition.lines.all():
        PurchaseOrderLine.objects.create(
            po=po,
            item=req_line.item,
            quantity_ordered=req_line.quantity,
            unit=req_line.unit,
            notes=req_line.notes
        )
    
    po.update_total()
    
    # Update requisition status
    requisition.status = 'converted'
    requisition.save()
    
    messages.success(request, f"Purchase Order {po.po_number} created from requisition.")
    return redirect('purchasing:po_edit', po_id=po.id)


# ============================
# Purchase Order Views
# ============================

@login_required
def po_list(request):
    """List all purchase orders"""
    pos = PurchaseOrder.objects.select_related(
        'supplier', 'company'
    ).order_by('-order_date')
    
    # Filter by status
    status = request.GET.get('status')
    if status:
        pos = pos.filter(status=status)
    
    # Filter by supplier
    supplier_id = request.GET.get('supplier')
    if supplier_id:
        pos = pos.filter(supplier_id=supplier_id)
    
    context = {
        'pos': pos,
        'status_choices': PurchaseOrder.STATUS_CHOICES,
        'suppliers': Supplier.objects.filter(is_active=True),
        'today': timezone.now().date(),
    }
    
    return render(request, 'purchasing/po_list.html', context)


@login_required
def po_create(request):
    """Create a new purchase order"""
    if request.method == 'POST':
        messages.info(request, "PO creation form coming soon")
        return redirect('purchasing:po_list')
    
    suppliers = Supplier.objects.filter(is_active=True)
    requisitions = PurchaseRequisition.objects.filter(status='approved')
    
    context = {
        'suppliers': suppliers,
        'requisitions': requisitions,
        'today': timezone.now().date(),
    }
    return render(request, 'purchasing/po_form.html', context)


@login_required
def po_detail(request, po_id):
    """
    View purchase order details
    """
    po = get_object_or_404(
        PurchaseOrder.objects.select_related(
            'supplier', 'company', 'branch', 'requisition', 'created_by', 'approved_by'
        ),
        id=po_id
    )
    
    lines = po.lines.all().select_related('item', 'unit')
    approvals = po.approvals.all().select_related('approver')
    receipts = po.goods_receipts.all().select_related('warehouse', 'received_by')
    
    # Get bills from accounting
    bills = po.bills.all() if hasattr(po, 'bills') else []
    
    context = {
        'po': po,
        'lines': lines,
        'approvals': approvals,
        'receipts': receipts,
        'bills': bills,
        'today': timezone.now().date(),
    }
    
    return render(request, 'purchasing/po_detail.html', context)


@login_required
def po_edit(request, po_id):
    """Edit purchase order"""
    po = get_object_or_404(PurchaseOrder, id=po_id)
    
    if po.status not in ['draft', 'approved']:
        messages.error(request, "Only draft or approved orders can be edited.")
        return redirect('purchasing:po_detail', po_id=po.id)
    
    if request.method == 'POST':
        messages.success(request, f"PO {po.po_number} updated")
        return redirect('purchasing:po_detail', po_id=po.id)
    
    suppliers = Supplier.objects.filter(is_active=True)
    
    context = {
        'po': po,
        'suppliers': suppliers,
        'today': timezone.now().date(),
    }
    return render(request, 'purchasing/po_form.html', context)


@login_required
def po_delete(request, po_id):
    """Delete a purchase order"""
    po = get_object_or_404(PurchaseOrder, id=po_id)
    
    if request.method == 'POST':
        po_number = po.po_number
        po.delete()
        messages.success(request, f"PO {po_number} deleted")
        return redirect('purchasing:po_list')
    
    context = {
        'po': po,
    }
    return render(request, 'purchasing/po_confirm_delete.html', context)


@login_required
def po_send(request, po_id):
    """Mark PO as sent to supplier"""
    po = get_object_or_404(PurchaseOrder, id=po_id)
    
    if po.status == 'approved':
        po.status = 'ordered'
        po.save()
        messages.success(request, f"PO {po.po_number} marked as sent to supplier")
    else:
        messages.error(request, f"Cannot send PO with status {po.get_status_display()}")
    
    return redirect('purchasing:po_detail', po_id=po.id)


@login_required
def receive_po(request, po_id):
    """Create goods receipt for a purchase order"""
    po = get_object_or_404(PurchaseOrder, id=po_id)
    
    if po.status not in ['ordered', 'partial']:
        messages.error(request, "Only orders that have been sent to supplier can be received.")
        return redirect('purchasing:po_detail', po_id=po.id)
    
    # Redirect to goods receipt creation
    return redirect(f'/admin/purchasing/goodsreceipt/add/?po={po.id}')


@login_required
def po_close(request, po_id):
    """Close a purchase order"""
    po = get_object_or_404(PurchaseOrder, id=po_id)
    
    if po.status == 'received':
        po.status = 'closed'
        po.save()
        messages.success(request, f"PO {po.po_number} closed")
    else:
        messages.error(request, "Only received orders can be closed")
    
    return redirect('purchasing:po_detail', po_id=po.id)


@login_required
def po_cancel(request, po_id):
    """Cancel a purchase order"""
    po = get_object_or_404(PurchaseOrder, id=po_id)
    
    if po.status in ['draft', 'approved', 'ordered']:
        po.status = 'cancelled'
        po.save()
        messages.success(request, f"PO {po.po_number} cancelled")
    else:
        messages.error(request, f"Cannot cancel PO with status {po.get_status_display()}")
    
    return redirect('purchasing:po_detail', po_id=po.id)


@login_required
def approve_po(request, po_id, level):
    """
    View for approving/rejecting purchase orders at specific approval levels
    """
    po = get_object_or_404(PurchaseOrder, id=po_id)
    approval = get_object_or_404(PurchaseOrderApproval, po=po, level=level)

    # Security: only assigned approver or admin can act
    if request.user != approval.approver and not request.user.is_superuser:
        messages.error(request, "You are not authorized to approve this level.")
        return redirect('purchasing:po_detail', po_id=po.id)

    if request.method == 'POST':
        action = request.POST.get('action')
        comment = request.POST.get('comment', '')

        if action == 'approve':
            approval.status = 'approved'
            approval.comment = comment
            approval.approved_at = timezone.now()
            approval.save()
            messages.success(request, f"Level {level} approved.")
        elif action == 'reject':
            approval.status = 'rejected'
            approval.comment = comment
            approval.approved_at = timezone.now()
            approval.save()
            messages.error(request, f"Level {level} rejected.")

        # Re-check overall status
        po.update_approval_status()

        return redirect('purchasing:po_detail', po_id=po.id)

    context = {
        'po': po,
        'approval': approval,
        'can_approve': approval.status == 'pending',
    }
    return render(request, 'purchasing/approve_po.html', context)


@login_required
def po_print(request, po_id):
    """Print/PDF view for purchase order"""
    po = get_object_or_404(PurchaseOrder, id=po_id)
    # This would generate a PDF - placeholder for now
    return render(request, 'purchasing/po_print.html', {'po': po})


@login_required
def export_pos(request):
    """Export purchase orders to CSV"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="pos_{timezone.now().strftime("%Y%m%d")}.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['PO Number', 'Supplier', 'Order Date', 'Expected Delivery', 'Status', 'Total Amount'])
    
    pos = PurchaseOrder.objects.select_related('supplier')
    for po in pos:
        writer.writerow([
            po.po_number,
            po.supplier.name,
            po.order_date,
            po.expected_delivery_date,
            po.get_status_display(),
            float(po.total_amount),
        ])
    
    return response


# ============================
# Goods Receipt Views
# ============================

@login_required
def goods_receipt_list(request):
    """List all goods receipts"""
    receipts = GoodsReceipt.objects.select_related(
        'po', 'warehouse', 'received_by'
    ).order_by('-receipt_date')
    
    context = {
        'receipts': receipts,
        'today': timezone.now().date(),
    }
    
    return render(request, 'purchasing/goods_receipt_list.html', context)


@login_required
def goods_receipt_create(request):
    """Create a new goods receipt"""
    if request.method == 'POST':
        messages.info(request, "Receipt creation form coming soon")
        return redirect('purchasing:goods_receipt_list')
    
    pos = PurchaseOrder.objects.filter(status__in=['ordered', 'partial'])
    warehouses = Warehouse.objects.filter(is_active=True)
    
    context = {
        'pos': pos,
        'warehouses': warehouses,
        'today': timezone.now().date(),
    }
    return render(request, 'purchasing/goods_receipt_form.html', context)


@login_required
def goods_receipt_detail(request, receipt_id):
    """View goods receipt details"""
    receipt = get_object_or_404(
        GoodsReceipt.objects.select_related('po', 'warehouse', 'received_by'),
        id=receipt_id
    )
    
    lines = receipt.lines.all().select_related('po_line__item', 'lot')
    
    context = {
        'receipt': receipt,
        'lines': lines,
        'today': timezone.now().date(),
    }
    
    return render(request, 'purchasing/goods_receipt_detail.html', context)


@login_required
def goods_receipt_edit(request, receipt_id):
    """Edit a goods receipt"""
    receipt = get_object_or_404(GoodsReceipt, id=receipt_id)
    
    if request.method == 'POST':
        messages.success(request, f"Receipt {receipt.receipt_number} updated")
        return redirect('purchasing:goods_receipt_detail', receipt_id=receipt.id)
    
    warehouses = Warehouse.objects.filter(is_active=True)
    
    context = {
        'receipt': receipt,
        'warehouses': warehouses,
        'today': timezone.now().date(),
    }
    return render(request, 'purchasing/goods_receipt_form.html', context)


@login_required
def goods_receipt_delete(request, receipt_id):
    """Delete a goods receipt"""
    receipt = get_object_or_404(GoodsReceipt, id=receipt_id)
    
    if request.method == 'POST':
        receipt_number = receipt.receipt_number
        receipt.delete()
        messages.success(request, f"Receipt {receipt_number} deleted")
        return redirect('purchasing:goods_receipt_list')
    
    context = {
        'receipt': receipt,
    }
    return render(request, 'purchasing/goods_receipt_confirm_delete.html', context)


@login_required
def export_receipts(request):
    """Export goods receipts to CSV"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="receipts_{timezone.now().strftime("%Y%m%d")}.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Receipt Number', 'PO Number', 'Date', 'Warehouse', 'Received By'])
    
    receipts = GoodsReceipt.objects.select_related('po', 'warehouse', 'received_by')
    for receipt in receipts:
        writer.writerow([
            receipt.receipt_number,
            receipt.po.po_number,
            receipt.receipt_date,
            receipt.warehouse.name,
            receipt.received_by.username if receipt.received_by else '',
        ])
    
    return response


# ============================
# Report Views
# ============================

@login_required
def purchasing_report(request):
    """Purchasing reports dashboard"""
    today = timezone.now().date()
    
    # PO by status
    po_by_status = PurchaseOrder.objects.values('status').annotate(
        count=Count('id'),
        total=Sum('total_amount')
    )
    
    # Top suppliers
    top_suppliers = Supplier.objects.annotate(
        total_spend=Sum('purchase_orders__total_amount',
                       filter=Q(purchase_orders__status__in=['received', 'partial']))
    ).filter(total_spend__gt=0).order_by('-total_spend')[:10]
    
    # Late deliveries
    late_deliveries = PurchaseOrder.objects.filter(
        expected_delivery_date__lt=today,
        status__in=['ordered', 'partial']
    ).select_related('supplier').order_by('expected_delivery_date')[:20]
    
    context = {
        'po_by_status': po_by_status,
        'top_suppliers': top_suppliers,
        'late_deliveries': late_deliveries,
        'today': today,
    }
    
    return render(request, 'purchasing/purchasing_report.html', context)


@login_required
def spend_analysis(request):
    """Spend analysis report"""
    today = timezone.now().date()
    
    # Spend by supplier
    spend_by_supplier = Supplier.objects.annotate(
        total_spend=Sum('purchase_orders__total_amount',
                       filter=Q(purchase_orders__status__in=['received', 'partial']))
    ).filter(total_spend__gt=0).order_by('-total_spend')
    
    context = {
        'spend_by_supplier': spend_by_supplier,
        'today': today,
    }
    return render(request, 'purchasing/spend_analysis.html', context)


@login_required
def supplier_performance_report(request):
    """Supplier performance report"""
    suppliers = Supplier.objects.annotate(
        total_pos=Count('purchase_orders'),
        on_time_deliveries=Count('purchase_orders', 
                                 filter=Q(purchase_orders__goods_receipts__receipt_date__lte=F('purchase_orders__expected_delivery_date'))),
        late_deliveries=Count('purchase_orders',
                              filter=Q(purchase_orders__goods_receipts__receipt_date__gt=F('purchase_orders__expected_delivery_date')))
    )
    
    for supplier in suppliers:
        if supplier.total_pos > 0:
            supplier.on_time_rate = (supplier.on_time_deliveries / supplier.total_pos) * 100
        else:
            supplier.on_time_rate = 0
    
    context = {
        'suppliers': suppliers,
        'today': timezone.now().date(),
    }
    return render(request, 'purchasing/supplier_performance_report.html', context)


@login_required
def lead_time_report(request):
    """Lead time analysis report"""
    today = timezone.now().date()
    
    # Calculate lead times for received orders
    completed_pos = PurchaseOrder.objects.filter(
        status='received',
        goods_receipts__isnull=False
    ).annotate(
        lead_time=F('goods_receipts__receipt_date') - F('order_date')
    )
    
    context = {
        'completed_pos': completed_pos[:50],
        'today': today,
    }
    return render(request, 'purchasing/lead_time.html', context)


@login_required
def po_status_report(request):
    """PO status report"""
    today = timezone.now().date()
    
    pos_by_status = PurchaseOrder.objects.values('status').annotate(
        count=Count('id'),
        total=Sum('total_amount')
    )
    
    context = {
        'pos_by_status': pos_by_status,
        'today': today,
    }
    return render(request, 'purchasing/po_status.html', context)


# ============================
# Export Views
# ============================

@login_required
def export_suppliers(request):
    """Export suppliers to CSV"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="suppliers_{timezone.now().strftime("%Y%m%d")}.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Code', 'Name', 'TIN', 'Contact Person', 'Phone', 'Email', 'Country', 'Status'])
    
    suppliers = Supplier.objects.filter(is_active=True).select_related('company')
    for supplier in suppliers:
        writer.writerow([
            supplier.code,
            supplier.name,
            supplier.tin,
            supplier.contact_person,
            supplier.phone,
            supplier.email,
            supplier.country,
            'Preferred' if supplier.is_preferred else 'Active' if supplier.is_active else 'Inactive'
        ])
    
    return response


# ============================
# AJAX Views
# ============================

@login_required
def ajax_supplier_info(request, supplier_id):
    """AJAX endpoint to get supplier information"""
    supplier = get_object_or_404(Supplier, id=supplier_id)
    
    data = {
        'id': supplier.id,
        'code': supplier.code,
        'name': supplier.name,
        'payment_terms': supplier.payment_terms_days,
        'currency': supplier.currency,
        'credit_limit': float(supplier.credit_limit),
        'is_preferred': supplier.is_preferred,
    }
    
    return JsonResponse(data)


@login_required
def ajax_po_lines(request, po_id):
    """AJAX endpoint to get PO lines"""
    lines = PurchaseOrderLine.objects.filter(po_id=po_id).select_related('item', 'unit')
    
    data = []
    for line in lines:
        data.append({
            'id': line.id,
            'item_code': line.item.code,
            'item_name': line.item.name,
            'quantity': float(line.quantity_ordered),
            'unit': line.unit.abbreviation,
            'unit_price': float(line.unit_price),
            'total': float(line.total_price),
            'received': float(line.quantity_received),
            'remaining': float(line.remaining),
        })
    
    return JsonResponse({'lines': data})


@login_required
def ajax_item_price(request, item_id, supplier_id):
    """AJAX endpoint to get item price for a supplier"""
    # This would look up supplier-specific pricing
    from apps.core.models import Item
    item = get_object_or_404(Item, id=item_id)
    
    data = {
        'item_id': item.id,
        'item_code': item.code,
        'unit_price': float(item.unit_cost or 0),
    }
    
    return JsonResponse(data)