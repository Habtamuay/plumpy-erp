from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Sum, Q, F
from django.http import HttpResponse, JsonResponse
from datetime import timedelta
from decimal import Decimal
import csv
import json

from .models import (
    SalesOrder, SalesOrderLine, SalesInvoice, SalesInvoiceLine,
    SalesShipment, SalesShipmentLine, SalesPayment
)
from apps.accounting.models import JournalEntry, JournalLine, Account
from apps.company.models import Customer
from apps.core.models import Item, Unit
from apps.inventory.models import Warehouse, Lot, StockTransaction


# ============================
# Dashboard
# ============================

@login_required
def dashboard(request):
    """Main sales dashboard"""
    today = timezone.now().date()
    
    # Statistics
    total_orders = SalesOrder.objects.count()
    pending_orders = SalesOrder.objects.filter(status='confirmed').count()
    processing_orders = SalesOrder.objects.filter(status='processing').count()
    shipped_orders = SalesOrder.objects.filter(status='shipped').count()
    
    # Recent orders
    recent_orders = SalesOrder.objects.select_related('customer').order_by('-order_date')[:10]
    
    # Top customers
    top_customers = Customer.objects.annotate(
        total_orders=Count('sales_orders'),
        total_spent=Sum('sales_orders__total_amount')
    ).order_by('-total_spent')[:5]
    
    # Recent invoices
    recent_invoices = SalesInvoice.objects.select_related('customer').order_by('-invoice_date')[:10]
    
    # Overdue invoices
    overdue_invoices = SalesInvoice.objects.filter(
        status__in=['posted', 'partial'],
        due_date__lt=today
    ).count()
    
    context = {
        'total_orders': total_orders,
        'pending_orders': pending_orders,
        'processing_orders': processing_orders,
        'shipped_orders': shipped_orders,
        'recent_orders': recent_orders,
        'top_customers': top_customers,
        'recent_invoices': recent_invoices,
        'overdue_invoices': overdue_invoices,
        'today': today,
    }
    
    return render(request, 'sales/dashboard.html', context)


# ============================
# Sales Order Views
# ============================

@login_required
def order_list(request):
    """List all sales orders"""
    orders = SalesOrder.objects.select_related('customer').order_by('-order_date')
    
    # Filter by status
    status = request.GET.get('status')
    if status:
        orders = orders.filter(status=status)
    
    # Filter by customer
    customer_id = request.GET.get('customer')
    if customer_id:
        orders = orders.filter(customer_id=customer_id)
    
    # Filter by date range
    date_from = request.GET.get('from')
    date_to = request.GET.get('to')
    if date_from and date_to:
        orders = orders.filter(order_date__range=[date_from, date_to])
    
    context = {
        'orders': orders,
        'status_choices': SalesOrder.STATUS_CHOICES,
        'customers': Customer.objects.filter(is_active=True),
        'today': timezone.now().date(),
    }
    
    return render(request, 'sales/order_list.html', context)


@login_required
def order_detail(request, order_id):
    """View sales order details"""
    order = get_object_or_404(
        SalesOrder.objects.select_related('customer', 'created_by'),
        id=order_id
    )
    
    lines = order.lines.all().select_related('item', 'unit', 'warehouse')
    shipments = order.shipments.all().select_related('warehouse')
    invoices = order.invoices.all()
    
    context = {
        'order': order,
        'lines': lines,
        'shipments': shipments,
        'invoices': invoices,
        'today': timezone.now().date(),
    }
    
    return render(request, 'sales/order_detail.html', context)


