from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Count, F
from django.utils import timezone
from django.contrib import messages
from django.http import JsonResponse
from django.core.exceptions import ValidationError
from django.urls import reverse
import json
from decimal import Decimal
from django.http import FileResponse
from .utils import generate_po_pdf
from apps.company.models import Company

from .models import (
    PurchaseOrder, PurchaseOrderLine, Supplier, 
    PurchaseRequisition, GoodsReceipt, GoodsReceiptLine
)
from apps.inventory.models import Item, Warehouse
from apps.core.models import Unit


# ============================
# Local Helpers
# ============================
def _generate_auto_item_code():
    """Generate a unique auto item code for PO quick-create."""
    base = timezone.now().strftime("AUTO-%Y%m%d")
    seq = 1
    code = f"{base}-{seq:03d}"
    while Item.objects.filter(code=code).exists():
        seq += 1
        code = f"{base}-{seq:03d}"
    return code


def _resolve_po_item(item_token, unit_id=None):
    """
    Resolve item token posted from PO form.
    Supports:
    - existing item id, e.g. "12"
    - new tag value, e.g. "new:Item Name"
    """
    token = (item_token or '').strip()
    if not token:
        raise ValueError("Empty item token")

    if token.isdigit():
        return Item.objects.get(id=int(token))

    if token.startswith('new:'):
        item_name = token[4:].strip()
        if not item_name:
            raise ValueError("Invalid item name")

        unit = None
        if unit_id:
            try:
                unit = Unit.objects.get(id=int(unit_id))
            except (Unit.DoesNotExist, ValueError, TypeError):
                unit = None
        if not unit:
            unit = Unit.objects.order_by('id').first()
        if not unit:
            raise ValueError("No Unit configured in system")

        return Item.objects.create(
            code=_generate_auto_item_code(),
            name=item_name,
            category='raw',
            unit=unit,
            is_active=True,
            is_purchased=True,
            is_sold=False,
            unit_cost=Decimal('0.00'),
            current_stock=Decimal('0.00'),
            minimum_stock=Decimal('0.00'),
            reorder_point=Decimal('0.00'),
        )

    raise ValueError("Unsupported item token")


def _calculate_withholding_tax(withholding_base, currency):
    """
    Ethiopian WHT rule for this system:
    - 3% only when currency is ETB
    - and taxable base is above 20,000 ETB
    """
    base = withholding_base or Decimal('0.00')
    if currency == 'ETB' and base > Decimal('20000'):
        return (base * Decimal('0.03')).quantize(Decimal('0.01'))
    return Decimal('0.00')


# ============================
# Dashboard Views
# ============================

@login_required
def dashboard(request):
    """
    Purchasing dashboard view
    """
    context = {
        'current_period': timezone.now().strftime('%B %Y'),
        'total_po_count': PurchaseOrder.objects.count(),
        'pending_po_count': PurchaseOrder.objects.filter(status='pending').count(),
        'total_suppliers': Supplier.objects.filter(is_active=True).count(),
        'recent_pos': PurchaseOrder.objects.order_by('-order_date')[:5],
    }
    return render(request, 'purchasing/dashboard.html', context)


@login_required
def supplier_dashboard(request):
    """
    Supplier dashboard view
    """
    suppliers = Supplier.objects.filter(is_active=True)
    context = {
        'suppliers': suppliers,
        'total_suppliers': suppliers.count(),
    }
    return render(request, 'purchasing/supplier_dashboard.html', context)


# ============================
# Purchase Order Views
# ============================

@login_required
def po_list(request):
    """
    List all purchase orders with filtering
    """
    # Base queryset
    queryset = PurchaseOrder.objects.select_related(
        'supplier', 'created_by'
    ).prefetch_related('lines').all()

    # Scope by selected company from session
    company_name = request.session.get('current_company_name')
    if company_name:
        queryset = queryset.filter(company=company_name)
    
    # Apply filters
    status = request.GET.get('status')
    if status:
        queryset = queryset.filter(status=status)
    
    supplier_id = request.GET.get('supplier')
    if supplier_id:
        queryset = queryset.filter(supplier_id=supplier_id)
    
    search = request.GET.get('search')
    if search:
        queryset = queryset.filter(
            Q(po_number__icontains=search) |
            Q(supplier__name__icontains=search) |
            Q(supplier__code__icontains=search)
        )
    
    date_range = request.GET.get('date_range')
    if date_range and ' to ' in date_range:
        start_date, end_date = date_range.split(' to ')
        queryset = queryset.filter(order_date__range=[start_date, end_date])
    
    # Order by latest first
    queryset = queryset.order_by('-order_date', '-id')
    
    # Pagination
    paginator = Paginator(queryset, 20)  # Show 20 per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Statistics
    summary_qs = PurchaseOrder.objects.all()
    if company_name:
        summary_qs = summary_qs.filter(company=company_name)

    total_po_count = summary_qs.count()
    total_po_value = summary_qs.aggregate(
        total=Sum('total_amount')
    )['total'] or 0
    pending_count = summary_qs.filter(
        status__in=['draft', 'pending', 'approved']
    ).count()
    
    # Get all active suppliers for filter dropdown
    suppliers = Supplier.objects.filter(is_active=True)
    if company_name:
        suppliers = suppliers.filter(company=company_name)
    suppliers = suppliers.order_by('name')
    
    context = {
        'purchase_orders': page_obj,
        'page_obj': page_obj,
        'is_paginated': page_obj.has_other_pages(),
        'suppliers': suppliers,
        'total_po_count': total_po_count,
        'total_po_value': f"{total_po_value:,.0f}",
        'pending_count': pending_count,
        'this_month_count': summary_qs.filter(
            order_date__month=timezone.now().month,
            order_date__year=timezone.now().year
        ).count(),
    }
    
    return render(request, 'purchasing/po_list.html', context)


