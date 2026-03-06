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

from .models import (
    PurchaseOrder, PurchaseOrderLine, Supplier, 
    PurchaseRequisition, GoodsReceipt, GoodsReceiptLine
)
from apps.inventory.models import Item, Warehouse
from apps.core.models import Unit


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
    total_po_count = PurchaseOrder.objects.count()
    total_po_value = PurchaseOrder.objects.aggregate(
        total=Sum('total_amount')
    )['total'] or 0
    pending_count = PurchaseOrder.objects.filter(
        status__in=['draft', 'pending', 'approved']
    ).count()
    
    # Get all active suppliers for filter dropdown
    suppliers = Supplier.objects.filter(is_active=True).order_by('name')
    
    context = {
        'purchase_orders': page_obj,
        'page_obj': page_obj,
        'is_paginated': page_obj.has_other_pages(),
        'suppliers': suppliers,
        'total_po_count': total_po_count,
        'total_po_value': f"{total_po_value:,.0f}",
        'pending_count': pending_count,
        'this_month_count': PurchaseOrder.objects.filter(
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
    po = get_object_or_404(
        PurchaseOrder.objects.select_related('supplier', 'created_by'),
        id=po_id
    )
    
    # Get lines with related items and units
    lines = PurchaseOrderLine.objects.filter(po=po).select_related('item', 'unit')
    
    # Calculate totals
    subtotal = Decimal('0')
    tax_total = Decimal('0')
    
    for line in lines:
        line_total = line.quantity_ordered * line.unit_price
        line_tax = line_total * (line.tax_rate / 100)
        subtotal += line_total
        tax_total += line_tax
    
    grand_total = subtotal + tax_total + po.shipping_cost - po.discount
    
    # Get related receipts if any
    receipts = GoodsReceipt.objects.filter(po=po).select_related('received_by')
    
    context = {
        'po': po,
        'lines': lines,
        'subtotal': subtotal,
        'tax_total': tax_total,
        'grand_total': grand_total,
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
            expected_date = request.POST.get('expected_date')
            shipping_method = request.POST.get('shipping_method')
            shipping_address = request.POST.get('shipping_address')
            billing_address = request.POST.get('billing_address')
            notes = request.POST.get('notes')
            terms = request.POST.get('terms')
            shipping_cost = Decimal(request.POST.get('shipping_cost', 0))
            discount = Decimal(request.POST.get('discount', 0))
            currency = request.POST.get('currency', 'USD')
            payment_terms = request.POST.get('payment_terms')
            
            # Validate required fields
            if not supplier_id or not po_number or not order_date:
                messages.error(request, "Please fill in all required fields.")
                return redirect('purchasing:po_create')
            
            # Get supplier
            supplier = get_object_or_404(Supplier, id=supplier_id)
            
            # Create purchase order
            po = PurchaseOrder.objects.create(
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
            
            for i in range(len(line_items)):
                if line_items[i] and quantities[i] and quantities[i].strip():
                    item_id = line_items[i]
                    if item_id and item_id.strip():
                        try:
                            item = Item.objects.get(id=int(item_id))
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
                                    item=str(item.id),  # Store as string since item is CharField
                                    unit=str(unit.id) if unit else '',
                                    quantity_ordered=quantity,
                                    unit_price=unit_price,
                                    tax_rate=tax_rate
                                )
                                
                                line_total = line.quantity_ordered * line.unit_price
                                tax_amount = line_total * (line.tax_rate / 100)
                                total_amount += line_total + tax_amount
                        except (Item.DoesNotExist, ValueError) as e:
                            print(f"Error processing line {i}: {e}")
                            continue
            
            # Update PO total
            po.total_amount = total_amount + shipping_cost - discount
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
    suppliers = Supplier.objects.filter(is_active=True).order_by('name')
    
    # Get items - since item is CharField, we need to get from somewhere
    # This is a placeholder - you might have a different source for items
    items = []  # Replace with actual item query
    
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
    po = get_object_or_404(PurchaseOrder, id=po_id)
    
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
            po.expected_delivery_date = request.POST.get('expected_date')
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
            
            for i in range(len(line_items)):
                if line_items[i] and quantities[i] and quantities[i].strip():
                    item_id = line_items[i]
                    if item_id and item_id.strip():
                        try:
                            quantity = Decimal(quantities[i]) if quantities[i] else Decimal('0')
                            unit_price = Decimal(unit_prices[i]) if i < len(unit_prices) and unit_prices[i] else Decimal('0')
                            tax_rate = Decimal(tax_rates[i]) if i < len(tax_rates) and tax_rates[i] else Decimal('0')
                            
                            if quantity > 0:
                                line = PurchaseOrderLine.objects.create(
                                    po=po,
                                    item=str(item_id),
                                    unit=str(units[i]) if i < len(units) and units[i] else '',
                                    quantity_ordered=quantity,
                                    unit_price=unit_price,
                                    tax_rate=tax_rate
                                )
                                
                                line_total = line.quantity_ordered * line.unit_price
                                tax_amount = line_total * (line.tax_rate / 100)
                                total_amount += line_total + tax_amount
                        except (ValueError, DecimalException) as e:
                            print(f"Error processing line {i}: {e}")
                            continue
            
            po.total_amount = total_amount + po.shipping_cost - po.discount
            po.save()
            
            messages.success(request, f"Purchase Order {po.po_number} updated successfully.")
            return redirect('purchasing:po_detail', po_id=po.id)
            
        except Exception as e:
            messages.error(request, f"Error updating purchase order: {str(e)}")
            return redirect('purchasing:po_edit', po_id=po.id)
    
    # GET request - show form with existing data
    suppliers = Supplier.objects.filter(is_active=True).order_by('name')
    
    # Get items - placeholder
    items = []
    
    units = Unit.objects.all().order_by('name')
    
    context = {
        'po': po,
        'suppliers': suppliers,
        'items': items,
        'units': units,
        'order_lines': po.lines.all(),
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
                received_by=request.user
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
    po = get_object_or_404(
        PurchaseOrder.objects.select_related('supplier', 'created_by'),
        id=po_id
    )
    
    lines = PurchaseOrderLine.objects.filter(po=po)
    
    # Calculate totals
    subtotal = Decimal('0')
    tax_total = Decimal('0')
    
    for line in lines:
        line_total = line.quantity_ordered * line.unit_price
        line_tax = line_total * (line.tax_rate / 100)
        subtotal += line_total
        tax_total += line_tax
    
    grand_total = subtotal + tax_total + po.shipping_cost - po.discount
    
    context = {
        'po': po,
        'lines': lines,
        'subtotal': subtotal,
        'tax_total': tax_total,
        'grand_total': grand_total,
        'company_name': 'Your Company Name',  # Get from settings or company model
        'company_address': 'Your Company Address',
        'company_phone': '123-456-7890',
        'company_email': 'info@company.com',
        'company_tax_id': 'TAX123456',
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
    
    # Calculate metrics
    total_orders = purchase_orders.count()
    total_spent = purchase_orders.filter(status='received').aggregate(
        total=Sum('total_amount')
    )['total'] or 0
    
    # On-time delivery rate
    received_orders = purchase_orders.filter(status='received')
    on_time_orders = received_orders.filter(
        received_date__lte=models.F('expected_delivery_date')
    ).count()
    
    on_time_rate = 0
    if received_orders.count() > 0:
        on_time_rate = (on_time_orders / received_orders.count()) * 100
    
    context = {
        'supplier': supplier,
        'purchase_orders': purchase_orders[:10],
        'total_orders': total_orders,
        'total_spent': total_spent,
        'on_time_rate': round(on_time_rate, 1),
        'avg_lead_time': 7.5,  # Calculate from actual data
    }
    
    return render(request, 'purchasing/supplier_performance.html', context)


@login_required
def export_suppliers(request):
    """
    Export suppliers to CSV/Excel
    """
    import csv
    from django.http import HttpResponse
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="suppliers.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Code', 'Name', 'Contact Person', 'Email', 'Phone', 'Address', 'Payment Terms', 'Tax ID', 'Active'])
    
    suppliers = Supplier.objects.all()
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
                received_by=request.user
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