@login_required
def order_create(request):
    """Create a new sales order"""
    if request.method == 'POST':
        try:
            # Create order
            order = SalesOrder.objects.create(
                customer_id=request.POST.get('customer'),
                order_date=request.POST.get('order_date') or timezone.now().date(),
                expected_ship_date=request.POST.get('expected_ship_date'),
                shipping_address=request.POST.get('shipping_address', ''),
                shipping_city=request.POST.get('shipping_city', ''),
                tax_rate=Decimal(request.POST.get('tax_rate', 15)),
                discount_percent=Decimal(request.POST.get('discount_percent', 0)),
                shipping_amount=Decimal(request.POST.get('shipping_amount', 0)),
                notes=request.POST.get('notes', ''),
                terms_conditions=request.POST.get('terms_conditions', ''),
                created_by=request.user,
                status='draft'
            )
            
            # Process order lines
            items = request.POST.getlist('item[]')
            quantities = request.POST.getlist('quantity[]')
            unit_prices = request.POST.getlist('unit_price[]')
            
            for i in range(len(items)):
                if items[i] and quantities[i] and unit_prices[i]:
                    SalesOrderLine.objects.create(
                        order=order,
                        item_id=items[i],
                        quantity=Decimal(quantities[i]),
                        unit_price=Decimal(unit_prices[i]),
                        unit_id=request.POST.getlist('unit[]')[i],
                        warehouse_id=request.POST.getlist('warehouse[]')[i] or None,
                        notes=request.POST.getlist('line_notes[]')[i] if i < len(request.POST.getlist('line_notes[]')) else ''
                    )
            
            order.calculate_totals()
            messages.success(request, f'Sales Order {order.order_number} created successfully.')
            return redirect('sales:order_detail', order_id=order.id)
            
        except Exception as e:
            messages.error(request, f'Error creating order: {e}')
    
    customers = Customer.objects.filter(is_active=True).order_by('name')
    products = Item.objects.filter(category='finished', is_active=True).select_related('unit')
    warehouses = Warehouse.objects.filter(is_active=True)
    
    context = {
        'customers': customers,
        'products': products,
        'warehouses': warehouses,
        'today': timezone.now().date(),
    }
    
    return render(request, 'sales/order_form.html', context)


@login_required
def order_edit(request, order_id):
    """Edit a sales order"""
    order = get_object_or_404(SalesOrder, id=order_id)
    
    if order.status not in ['draft', 'confirmed']:
        messages.error(request, 'Only draft or confirmed orders can be edited.')
        return redirect('sales:order_detail', order_id=order.id)
    
    if request.method == 'POST':
        try:
            order.customer_id = request.POST.get('customer')
            order.expected_ship_date = request.POST.get('expected_ship_date')
            order.shipping_address = request.POST.get('shipping_address', '')
            order.shipping_city = request.POST.get('shipping_city', '')
            order.tax_rate = Decimal(request.POST.get('tax_rate', 15))
            order.discount_percent = Decimal(request.POST.get('discount_percent', 0))
            order.shipping_amount = Decimal(request.POST.get('shipping_amount', 0))
            order.notes = request.POST.get('notes', '')
            order.terms_conditions = request.POST.get('terms_conditions', '')
            order.save()
            
            # Delete existing lines and recreate
            order.lines.all().delete()
            
            # Process order lines
            items = request.POST.getlist('item[]')
            quantities = request.POST.getlist('quantity[]')
            unit_prices = request.POST.getlist('unit_price[]')
            
            for i in range(len(items)):
                if items[i] and quantities[i] and unit_prices[i]:
                    SalesOrderLine.objects.create(
                        order=order,
                        item_id=items[i],
                        quantity=Decimal(quantities[i]),
                        unit_price=Decimal(unit_prices[i]),
                        unit_id=request.POST.getlist('unit[]')[i],
                        warehouse_id=request.POST.getlist('warehouse[]')[i] or None,
                        notes=request.POST.getlist('line_notes[]')[i] if i < len(request.POST.getlist('line_notes[]')) else ''
                    )
            
            order.calculate_totals()
            messages.success(request, f'Sales Order {order.order_number} updated successfully.')
            return redirect('sales:order_detail', order_id=order.id)
            
        except Exception as e:
            messages.error(request, f'Error updating order: {e}')
    
    customers = Customer.objects.filter(is_active=True).order_by('name')
    products = Item.objects.filter(category='finished', is_active=True).select_related('unit')
    warehouses = Warehouse.objects.filter(is_active=True)
    
    context = {
        'order': order,
        'lines': order.lines.all(),
        'customers': customers,
        'products': products,
        'warehouses': warehouses,
        'today': timezone.now().date(),
    }
    
    return render(request, 'sales/order_form.html', context)


@login_required
def order_confirm(request, order_id):
    """Confirm a sales order"""
    order = get_object_or_404(SalesOrder, id=order_id)
    
    if order.status != 'draft':
        messages.error(request, 'Only draft orders can be confirmed.')
        return redirect('sales:order_detail', order_id=order.id)
    
    order.status = 'confirmed'
    order.save()
    
    messages.success(request, f'Order {order.order_number} confirmed successfully.')
    return redirect('sales:order_detail', order_id=order.id)


@login_required
def order_cancel(request, order_id):
    """Cancel a sales order"""
    order = get_object_or_404(SalesOrder, id=order_id)
    
    if order.status in ['shipped', 'delivered', 'closed']:
        messages.error(request, 'Cannot cancel shipped, delivered, or closed orders.')
        return redirect('sales:order_detail', order_id=order.id)
    
    order.status = 'cancelled'
    order.save()
    
    messages.success(request, f'Order {order.order_number} cancelled.')
    return redirect('sales:order_detail', order_id=order.id)