@login_required
def po_detail(request, po_id):
    """
    View purchase order details
    """
    po_qs = PurchaseOrder.objects.select_related('supplier', 'created_by')
    company_name = request.session.get('current_company_name')
    if company_name:
        po_qs = po_qs.filter(company=company_name)
    po = get_object_or_404(po_qs, id=po_id)
    
    # Get lines, then attach related objects using the temporary item_id/unit_id fields
    lines = list(PurchaseOrderLine.objects.filter(po=po))
    # preload items and units for efficiency
    item_ids = [l.item_id for l in lines if l.item_id]
    unit_ids = [l.unit_id for l in lines if l.unit_id]
    items_map = {i.id: i for i in Item.objects.filter(id__in=item_ids)} if item_ids else {}
    units_map = {u.id: u for u in Unit.objects.filter(id__in=unit_ids)} if unit_ids else {}
    for l in lines:
        l.item_obj = items_map.get(l.item_id)
        l.unit_obj = units_map.get(l.unit_id)
    
    # Calculate totals
    subtotal = Decimal('0')
    tax_total = Decimal('0')
    
    for line in lines:
        line_total = line.quantity_ordered * line.unit_price
        line_tax = line_total * (line.tax_rate / 100)
        subtotal += line_total
        tax_total += line_tax
    
    withholding_tax = _calculate_withholding_tax(subtotal, po.currency)
    grand_total = subtotal + tax_total + po.shipping_cost - po.discount
    net_grand_total = grand_total - withholding_tax
    
    # Get related receipts if any
    receipts = GoodsReceipt.objects.filter(po=po).select_related('received_by', 'created_by')
    
    context = {
        'po': po,
        'lines': lines,
        'subtotal': subtotal,
        'tax_total': tax_total,
        'withholding_tax': withholding_tax,
        'grand_total': grand_total,
        'net_grand_total': net_grand_total,
        'receipts': receipts,
        'can_edit': po.status in ['draft', 'pending'],
        'can_cancel': po.status not in ['received', 'cancelled', 'closed'],
        'can_receive': po.status in ['approved', 'sent'],
        'can_send': po.status in ['approved'],
    }
    return render(request, 'purchasing/po_detail.html', context)


@login_required
def po_create(request):
    """
    Create a new purchase order
    """
    if request.method == 'POST':
        # Process form submission
        try:
            # Get form data
            supplier_id = request.POST.get('supplier')
            po_number = request.POST.get('po_number')
            order_date = request.POST.get('order_date')
            expected_date = request.POST.get('expected_delivery_date') or request.POST.get('expected_date')
            shipping_method = request.POST.get('shipping_method')
            shipping_address = request.POST.get('shipping_address')
            billing_address = request.POST.get('billing_address')
            notes = request.POST.get('notes')
            terms = request.POST.get('terms')
            shipping_cost = Decimal(request.POST.get('shipping_cost', 0))
            discount = Decimal(request.POST.get('discount', 0))
            currency = request.POST.get('currency', 'USD')
            payment_terms = request.POST.get('payment_terms')
            company_name = request.session.get('current_company_name')
            if not company_name:
                messages.error(request, "Please select a company first.")
                return redirect('core:home')
            
            # Validate required fields
            if not supplier_id or not po_number or not order_date:
                messages.error(request, "Please fill in all required fields.")
                return redirect('purchasing:po_create')
            
            # Get supplier
            supplier = get_object_or_404(Supplier, id=supplier_id)
            
            # Create purchase order
            po = PurchaseOrder.objects.create(
                company=company_name,
                po_number=po_number,
                supplier=supplier,
                order_date=order_date,
                expected_delivery_date=expected_date if expected_date else None,
                shipping_method=shipping_method,
                shipping_address=shipping_address,
                billing_address=billing_address,
                notes=notes,
                terms=terms,
                shipping_cost=shipping_cost,
                discount=discount,
                currency=currency,
                payment_terms=payment_terms,
                status='draft',
                created_by=request.user
            )
            
            # Process order lines
            line_items = request.POST.getlist('item')
            quantities = request.POST.getlist('quantity')
            units = request.POST.getlist('unit')
            unit_prices = request.POST.getlist('unit_price')
            tax_rates = request.POST.getlist('tax_rate')
            
            total_amount = Decimal('0')
            withholding_base = Decimal('0')
            
            for i in range(len(line_items)):
                if line_items[i] and quantities[i] and quantities[i].strip():
                    item_id = line_items[i]
                    if item_id and item_id.strip():
                        try:
                            unit_id_value = units[i] if i < len(units) else None
                            item = _resolve_po_item(item_id, unit_id=unit_id_value)
                            quantity = Decimal(quantities[i]) if quantities[i] else Decimal('0')
                            unit_price = Decimal(unit_prices[i]) if i < len(unit_prices) and unit_prices[i] else Decimal('0')
                            tax_rate = Decimal(tax_rates[i]) if i < len(tax_rates) and tax_rates[i] else Decimal('0')
                            
                            unit = None
                            if units[i] and units[i].strip():
                                try:
                                    unit = Unit.objects.get(id=int(units[i]))
                                except (Unit.DoesNotExist, ValueError):
                                    unit = None
                            
                            if quantity > 0:
                                line = PurchaseOrderLine.objects.create(
                                    po=po,
                                    item=f"{item.code} - {item.name}",
                                    item_id=item.id,
                                    unit=str(unit.id) if unit else '',
                                    unit_id=unit.id if unit else None,
                                    quantity_ordered=quantity,
                                    unit_price=unit_price,
                                    tax_rate=tax_rate
                                )
                                
                                line_total = line.quantity_ordered * line.unit_price
                                tax_amount = line_total * (line.tax_rate / 100)
                                total_amount += line_total + tax_amount
                                withholding_base += line_total
                        except (Item.DoesNotExist, ValueError) as e:
                            print(f"Error processing line {i}: {e}")
                            continue
            
            # Update PO total
            withholding_tax = _calculate_withholding_tax(withholding_base, currency)
            po.total_amount = total_amount + shipping_cost - discount - withholding_tax
            po.save()
            
            messages.success(request, f"Purchase Order {po.po_number} created successfully.")
            
            # Handle action buttons
            action = request.POST.get('action')
            if action == 'save_and_new':
                return redirect('purchasing:po_create')
            elif action == 'save_and_send':
                # Redirect to send page or send email
                messages.info(request, "PO saved. You can now send it to the supplier.")
                return redirect('purchasing:po_detail', po_id=po.id)
            else:
                return redirect('purchasing:po_detail', po_id=po.id)
                
        except Exception as e:
            messages.error(request, f"Error creating purchase order: {str(e)}")
            return redirect('purchasing:po_create')
    
    # GET request - show form
    company_name = request.session.get('current_company_name')
    suppliers = Supplier.objects.filter(is_active=True)
    if company_name:
        suppliers = suppliers.filter(company=company_name)
    suppliers = suppliers.order_by('name')
    
    # Load purchasable inventory items for dropdown
    items = Item.objects.filter(
        is_active=True,
        is_purchased=True
    ).select_related('unit').order_by('code')
    
    units = Unit.objects.all().order_by('name')
    
    # Check if coming from requisition
    requisition_id = request.GET.get('requisition')
    initial_data = {}
    if requisition_id:
        try:
            requisition = PurchaseRequisition.objects.get(id=requisition_id)
            initial_data = {
                'requisition': requisition,
                'expected_date': requisition.required_date,
            }
        except PurchaseRequisition.DoesNotExist:
            pass
    
    context = {
        'suppliers': suppliers,
        'items': items,
        'units': units,
        'requisition_id': requisition_id,
        'initial_data': initial_data,
        'now': timezone.now(),
    }
    return render(request, 'purchasing/po_form.html', context)