# ============================
# Sales Invoice Views
# ============================

@login_required
def invoice_list(request):
    """List all sales invoices"""
    invoices = SalesInvoice.objects.select_related('customer').order_by('-invoice_date')
    
    # Filter by status
    status = request.GET.get('status')
    if status:
        invoices = invoices.filter(status=status)
    
    # Filter by customer
    customer_id = request.GET.get('customer')
    if customer_id:
        invoices = invoices.filter(customer_id=customer_id)
    
    context = {
        'invoices': invoices,
        'status_choices': SalesInvoice.STATUS_CHOICES,
        'customers': Customer.objects.filter(is_active=True),
        'today': timezone.now().date(),
    }
    
    return render(request, 'sales/invoice_list.html', context)


@login_required
def invoice_detail(request, invoice_id):
    """View invoice details"""
    invoice = get_object_or_404(
        SalesInvoice.objects.select_related('customer', 'sales_order', 'journal_entry'),
        id=invoice_id
    )
    
    lines = invoice.lines.all().select_related('item', 'unit')
    payments = invoice.payments.all().order_by('-payment_date')
    
    context = {
        'invoice': invoice,
        'lines': lines,
        'payments': payments,
        'today': timezone.now().date(),
    }
    
    return render(request, 'sales/invoice_detail.html', context)


@login_required
def create_invoice_from_order(request, order_id):
    """Create an invoice from a sales order"""
    order = get_object_or_404(SalesOrder, id=order_id)

    if order.status not in ['confirmed', 'processing', 'ready_to_ship']:
        messages.error(request, "Sales Order must be confirmed before invoicing.")
        return redirect('sales:order_detail', order_id=order.id)

    if order.invoice_generated:
        messages.warning(request, "Invoice already exists for this order.")
        return redirect('sales:invoice_detail', invoice_id=order.invoice.id)

    try:
        with transaction.atomic():
            # Create invoice
            invoice = SalesInvoice.objects.create(
                sales_order=order,
                customer=order.customer,
                invoice_date=timezone.now().date(),
                due_date=timezone.now().date() + timedelta(days=30),
                tax_rate=order.tax_rate,
                shipping_amount=order.shipping_amount,
                discount_amount=order.discount_amount,
                status='draft',
                created_by=request.user
            )

            # Copy lines from Sales Order
            for line in order.lines.all():
                SalesInvoiceLine.objects.create(
                    invoice=invoice,
                    sales_order_line=line,
                    item=line.item,
                    description=line.item.name,
                    quantity=line.quantity,
                    unit=line.unit,
                    unit_price=line.unit_price,
                    discount_percent=line.discount_percent
                )

            invoice.calculate_totals()

            # Auto-post journal entry
            je = JournalEntry.objects.create(
                company=order.customer.company,
                entry_date=invoice.invoice_date,
                reference=invoice.invoice_number,
                narration=f"Sales Invoice from SO {order.order_number}",
                is_posted=True,
                posted_at=timezone.now(),
                created_by=request.user
            )
            
            # Get accounts
            ar_account = Account.objects.get_or_create(
                code='1100',
                defaults={'name': 'Accounts Receivable', 'account_type': 'asset'}
            )[0]
            sales_account = Account.objects.get_or_create(
                code='4100',
                defaults={'name': 'Sales Revenue', 'account_type': 'revenue'}
            )[0]
            
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
            
            # Cr VAT if applicable
            if invoice.tax_amount and invoice.tax_amount > 0:
                vat_account = Account.objects.get_or_create(
                    code='2200',
                    defaults={'name': 'VAT Payable', 'account_type': 'liability'}
                )[0]
                JournalLine.objects.create(
                    journal=je,
                    account=vat_account,
                    credit=invoice.tax_amount,
                    narration=f"VAT on {invoice.invoice_number}"
                )

            invoice.journal_entry = je
            invoice.status = 'posted'
            invoice.save()

            order.invoice_generated = True
            order.invoice = invoice
            order.status = 'invoiced'
            order.save()

            messages.success(request, f"Invoice {invoice.invoice_number} created and posted successfully.")
            return redirect('sales:invoice_detail', invoice_id=invoice.id)
            
    except Exception as e:
        messages.error(request, f"Error creating invoice: {e}")
        return redirect('sales:order_detail', order_id=order.id)


@login_required
def invoice_send(request, invoice_id):
    """Mark invoice as sent to customer"""
    invoice = get_object_or_404(SalesInvoice, id=invoice_id)
    
    if invoice.status != 'posted':
        messages.error(request, 'Only posted invoices can be marked as sent.')
        return redirect('sales:invoice_detail', invoice_id=invoice.id)
    
    invoice.status = 'sent'
    invoice.save()
    
    # Here you could also trigger email sending
    messages.success(request, f'Invoice {invoice.invoice_number} marked as sent.')
    return redirect('sales:invoice_detail', invoice_id=invoice.id)