@login_required
def po_edit(request, po_id):
    """
    Edit a purchase order
    """
    po_qs = PurchaseOrder.objects.all()
    company_name = request.session.get('current_company_name')
    if company_name:
        po_qs = po_qs.filter(company=company_name)
    po = get_object_or_404(po_qs, id=po_id)
    
    # Check if PO can be edited
    if po.status not in ['draft', 'pending']:
        messages.error(request, f"Cannot edit PO with status '{po.status}'.")
        return redirect('purchasing:po_detail', po_id=po.id)
    
    if request.method == 'POST':
        try:
            # Update PO fields
            po.supplier_id = request.POST.get('supplier')
            po.po_number = request.POST.get('po_number')
            po.order_date = request.POST.get('order_date')
            po.expected_delivery_date = request.POST.get('expected_delivery_date') or request.POST.get('expected_date')
            po.shipping_method = request.POST.get('shipping_method')
            po.shipping_address = request.POST.get('shipping_address')
            po.billing_address = request.POST.get('billing_address')
            po.notes = request.POST.get('notes')
            po.terms = request.POST.get('terms')
            po.shipping_cost = Decimal(request.POST.get('shipping_cost', 0))
            po.discount = Decimal(request.POST.get('discount', 0))
            po.currency = request.POST.get('currency', 'USD')
            po.payment_terms = request.POST.get('payment_terms')
            po.save()
            
            # Handle line items - delete existing and recreate
            po.lines.all().delete()
            
            line_items = request.POST.getlist('item')
            quantities = request.POST.getlist('quantity')
            units = request.POST.getlist('unit')
            unit_prices = request.POST.getlist('unit_price')
            tax_rates = request.POST.getlist('tax_rate')
            
            total_amount = Decimal('0')
            withholding_base = Decimal('0')
            
            for i in range(len(line_items)):
                if line_items[i] and quantities[i] and quantities[i].strip():
                    item_id = line_items[i]
                    if item_id and item_id.strip():
                        try:
                            unit_id_value = units[i] if i < len(units) else None
                            item_obj = _resolve_po_item(item_id, unit_id=unit_id_value)
                            quantity = Decimal(quantities[i]) if quantities[i] else Decimal('0')
                            unit_price = Decimal(unit_prices[i]) if i < len(unit_prices) and unit_prices[i] else Decimal('0')
                            tax_rate = Decimal(tax_rates[i]) if i < len(tax_rates) and tax_rates[i] else Decimal('0')
                            
                            if quantity > 0:
                                # build a readable string for the item field
                                item_str = f"{item_obj.code} - {item_obj.name}"

                                line = PurchaseOrderLine.objects.create(
                                    po=po,
                                    item=item_str,
                                    item_id=item_obj.id,
                                    unit=str(units[i]) if i < len(units) and units[i] else '',
                                    unit_id=int(units[i]) if i < len(units) and units[i] else None,
                                    quantity_ordered=quantity,
                                    unit_price=unit_price,
                                    tax_rate=tax_rate
                                )

                                line_total = line.quantity_ordered * line.unit_price
                                tax_amount = line_total * (line.tax_rate / 100)
                                total_amount += line_total + tax_amount
                                withholding_base += line_total
                        except (ValueError, DecimalException) as e:
                            print(f"Error processing line {i}: {e}")
                            continue
            
            withholding_tax = _calculate_withholding_tax(withholding_base, po.currency)
            po.total_amount = total_amount + po.shipping_cost - po.discount - withholding_tax
            po.save()
            
            messages.success(request, f"Purchase Order {po.po_number} updated successfully.")
            return redirect('purchasing:po_detail', po_id=po.id)
            
        except Exception as e:
            messages.error(request, f"Error updating purchase order: {str(e)}")
            return redirect('purchasing:po_edit', po_id=po.id)
    
    # GET request - show form with existing data
    suppliers = Supplier.objects.filter(is_active=True)
    if company_name:
        suppliers = suppliers.filter(company=company_name)
    suppliers = suppliers.order_by('name')
    
    # Load items for dropdowns
    items = Item.objects.filter(is_active=True).select_related('unit').order_by('code')
    
    units = Unit.objects.all().order_by('name')
    
    # prepare existing order lines with related objects as above
    order_lines = list(po.lines.all())
    item_ids = [l.item_id for l in order_lines if l.item_id]
    unit_ids = [l.unit_id for l in order_lines if l.unit_id]
    items_map = {i.id: i for i in Item.objects.filter(id__in=item_ids)} if item_ids else {}
    units_map = {u.id: u for u in Unit.objects.filter(id__in=unit_ids)} if unit_ids else {}
    for l in order_lines:
        l.item_obj = items_map.get(l.item_id)
        l.unit_obj = units_map.get(l.unit_id)
    
    context = {
        'po': po,
        'suppliers': suppliers,
        'items': items,
        'units': units,
        'order_lines': order_lines,
    }
    return render(request, 'purchasing/po_form.html', context)