@login_required
def invoice_cancel(request, invoice_id):
    """Cancel an invoice"""
    invoice = get_object_or_404(SalesInvoice, id=invoice_id)
    
    if invoice.status in ['paid', 'partial']:
        messages.error(request, 'Cannot cancel paid or partially paid invoices.')
        return redirect('sales:invoice_detail', invoice_id=invoice.id)
    
    invoice.status = 'cancelled'
    invoice.save()
    
    messages.success(request, f'Invoice {invoice.invoice_number} cancelled.')
    return redirect('sales:invoice_detail', invoice_id=invoice.id)


# ============================
# Shipment Views
# ============================

@login_required
def shipment_list(request):
    """List all shipments"""
    shipments = SalesShipment.objects.select_related('sales_order', 'warehouse').order_by('-shipment_date')
    
    context = {
        'shipments': shipments,
        'today': timezone.now().date(),
    }
    
    return render(request, 'sales/shipment_list.html', context)


@login_required
def shipment_detail(request, shipment_id):
    """View shipment details"""
    shipment = get_object_or_404(
        SalesShipment.objects.select_related('sales_order', 'warehouse', 'created_by'),
        id=shipment_id
    )
    
    lines = shipment.lines.all().select_related('sales_order_line__item', 'lot')
    
    context = {
        'shipment': shipment,
        'lines': lines,
        'today': timezone.now().date(),
    }
    
    return render(request, 'sales/shipment_detail.html', context)


@login_required
def create_shipment(request, order_id):
    """Create a shipment for an order"""
    order = get_object_or_404(SalesOrder, id=order_id)
    
    if order.status not in ['confirmed', 'processing', 'ready_to_ship']:
        messages.error(request, 'Order must be confirmed to create shipment.')
        return redirect('sales:order_detail', order_id=order.id)
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # Create shipment
                shipment = SalesShipment.objects.create(
                    sales_order=order,
                    shipment_date=timezone.now().date(),
                    carrier=request.POST.get('carrier', ''),
                    tracking_number=request.POST.get('tracking_number', ''),
                    shipping_cost=Decimal(request.POST.get('shipping_cost', 0)),
                    warehouse_id=request.POST.get('warehouse'),
                    shipping_address=order.shipping_address,
                    shipping_city=order.shipping_city,
                    status='pending',
                    created_by=request.user
                )
                
                # Process shipment lines
                order_lines = request.POST.getlist('order_line[]')
                quantities = request.POST.getlist('ship_quantity[]')
                lots = request.POST.getlist('lot[]')
                
                for i in range(len(order_lines)):
                    if order_lines[i] and quantities[i] and Decimal(quantities[i]) > 0:
                        order_line = SalesOrderLine.objects.get(id=order_lines[i])
                        
                        SalesShipmentLine.objects.create(
                            shipment=shipment,
                            sales_order_line=order_line,
                            quantity=Decimal(quantities[i]),
                            lot_id=lots[i] if lots[i] else None
                        )
                
                # Update shipment status if all lines have lots assigned
                if all(l.line.lot for l in shipment.lines.all()):
                    shipment.status = 'picking'
                    shipment.save()
                
                messages.success(request, f'Shipment {shipment.shipment_number} created successfully.')
                return redirect('sales:shipment_detail', shipment_id=shipment.id)
                
        except Exception as e:
            messages.error(request, f'Error creating shipment: {e}')
    
    # Get available lots for each order line
    lines = order.lines.all().select_related('item', 'warehouse')
    for line in lines:
        line.available_lots = Lot.objects.filter(
            item=line.item,
            warehouse=line.warehouse,
            is_active=True,
            current_quantity__gt=0
        ).order_by('expiry_date')
    
    warehouses = Warehouse.objects.filter(is_active=True)
    
    context = {
        'order': order,
        'lines': lines,
        'warehouses': warehouses,
        'today': timezone.now().date(),
    }
    
    return render(request, 'sales/shipment_form.html', context)


@login_required
def shipment_ship(request, shipment_id):
    """Mark shipment as shipped"""
    shipment = get_object_or_404(SalesShipment, id=shipment_id)
    
    if shipment.status not in ['pending', 'picking', 'packed']:
        messages.error(request, 'Shipment cannot be marked as shipped from current status.')
        return redirect('sales:shipment_detail', shipment_id=shipment.id)
    
    shipment.status = 'shipped'
    shipment.save()
    
    messages.success(request, f'Shipment {shipment.shipment_number} marked as shipped.')
    return redirect('sales:shipment_detail', shipment_id=shipment.id)