@login_required
def po_delete(request, po_id):
    """
    Delete a purchase order
    """
    po = get_object_or_404(PurchaseOrder, id=po_id)
    
    if request.method == 'POST':
        po_number = po.po_number
        po.delete()
        messages.success(request, f"Purchase Order {po_number} deleted successfully.")
        return redirect('purchasing:po_list')
    
    context = {'po': po}
    return render(request, 'purchasing/po_confirm_delete.html', context)


@login_required
def po_send(request, po_id):
    """
    Send purchase order to supplier (change status to 'sent')
    """
    po = get_object_or_404(PurchaseOrder, id=po_id)
    
    if request.method == 'POST':
        po.status = 'ordered'  # Changed from 'sent' to match STATUS_CHOICES
        po.save()
        messages.success(request, f"PO {po.po_number} sent to supplier.")
        
        # Here you would add email sending logic
        # send_po_email(po)
        
        return redirect('purchasing:po_detail', po_id=po.id)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@login_required
def receive_po(request, po_id):
    """
    Receive purchase order (create goods receipt)
    """
    po = get_object_or_404(PurchaseOrder, id=po_id)
    
    if request.method == 'POST':
        try:
            received_date = request.POST.get('received_date')
            receipt_number = request.POST.get('receipt_number')
            notes = request.POST.get('notes')
            
            # Create goods receipt
            receipt = GoodsReceipt.objects.create(
                receipt_number=receipt_number,
                po=po,
                receipt_date=received_date,
                notes=notes,
                received_by=request.user,
                created_by=request.user
            )
            
            # Update inventory for each line
            for line in po.lines.all():
                # Create receipt line
                GoodsReceiptLine.objects.create(
                    receipt=receipt,
                    po_line=line,
                    quantity_received=line.quantity_ordered
                )
                
                # Update stock - since item is CharField, you'll need to handle this differently
                # line.item.current_stock += line.quantity_ordered
                # line.item.save()
            
            # Update PO status
            po.status = 'received'
            po.save()
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'receipt_id': receipt.id})
            
            messages.success(request, f"PO {po.po_number} received successfully.")
            return redirect('purchasing:po_detail', po_id=po.id)
            
        except Exception as e:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': str(e)})
            messages.error(request, f"Error receiving PO: {str(e)}")
            return redirect('purchasing:po_detail', po_id=po.id)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@login_required
def po_close(request, po_id):
    """
    Close a purchase order
    """
    po = get_object_or_404(PurchaseOrder, id=po_id)
    
    if request.method == 'POST':
        po.status = 'closed'
        po.save()
        messages.success(request, f"PO {po.po_number} closed.")
        return redirect('purchasing:po_detail', po_id=po.id)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@login_required
def po_cancel(request, po_id):
    """
    Cancel a purchase order
    """
    po = get_object_or_404(PurchaseOrder, id=po_id)
    
    if request.method == 'POST':
        reason = request.POST.get('reason')
        notes = request.POST.get('notes')
        
        po.status = 'cancelled'
        po.notes = f"Cancelled: {reason}\n{notes}" if notes else f"Cancelled: {reason}"
        po.save()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True})
        
        messages.success(request, f"PO {po.po_number} cancelled.")
        return redirect('purchasing:po_detail', po_id=po.id)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@login_required
def po_print(request, po_id):
    """
    Print purchase order (return PDF or print-friendly HTML)
    """
    po_qs = PurchaseOrder.objects.select_related('supplier', 'created_by')
    company_name = request.session.get('current_company_name')
    if company_name:
        po_qs = po_qs.filter(company=company_name)
    po = get_object_or_404(po_qs, id=po_id)
    
    lines = list(PurchaseOrderLine.objects.filter(po=po))
    unit_ids = [l.unit_id for l in lines if l.unit_id]
    units_map = {u.id: u for u in Unit.objects.filter(id__in=unit_ids)} if unit_ids else {}
    for l in lines:
        l.unit_obj = units_map.get(l.unit_id)
    
    # Calculate totals
    subtotal = Decimal('0')
    tax_total = Decimal('0')
    
    for line in lines:
        line_total = line.quantity_ordered * line.unit_price
        line_tax = line_total * (line.tax_rate / 100)
        subtotal += line_total
        tax_total += line_tax
    
    withholding_tax = _calculate_withholding_tax(subtotal, po.currency)
    grand_total = subtotal + tax_total + po.shipping_cost - po.discount
    net_grand_total = grand_total - withholding_tax
    
    company_obj = None
    company_id = request.session.get('current_company_id')
    if company_id:
        company_obj = Company.objects.filter(id=company_id, is_active=True).first()

    context = {
        'po': po,
        'lines': lines,
        'subtotal': subtotal,
        'tax_total': tax_total,
        'withholding_tax': withholding_tax,
        'grand_total': grand_total,
        'net_grand_total': net_grand_total,
        'company_name': company_obj.name if company_obj else (request.session.get('current_company_name') or po.company or 'Company'),
        'company_address': company_obj.address if company_obj else '',
        'company_phone': company_obj.phone if company_obj else '',
        'company_email': company_obj.email if company_obj else '',
        'company_tax_id': company_obj.tin_number if company_obj else '',
    }
    return render(request, 'purchasing/po_print.html', context)


def download_po_pdf(request, po_id):
    po = get_object_or_404(PurchaseOrder, id=po_id)
    pdf_buffer = generate_po_pdf(po)
    return FileResponse(pdf_buffer, as_attachment=True, filename=f'{po.po_number}.pdf')

@login_required
def export_pos(request):
    """
    Export purchase orders to CSV/Excel
    """
    import csv
    from django.http import HttpResponse
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="purchase_orders.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['PO Number', 'Supplier', 'Order Date', 'Total Amount', 'Status', 'Created By', 'Created Date'])
    
    pos = PurchaseOrder.objects.all().select_related('supplier', 'created_by')
    for po in pos:
        writer.writerow([
            po.po_number,
            po.supplier.name if po.supplier else '',
            po.order_date,
            f"{po.total_amount:.2f}",
            po.status,
            po.created_by.username if po.created_by else '',
            po.created_at,
        ])
    
    return response


# ============================
# Supplier Views
# ============================

@login_required
def supplier_list(request):
    """
    List all suppliers with filtering
    """
    # Base queryset
    suppliers = Supplier.objects.all().order_by('name')
    
    # Apply filters
    search = request.GET.get('search')
    if search:
        suppliers = suppliers.filter(
            Q(name__icontains=search) |
            Q(code__icontains=search) |
            Q(email__icontains=search) |
            Q(phone__icontains=search) |
            Q(contact_person__icontains=search) |
            Q(tax_id__icontains=search)
        )
    
    is_active = request.GET.get('is_active')
    if is_active == 'true':
        suppliers = suppliers.filter(is_active=True)
    elif is_active == 'false':
        suppliers = suppliers.filter(is_active=False)
    
    # Pagination
    paginator = Paginator(suppliers, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Statistics
    total_count = Supplier.objects.count()
    active_count = Supplier.objects.filter(is_active=True).count()
    inactive_count = total_count - active_count
    
    context = {
        'suppliers': page_obj,
        'page_obj': page_obj,
        'is_paginated': page_obj.has_other_pages(),
        'total_count': total_count,
        'active_count': active_count,
        'inactive_count': inactive_count,
    }
    
    return render(request, 'purchasing/supplier_list.html', context)


@login_required
def supplier_detail(request, supplier_id):
    """
    View supplier details
    """
    supplier = get_object_or_404(Supplier, id=supplier_id)
    recent_pos = PurchaseOrder.objects.filter(
        supplier=supplier
    ).order_by('-order_date')[:10]
    
    context = {
        'supplier': supplier,
        'recent_pos': recent_pos,
        'po_count': PurchaseOrder.objects.filter(supplier=supplier).count(),
        'total_spend': PurchaseOrder.objects.filter(
            supplier=supplier,
            status='received'
        ).aggregate(total=Sum('total_amount'))['total'] or 0,
    }
    return render(request, 'purchasing/supplier_detail.html', context)


@login_required
def supplier_create(request):
    """
    Create a new supplier
    """
    if request.method == 'POST':
        try:
            supplier = Supplier.objects.create(
                code=request.POST.get('code'),
                name=request.POST.get('name'),
                contact_person=request.POST.get('contact_person'),
                email=request.POST.get('email'),
                phone=request.POST.get('phone'),
                address=request.POST.get('address'),
                payment_terms_days=int(request.POST.get('payment_terms_days', 30)),
                tax_id=request.POST.get('tax_id'),
                is_active=request.POST.get('is_active') == 'on'
            )
            messages.success(request, f"Supplier {supplier.name} created successfully.")
            return redirect('purchasing:supplier_detail', supplier_id=supplier.id)
        except Exception as e:
            messages.error(request, f"Error creating supplier: {str(e)}")
            return redirect('purchasing:supplier_create')
    
    return render(request, 'purchasing/supplier_form.html')


@login_required
def supplier_edit(request, supplier_id):
    """
    Edit an existing supplier
    """
    supplier = get_object_or_404(Supplier, id=supplier_id)
    
    if request.method == 'POST':
        try:
            # Update supplier fields
            supplier.code = request.POST.get('code')
            supplier.name = request.POST.get('name')
            supplier.contact_person = request.POST.get('contact_person')
            supplier.email = request.POST.get('email')
            supplier.phone = request.POST.get('phone')
            supplier.address = request.POST.get('address')
            supplier.payment_terms_days = int(request.POST.get('payment_terms_days', 30))
            supplier.tax_id = request.POST.get('tax_id')
            supplier.is_active = request.POST.get('is_active') == 'on'
            supplier.save()
            
            messages.success(request, f'Supplier {supplier.name} updated successfully.')
            return redirect('purchasing:supplier_detail', supplier_id=supplier.id)
            
        except Exception as e:
            messages.error(request, f'Error updating supplier: {str(e)}')
            return redirect('purchasing:supplier_edit', supplier_id=supplier.id)
    
    context = {
        'supplier': supplier,
    }
    return render(request, 'purchasing/supplier_form.html', context)


@login_required
def supplier_delete(request, supplier_id):
    """
    Delete a supplier
    """
    supplier = get_object_or_404(Supplier, id=supplier_id)
    
    if request.method == 'POST':
        try:
            supplier_name = supplier.name
            supplier.delete()
            messages.success(request, f'Supplier {supplier_name} deleted successfully.')
            return redirect('purchasing:supplier_list')
        except Exception as e:
            messages.error(request, f'Error deleting supplier: {str(e)}')
            return redirect('purchasing:supplier_detail', supplier_id=supplier_id)
    
    return redirect('purchasing:supplier_list')


@login_required
def supplier_performance(request, supplier_id):
    """
    View supplier performance metrics
    """
    supplier = get_object_or_404(Supplier, id=supplier_id)
    
    # Get purchase orders for this supplier
    purchase_orders = PurchaseOrder.objects.filter(supplier=supplier).order_by('-order_date')

    # Calculate core metrics
    total_orders = purchase_orders.count()
    total_spent = purchase_orders.filter(status='received').aggregate(
        total=Sum('total_amount')
    )['total'] or Decimal('0.00')

    received_orders = purchase_orders.filter(
        status='received',
        received_date__isnull=False
    )
    delivered_orders_count = received_orders.count()

    on_time_orders = received_orders.filter(
        expected_delivery_date__isnull=False,
        received_date__lte=F('expected_delivery_date')
    ).count()
    late_orders = max(delivered_orders_count - on_time_orders, 0)

    on_time_rate = (on_time_orders / delivered_orders_count * 100) if delivered_orders_count else 0

    lead_time_values = []
    for po in received_orders.exclude(order_date__isnull=True):
        if po.received_date and po.order_date:
            lead_time_values.append((po.received_date - po.order_date).days)
    avg_lead_time = round(sum(lead_time_values) / len(lead_time_values), 1) if lead_time_values else 0

    # Build recent order performance rows
    recent_orders = []
    for po in purchase_orders[:20]:
        lead_days = None
        if po.received_date and po.order_date:
            lead_days = (po.received_date - po.order_date).days

        delay_days = None
        is_on_time = None
        if po.received_date and po.expected_delivery_date:
            delay_days = (po.received_date - po.expected_delivery_date).days
            is_on_time = delay_days <= 0

        recent_orders.append({
            'po': po,
            'lead_days': lead_days,
            'delay_days': delay_days,
            'is_on_time': is_on_time,
        })

    # Weighted score (60% delivery + 40% quality)
    quality_rating = float(supplier.quality_rating or 0)  # expected out of 5
    delivery_score = on_time_rate
    quality_score = (quality_rating / 5.0) * 100 if quality_rating > 0 else 0
    score = round((delivery_score * 0.6) + (quality_score * 0.4), 1)

    if score >= 90:
        score_grade = 'A'
    elif score >= 80:
        score_grade = 'B'
    elif score >= 70:
        score_grade = 'C'
    else:
        score_grade = 'D'

    context = {
        'supplier': supplier,
        'recent_orders': recent_orders,
        'total_orders': total_orders,
        'delivered_orders_count': delivered_orders_count,
        'on_time_orders': on_time_orders,
        'late_orders': late_orders,
        'total_spent': total_spent,
        'on_time_rate': round(on_time_rate, 1),
        'avg_lead_time': avg_lead_time,
        'score': score,
        'score_grade': score_grade,
        'current_date': timezone.now(),
    }
    
    return render(request, 'purchasing/supplier_performance.html', context)


@login_required
def export_suppliers(request):
    """
    Export suppliers to CSV/Excel
    """
    import csv
    from django.http import HttpResponse

    suppliers = Supplier.objects.all().order_by('name')

    # Apply same filters as supplier_list, but never paginate
    search = (request.GET.get('search') or '').strip()
    if search:
        suppliers = suppliers.filter(
            Q(name__icontains=search) |
            Q(code__icontains=search) |
            Q(email__icontains=search) |
            Q(phone__icontains=search) |
            Q(contact_person__icontains=search)
        )

    is_active = request.GET.get('is_active')
    if is_active == 'true':
        suppliers = suppliers.filter(is_active=True)
    elif is_active == 'false':
        suppliers = suppliers.filter(is_active=False)

    vat_registered = request.GET.get('vat_registered')
    if vat_registered == 'true':
        suppliers = suppliers.filter(
            Q(tax_id__isnull=False) & ~Q(tax_id='') |
            Q(tin__isnull=False) & ~Q(tin='')
        )
    elif vat_registered == 'false':
        suppliers = suppliers.filter(
            (Q(tax_id__isnull=True) | Q(tax_id='')) &
            (Q(tin__isnull=True) | Q(tin=''))
        )

    export_format = (request.GET.get('format') or 'excel').lower()

    if export_format == 'excel':
        try:
            from openpyxl import Workbook
        except ImportError:
            export_format = 'csv'
        else:
            wb = Workbook()
            ws = wb.active
            ws.title = "Suppliers"

            ws.append([
                'Code', 'Name', 'Contact Person', 'Email', 'Phone',
                'Address', 'Payment Terms', 'Tax ID', 'VAT Registered', 'Active'
            ])

            for supplier in suppliers:
                ws.append([
                    supplier.code,
                    supplier.name,
                    supplier.contact_person,
                    supplier.email,
                    supplier.phone,
                    supplier.address,
                    supplier.payment_terms_days,
                    supplier.tax_id,
                    'Yes' if (supplier.tax_id or supplier.tin) else 'No',
                    'Yes' if supplier.is_active else 'No',
                ])

            response = HttpResponse(
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            response['Content-Disposition'] = 'attachment; filename="suppliers.xlsx"'
            wb.save(response)
            return response

    if export_format == 'pdf':
        try:
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.pdfgen import canvas
        except ImportError:
            return HttpResponse(
                "PDF export is unavailable because reportlab is not installed.",
                status=500,
                content_type='text/plain'
            )

        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="suppliers.pdf"'

        page_size = landscape(A4)
        pdf = canvas.Canvas(response, pagesize=page_size)
        width, height = page_size
        y = height - 35

        pdf.setFont("Helvetica-Bold", 14)
        pdf.drawString(30, y, "Suppliers List")
        y -= 18
        pdf.setFont("Helvetica", 9)
        pdf.drawString(30, y, f"Generated: {timezone.now().strftime('%d %b %Y %H:%M')}")
        y -= 16

        headers = ["Code", "Name", "Contact", "Email", "Phone", "Tax ID", "Active"]
        col_x = [30, 95, 255, 380, 530, 620, 710]
        pdf.setFont("Helvetica-Bold", 8)
        for i, h in enumerate(headers):
            pdf.drawString(col_x[i], y, h)
        y -= 10
        pdf.line(25, y + 6, width - 25, y + 6)
        pdf.setFont("Helvetica", 7)

        for supplier in suppliers:
            if y < 40:
                pdf.showPage()
                y = height - 35
                pdf.setFont("Helvetica-Bold", 8)
                for i, h in enumerate(headers):
                    pdf.drawString(col_x[i], y, h)
                y -= 10
                pdf.line(25, y + 6, width - 25, y + 6)
                pdf.setFont("Helvetica", 7)

            pdf.drawString(col_x[0], y, (supplier.code or '')[:10])
            pdf.drawString(col_x[1], y, (supplier.name or '')[:30])
            pdf.drawString(col_x[2], y, (supplier.contact_person or '')[:20])
            pdf.drawString(col_x[3], y, (supplier.email or '')[:24])
            pdf.drawString(col_x[4], y, (supplier.phone or '')[:14])
            pdf.drawString(col_x[5], y, (supplier.tax_id or '')[:12])
            pdf.drawString(col_x[6], y, 'Yes' if supplier.is_active else 'No')
            y -= 9

        pdf.showPage()
        pdf.save()
        return response

    # Default CSV (Excel-friendly)
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="suppliers.csv"'

    writer = csv.writer(response)
    writer.writerow(['Code', 'Name', 'Contact Person', 'Email', 'Phone', 'Address', 'Payment Terms', 'Tax ID', 'VAT Registered', 'Active'])

    for supplier in suppliers:
        writer.writerow([
            supplier.code,
            supplier.name,
            supplier.contact_person,
            supplier.email,
            supplier.phone,
            supplier.address,
            supplier.payment_terms_days,
            supplier.tax_id,
            'Yes' if (supplier.tax_id or supplier.tin) else 'No',
            'Yes' if supplier.is_active else 'No',
        ])

    return response


# ============================
# Requisition Views
# ============================

@login_required
def requisition_list(request):
    """
    List all purchase requisitions
    """
    requisitions = PurchaseRequisition.objects.all().order_by('-created_at')
    context = {'requisitions': requisitions}
    return render(request, 'purchasing/requisition_list.html', context)


@login_required
def requisition_detail(request, requisition_id):
    """
    View requisition details
    """
    requisition = get_object_or_404(PurchaseRequisition, id=requisition_id)
    context = {'requisition': requisition}
    return render(request, 'purchasing/requisition_detail.html', context)


@login_required
def requisition_create(request):
    """
    Create a new purchase requisition
    """
    if request.method == 'POST':
        try:
            requisition = PurchaseRequisition.objects.create(
                requisition_number=request.POST.get('requisition_number'),
                required_date=request.POST.get('required_date'),
                requested_by=request.user,
                notes=request.POST.get('notes'),
                status='draft'
            )
            
            # Process requisition lines (simplified)
            messages.success(request, f"Requisition {requisition.requisition_number} created successfully.")
            return redirect('purchasing:requisition_detail', requisition_id=requisition.id)
        except Exception as e:
            messages.error(request, f"Error creating requisition: {str(e)}")
            return redirect('purchasing:requisition_create')
    
    return render(request, 'purchasing/requisition_form.html')


@login_required
def requisition_edit(request, requisition_id):
    """
    Edit requisition
    """
    requisition = get_object_or_404(PurchaseRequisition, id=requisition_id)
    
    if request.method == 'POST':
        try:
            requisition.required_date = request.POST.get('required_date')
            requisition.notes = request.POST.get('notes')
            requisition.save()
            
            messages.success(request, "Requisition updated successfully.")
            return redirect('purchasing:requisition_detail', requisition_id=requisition.id)
        except Exception as e:
            messages.error(request, f"Error updating requisition: {str(e)}")
            return redirect('purchasing:requisition_edit', requisition_id=requisition.id)
    
    context = {'requisition': requisition}
    return render(request, 'purchasing/requisition_form.html', context)


@login_required
def requisition_delete(request, requisition_id):
    """
    Delete requisition
    """
    requisition = get_object_or_404(PurchaseRequisition, id=requisition_id)
    
    if request.method == 'POST':
        req_number = requisition.requisition_number
        requisition.delete()
        messages.success(request, f"Requisition {req_number} deleted.")
        return redirect('purchasing:requisition_list')
    
    context = {'requisition': requisition}
    return render(request, 'purchasing/requisition_confirm_delete.html', context)


@login_required
def requisition_submit(request, requisition_id):
    """
    Submit requisition for approval
    """
    requisition = get_object_or_404(PurchaseRequisition, id=requisition_id)
    requisition.status = 'submitted'
    requisition.save()
    messages.success(request, "Requisition submitted for approval.")
    return redirect('purchasing:requisition_detail', requisition_id=requisition.id)


@login_required
def requisition_approve(request, requisition_id):
    """
    Approve requisition
    """
    requisition = get_object_or_404(PurchaseRequisition, id=requisition_id)
    requisition.status = 'approved'
    requisition.save()
    messages.success(request, "Requisition approved.")
    return redirect('purchasing:requisition_detail', requisition_id=requisition.id)


@login_required
def requisition_reject(request, requisition_id):
    """
    Reject requisition
    """
    requisition = get_object_or_404(PurchaseRequisition, id=requisition_id)
    
    if request.method == 'POST':
        reason = request.POST.get('reason')
        requisition.status = 'rejected'
        requisition.notes = f"Rejected: {reason}" if reason else "Rejected"
        requisition.save()
        messages.success(request, "Requisition rejected.")
        return redirect('purchasing:requisition_detail', requisition_id=requisition.id)
    
    context = {'requisition': requisition}
    return render(request, 'purchasing/requisition_reject.html', context)


@login_required
def create_po_from_requisition(request, requisition_id):
    """
    Create purchase order from requisition
    """
    requisition = get_object_or_404(PurchaseRequisition, id=requisition_id)
    # Redirect to PO create with pre-filled data
    return redirect(f"{reverse('purchasing:po_create')}?requisition={requisition_id}")


# ============================
# Goods Receipt Views
# ============================

@login_required
def goods_receipt_list(request):
    """
    List all goods receipts
    """
    receipts = GoodsReceipt.objects.all().select_related(
        'po', 'received_by'
    ).order_by('-receipt_date')
    context = {'receipts': receipts}
    return render(request, 'purchasing/receipt_list.html', context)


@login_required
def goods_receipt_detail(request, receipt_id):
    """
    View goods receipt details
    """
    receipt = get_object_or_404(
        GoodsReceipt.objects.select_related('po', 'received_by'),
        id=receipt_id
    )
    lines = GoodsReceiptLine.objects.filter(receipt=receipt).select_related('po_line')
    context = {'receipt': receipt, 'lines': lines}
    return render(request, 'purchasing/receipt_detail.html', context)


@login_required
def goods_receipt_create(request):
    """
    Create a new goods receipt
    """
    if request.method == 'POST':
        try:
            po_id = request.POST.get('po')
            po = get_object_or_404(PurchaseOrder, id=po_id)
            
            receipt = GoodsReceipt.objects.create(
                receipt_number=request.POST.get('receipt_number'),
                po=po,
                receipt_date=request.POST.get('receipt_date'),
                notes=request.POST.get('notes'),
                received_by=request.user,
                created_by=request.user
            )
            
            messages.success(request, f"Goods receipt {receipt.receipt_number} created successfully.")
            return redirect('purchasing:goods_receipt_detail', receipt_id=receipt.id)
        except Exception as e:
            messages.error(request, f"Error creating goods receipt: {str(e)}")
            return redirect('purchasing:goods_receipt_create')
    
    pos = PurchaseOrder.objects.filter(status__in=['ordered', 'approved']).order_by('-order_date')
    context = {'pos': pos}
    return render(request, 'purchasing/receipt_form.html', context)


@login_required
def goods_receipt_edit(request, receipt_id):
    """
    Edit goods receipt
    """
    receipt = get_object_or_404(GoodsReceipt, id=receipt_id)
    
    if request.method == 'POST':
        try:
            receipt.receipt_date = request.POST.get('receipt_date')
            receipt.notes = request.POST.get('notes')
            receipt.save()
            
            messages.success(request, "Goods receipt updated successfully.")
            return redirect('purchasing:goods_receipt_detail', receipt_id=receipt.id)
        except Exception as e:
            messages.error(request, f"Error updating goods receipt: {str(e)}")
            return redirect('purchasing:goods_receipt_edit', receipt_id=receipt.id)
    
    context = {'receipt': receipt}
    return render(request, 'purchasing/receipt_form.html', context)


@login_required
def goods_receipt_delete(request, receipt_id):
    """
    Delete goods receipt
    """
    receipt = get_object_or_404(GoodsReceipt, id=receipt_id)
    
    if request.method == 'POST':
        receipt_number = receipt.receipt_number
        receipt.delete()
        messages.success(request, f"Goods receipt {receipt_number} deleted.")
        return redirect('purchasing:goods_receipt_list')
    
    context = {'receipt': receipt}
    return render(request, 'purchasing/receipt_confirm_delete.html', context)


@login_required
def export_receipts(request):
    """
    Export goods receipts to CSV/Excel
    """
    import csv
    from django.http import HttpResponse
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="goods_receipts.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Receipt Number', 'PO Number', 'Received Date', 'Notes', 'Created By', 'Created Date'])
    
    receipts = GoodsReceipt.objects.all().select_related('po', 'received_by')
    for receipt in receipts:
        writer.writerow([
            receipt.receipt_number,
            receipt.po.po_number if receipt.po else '',
            receipt.receipt_date,
            receipt.notes,
            receipt.received_by.username if receipt.received_by else '',
            receipt.created_at,
        ])
    
    return response


# ============================
# Report Views
# ============================

@login_required
def purchasing_report(request):
    """
    Main purchasing report
    """
    context = {}
    return render(request, 'purchasing/report.html', context)


@login_required
def spend_analysis(request):
    """
    Spend analysis report
    """
    # Get spend by supplier
    supplier_spend = PurchaseOrder.objects.filter(
        status='received'
    ).values('supplier__name').annotate(
        total_spend=Sum('total_amount')
    ).order_by('-total_spend')[:10]
    
    # Get spend by category (simplified - you'd need item categories)
    context = {
        'supplier_spend': supplier_spend,
    }
    return render(request, 'purchasing/spend_analysis.html', context)


@login_required
def lead_time_report(request):
    """
    Supplier lead time report
    """
    # Calculate lead times for received POs
    pos = PurchaseOrder.objects.filter(
        status='received'
    ).select_related('supplier')
    
    lead_times = []
    for po in pos:
        if po.received_date and po.order_date:
            lead_time = (po.received_date - po.order_date).days
            lead_times.append({
                'supplier': po.supplier.name,
                'po_number': po.po_number,
                'order_date': po.order_date,
                'received_date': po.received_date,
                'lead_time': lead_time,
            })
    
    context = {'lead_times': lead_times}
    return render(request, 'purchasing/lead_time_report.html', context)


@login_required
def po_status_report(request):
    """
    Purchase order status report
    """
    status_counts = PurchaseOrder.objects.values('status').annotate(
        count=Count('id')
    ).order_by('status')
    
    context = {'status_counts': status_counts}
    return render(request, 'purchasing/po_status_report.html', context)


# ============================
# AJAX Views
# ============================

@login_required
def ajax_supplier_info(request, supplier_id):
    """
    AJAX endpoint to get supplier information
    """
    try:
        supplier = Supplier.objects.get(id=supplier_id)
        data = {
            'id': supplier.id,
            'name': supplier.name,
            'code': supplier.code,
            'contact_person': supplier.contact_person,
            'email': supplier.email,
            'phone': supplier.phone,
            'address': supplier.address,
            'payment_terms': supplier.payment_terms_days,
            'payment_terms_days': supplier.payment_terms_days,
            'vat_registered': bool(supplier.tax_id or supplier.tin),
            'tax_id': supplier.tax_id,
        }
        return JsonResponse(data)
    except Supplier.DoesNotExist:
        return JsonResponse({'error': 'Supplier not found'}, status=404)


@login_required
def ajax_po_lines(request, po_id):
    """
    AJAX endpoint to get PO lines
    """
    try:
        po = PurchaseOrder.objects.get(id=po_id)
        lines = []
        for line in po.lines.all():
            lines.append({
                'id': line.id,
                'item': line.item,
                'quantity_ordered': float(line.quantity_ordered),
                'unit': line.unit,
                'unit_price': float(line.unit_price),
                'tax_rate': float(line.tax_rate),
                'total_price': float(line.total_price),
            })
        return JsonResponse({'lines': lines})
    except PurchaseOrder.DoesNotExist:
        return JsonResponse({'error': 'PO not found'}, status=404)


@login_required
def ajax_item_price(request, item_id, supplier_id):
    """
    AJAX endpoint to get item price from supplier
    """
    try:
        # Since item is CharField, we can't get it by ID like this
        # This is a placeholder - you'll need to implement proper item lookup
        data = {
            'item_id': item_id,
            'unit_price': 0,
            'unit': '',
            'tax_rate': 0,
        }
        return JsonResponse(data)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=404)
    
@login_required
def ajax_check_po_number(request):
    """Check if PO number already exists"""
    po_number = request.GET.get('po_number')
    if po_number:
        exists = PurchaseOrder.objects.filter(po_number=po_number).exists()
        return JsonResponse({'exists': exists})
    return JsonResponse({'exists': False})