@login_required
def shipment_deliver(request, shipment_id):
    """Mark shipment as delivered"""
    shipment = get_object_or_404(SalesShipment, id=shipment_id)
    
    if shipment.status != 'shipped':
        messages.error(request, 'Only shipped shipments can be marked as delivered.')
        return redirect('sales:shipment_detail', shipment_id=shipment.id)
    
    shipment.status = 'delivered'
    shipment.delivery_date = timezone.now().date()
    shipment.save()
    
    messages.success(request, f'Shipment {shipment.shipment_number} marked as delivered.')
    return redirect('sales:shipment_detail', shipment_id=shipment.id)


# ============================
# Payment Views
# ============================

@login_required
def payment_list(request):
    """List all payments"""
    payments = SalesPayment.objects.select_related('invoice__customer').order_by('-payment_date')
    
    context = {
        'payments': payments,
        'today': timezone.now().date(),
    }
    
    return render(request, 'sales/payment_list.html', context)


@login_required
def payment_create(request, invoice_id):
    """Record a payment for an invoice"""
    invoice = get_object_or_404(SalesInvoice, id=invoice_id)
    
    if invoice.status in ['paid', 'cancelled']:
        messages.error(request, 'Cannot add payment to paid or cancelled invoice.')
        return redirect('sales:invoice_detail', invoice_id=invoice.id)
    
    if request.method == 'POST':
        try:
            amount = Decimal(request.POST.get('amount', 0))
            
            if amount <= 0:
                messages.error(request, 'Amount must be positive.')
                return redirect('sales:payment_create', invoice_id=invoice.id)
            
            if amount > invoice.remaining_amount:
                messages.error(request, f'Amount exceeds remaining balance of {invoice.remaining_amount}.')
                return redirect('sales:payment_create', invoice_id=invoice.id)
            
            payment = SalesPayment.objects.create(
                invoice=invoice,
                payment_date=request.POST.get('payment_date') or timezone.now().date(),
                amount=amount,
                payment_method=request.POST.get('payment_method'),
                reference=request.POST.get('reference', ''),
                notes=request.POST.get('notes', ''),
                created_by=request.user
            )
            
            messages.success(request, f'Payment of {amount} recorded successfully.')
            return redirect('sales:invoice_detail', invoice_id=invoice.id)
            
        except Exception as e:
            messages.error(request, f'Error recording payment: {e}')
    
    context = {
        'invoice': invoice,
        'today': timezone.now().date(),
        'payment_methods': SalesPayment.PAYMENT_METHODS,
    }
    
    return render(request, 'sales/payment_form.html', context)


# ============================
# AJAX Views
# ============================

@login_required
def ajax_order_lines(request, order_id):
    """AJAX endpoint to get order lines"""
    lines = SalesOrderLine.objects.filter(order_id=order_id).select_related('item', 'unit')
    
    data = []
    for line in lines:
        data.append({
            'id': line.id,
            'item_code': line.item.code,
            'item_name': line.item.name,
            'quantity': float(line.quantity),
            'unit': line.unit.abbreviation,
            'unit_price': float(line.unit_price),
            'total': float(line.total_price),
            'shipped': float(line.quantity_shipped),
            'remaining': float(line.remaining_to_ship),
        })
    
    return JsonResponse({'lines': data})


@login_required
def ajax_item_price(request, item_id, customer_id):
    """AJAX endpoint to get item price for customer"""
    from apps.sales.models import CustomerPricing
    
    try:
        # Check if there's special pricing for this customer
        pricing = CustomerPricing.objects.filter(
            customer_id=customer_id,
            item_id=item_id,
            is_active=True
        ).first()
        
        if pricing:
            price = float(pricing.unit_price)
        else:
            # Default to item's standard price
            item = Item.objects.get(id=item_id)
            price = float(item.unit_cost or 0) * 1.3  # Example markup
        
        return JsonResponse({'price': price})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


# ============================
# Export Views
# ============================

@login_required
def export_orders(request):
    """Export orders to CSV"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="orders_{timezone.now().strftime("%Y%m%d")}.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Order #', 'Customer', 'Order Date', 'Expected Ship Date', 'Total Amount', 'Status'])
    
    orders = SalesOrder.objects.select_related('customer')
    for order in orders:
        writer.writerow([
            order.order_number,
            order.customer.name,
            order.order_date,
            order.expected_ship_date,
            float(order.total_amount),
            order.get_status_display()
        ])
    
    return response