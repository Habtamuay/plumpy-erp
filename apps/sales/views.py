from decimal import Decimal
import csv
from datetime import timedelta  # ADDED - missing import
from collections import defaultdict
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.db.models import Q, Sum, Avg, Count

from .models import (
    SalesOrder, SalesOrderLine,
    SalesInvoice, SalesInvoiceLine,
    SalesShipment, SalesShipmentLine,
    SalesPayment
)
from .forms import SalesInvoiceForm, SalesInvoiceLineFormSet  # ADDED - missing import
from apps.company.models import Customer
from apps.core.models import Item, Unit
from apps.inventory.models import Warehouse
from apps.company.models import Company
from .utils.invoice_pdf import generate_invoice_pdf  # Keep this import


def _current_company(request):
    company_id = request.session.get('current_company_id')
    if not company_id:
        return None
    return Company.objects.filter(id=company_id, is_active=True).first()


def _scope(qs, company, include_legacy=False):
    if company is None:
        return qs.none()
    if include_legacy:
        return qs.filter(Q(company=company) | Q(company__isnull=True))
    return qs.filter(company=company)


def generate_invoice_number():
    """Generate a unique invoice number"""
    from django.utils import timezone
    last_invoice = SalesInvoice.objects.order_by('-id').first()
    if last_invoice:
        try:
            last_num = int(last_invoice.invoice_number.split('-')[-1])
            new_num = last_num + 1
        except (ValueError, AttributeError):
            new_num = 1
    else:
        new_num = 1
    
    today = timezone.now()
    return f"INV-{today.strftime('%Y%m')}-{new_num:05d}"


# =========================================================
# DASHBOARD
# =========================================================

class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "sales/dashboard.html"

    def get(self, request, *args, **kwargs):
        company = _current_company(request)
        if company is None:
            messages.error(request, "Please select a company first.")
            return redirect('core:home')
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        company = _current_company(self.request)
        
        # Get all orders for this company
        orders = _scope(SalesOrder.objects.all(), company)
        
        # Order statistics
        total_orders = orders.count()
        pending_orders = orders.filter(status='draft').count()
        confirmed_orders = orders.filter(status='confirmed').count()
        processing_orders = orders.filter(status='processing').count()
        shipped_orders = orders.filter(status='shipped').count()
        delivered_orders = orders.filter(status='delivered').count()
        invoiced_orders = orders.filter(status='invoiced').count()
        cancelled_orders = orders.filter(status='cancelled').count()
        
        # Get recent orders (last 5)
        recent_orders = orders.select_related('customer').order_by('-created_at')[:5]
        
        # Invoice statistics
        invoices = _scope(SalesInvoice.objects.all(), company)
        total_invoices = invoices.count()
        paid_invoices = invoices.filter(status='paid').count()
        unpaid_invoices = invoices.filter(status__in=['posted', 'partial', 'overdue']).count()
        overdue_invoices = invoices.filter(status='overdue').count()
        
        # Get recent invoices (last 5)
        recent_invoices = invoices.select_related('customer').order_by('-invoice_date', '-id')[:5]
        
        # Shipment statistics
        shipments = _scope(SalesShipment.objects.all(), company)
        pending_shipments = shipments.filter(status='draft').count()
        shipped_shipments = shipments.filter(status='shipped').count()
        delivered_shipments = shipments.filter(status='delivered').count()
        
        # Payment statistics
        payments = _scope(SalesPayment.objects.all(), company)
        total_payments = payments.aggregate(total=Sum('amount'))['total'] or 0
        
        # Monthly sales trend (last 6 months)
        from django.db.models.functions import TruncMonth
        import datetime
        
        six_months_ago = timezone.now() - datetime.timedelta(days=180)
        
        monthly_sales = invoices.filter(
            invoice_date__gte=six_months_ago,
            status__in=['paid', 'posted', 'partial']
        ).annotate(
            month=TruncMonth('invoice_date')
        ).values('month').annotate(
            total=Sum('total_amount'),
            count=Count('id')
        ).order_by('month')
        
        # Format monthly sales data for chart
        monthly_labels = []
        monthly_data = []
        for item in monthly_sales:
            monthly_labels.append(item['month'].strftime('%b %Y'))
            monthly_data.append(float(item['total'] or 0))
        
        # Order status breakdown for pie chart
        status_data = [
            pending_orders,
            confirmed_orders,
            processing_orders,
            shipped_orders + delivered_orders,
            cancelled_orders
        ]
        status_labels = ['Draft', 'Confirmed', 'Processing', 'Shipped/Delivered', 'Cancelled']
        
        # Sales by Item Category
        sales_by_category = SalesInvoiceLine.objects.filter(
            invoice__company=company,
            invoice__status__in=['paid', 'posted', 'partial'],
            invoice__invoice_date__gte=six_months_ago
        ).values('item__category').annotate(
            total=Sum('total_price')
        ).order_by('-total')
        
        category_labels = [item['item__category'].title().replace('_', ' ') for item in sales_by_category if item['item__category']]
        category_data = [float(item['total']) for item in sales_by_category if item['item__category']]
        
        # Top customers by revenue
        top_customers = Customer.objects.filter(
            company=company,
            is_active=True
        ).annotate(
            order_count=Count('sales_orders'),
            total_spent=Sum('sales_orders__total_amount'),
            avg_order=Avg('sales_orders__total_amount')
        ).filter(
            order_count__gt=0
        ).order_by('-total_spent')[:5]
        
        # Quick stats for summary cards
        total_revenue = invoices.filter(status__in=['paid', 'posted']).aggregate(total=Sum('total_amount'))['total'] or 0
        pending_revenue = invoices.filter(status='partial').aggregate(total=Sum('total_amount'))['total'] or 0
        
        context.update({
            # Order statistics
            'total_orders': total_orders,
            'pending_orders': pending_orders,
            'confirmed_orders': confirmed_orders,
            'processing_orders': processing_orders,
            'shipped_orders': shipped_orders,
            'delivered_orders': delivered_orders,
            'invoiced_orders': invoiced_orders,
            'cancelled_orders': cancelled_orders,
            
            # Summary counts for cards
            'total_orders_count': total_orders,
            'pending_orders_count': pending_orders + confirmed_orders,
            'processing_count': processing_orders,
            'shipped_delivered_count': shipped_orders + delivered_orders,
            
            # Recent items
            'recent_orders': recent_orders,
            'recent_invoices': recent_invoices,
            
            # Invoice statistics
            'total_invoices': total_invoices,
            'paid_invoices': paid_invoices,
            'unpaid_invoices': unpaid_invoices,
            'overdue_invoices': overdue_invoices,
            
            # Shipment statistics
            'pending_shipments': pending_shipments,
            'shipped_shipments': shipped_shipments,
            'delivered_shipments': delivered_shipments,
            
            # Payment statistics
            'total_payments': total_payments,
            'total_revenue': total_revenue,
            'pending_revenue': pending_revenue,
            
            # Chart data
            'monthly_labels': monthly_labels,
            'monthly_data': monthly_data,
            'status_labels': status_labels,
            'status_data': status_data,
            'category_labels': category_labels,
            'category_data': category_data,
            
            # Top customers
            'top_customers': top_customers,
        })
        return context

# For backward compatibility with existing URLs, assign the view to the variable 'dashboard'
dashboard = DashboardView.as_view()


# =========================================================
# SALES ORDERS
# =========================================================

@login_required
def order_list(request):
    company = _current_company(request)
    if company is None:
        messages.error(request, "Please select a company first.")
        return redirect('core:home')
    orders = _scope(SalesOrder.objects.select_related("customer"), company).order_by("-id")
    return render(request, "sales/order_list.html", {"orders": orders})


@login_required
def order_create(request):
    company = _current_company(request)
    if company is None:
        messages.error(request, "Please select a company first.")
        return redirect('core:home')

    if request.method == "POST":
        customer_id = request.POST.get("customer")
        customer = get_object_or_404(_scope(Customer.objects.filter(is_active=True), company), id=customer_id)
        
        order = SalesOrder.objects.create(
            company=company,
            customer=customer,
            order_date=request.POST.get("order_date", timezone.now().date()),
            expected_ship_date=request.POST.get("expected_ship_date") or None,
            tax_rate=Decimal(request.POST.get("tax_rate", 15)),
            notes=request.POST.get("notes", ""),
            terms_conditions=request.POST.get("terms_conditions", ""),
            created_by=request.user
        )
        
        messages.success(request, f"Sales order {order.order_number} created successfully.")
        # Redirect to edit page so user can add items
        return redirect("sales:order_edit", order_id=order.id)

    # GET request
    customers = _scope(Customer.objects.filter(is_active=True), company).order_by('name')
    
    context = {
        'company': company,
        'customers': customers,
        'today': timezone.now().date(),
        'form_title': "Create New Sales Order",
    }
    return render(request, "sales/order_form.html", context)


@login_required
def order_detail(request, order_id):
    company = _current_company(request)
    if company is None:
        messages.error(request, "Please select a company first.")
        return redirect('core:home')
    order = get_object_or_404(_scope(SalesOrder.objects.select_related("customer", "created_by"), company), id=order_id)
    lines = order.lines.select_related("item", "unit")
    invoices = order.invoices.all()
    shipments = order.shipments.all()
    return render(request, "sales/order_detail.html", {
        "order": order, 
        "lines": lines,
        "invoices": invoices,
        "shipments": shipments
    })


@login_required
def order_confirm(request, order_id):
    company = _current_company(request)
    if company is None:
        messages.error(request, "Please select a company first.")
        return redirect('core:home')
    
    order = get_object_or_404(_scope(SalesOrder.objects.all(), company), id=order_id)
    
    # Check if order has lines
    if not order.lines.exists():
        messages.error(request, "Cannot confirm order with no items.")
        return redirect("sales:order_edit", order_id=order.id)
    
    order.status = "confirmed"
    order.save(update_fields=["status"])
    
    messages.success(request, f"Order {order.order_number} confirmed successfully.")
    return redirect("sales:order_detail", order_id=order.id)

@login_required
def order_edit(request, order_id):
    company = _current_company(request)
    if company is None:
        messages.error(request, "Please select a company first.")
        return redirect('core:home')

    order = get_object_or_404(
        _scope(SalesOrder.objects.select_related('customer').prefetch_related('lines'), company), 
        id=order_id
    )
    
    if request.method == "POST":
        # Update order basic info
        customer_id = request.POST.get("customer")
        if customer_id:
            customer = get_object_or_404(Customer, id=customer_id, company=company)
            order.customer = customer
        
        order.order_date = request.POST.get("order_date", order.order_date)
        order.expected_ship_date = request.POST.get("expected_ship_date") or None
        order.tax_rate = Decimal(request.POST.get("tax_rate", order.tax_rate))
        order.notes = request.POST.get("notes", "")
        order.terms_conditions = request.POST.get("terms_conditions", "")
        order.save()
        
        # Handle order lines
        items = request.POST.getlist("item[]")
        quantities = request.POST.getlist("quantity[]")
        units = request.POST.getlist("unit[]")
        unit_prices = request.POST.getlist("unit_price[]")
        line_ids = request.POST.getlist("line_id[]")
        
        kept_line_ids = []
        
        for i in range(len(items)):
            if items[i] and quantities[i] and Decimal(quantities[i]) > 0:
                # Get item
                item = get_object_or_404(_scope(Item.objects.all(), company, include_legacy=True), id=items[i])
                
                # Handle Unit
                unit_id = units[i] if i < len(units) and units[i] else None
                unit = Unit.objects.filter(id=unit_id).first() if unit_id else item.unit
                
                price = Decimal(unit_prices[i]) if unit_prices[i] else item.unit_cost
                
                # Check for existing line ID
                line_id = line_ids[i] if i < len(line_ids) and line_ids[i] else None
                
                if line_id and line_id.isdigit():
                    # Update existing line
                    line = get_object_or_404(SalesOrderLine, id=line_id, order=order)
                    line.item = item
                    line.quantity = Decimal(quantities[i])
                    line.unit = unit
                    line.unit_price = price
                    line.save()
                    kept_line_ids.append(line.id)
                else:
                    # Create new line
                    line = SalesOrderLine.objects.create(
                        company=company,
                        order=order,
                        item=item,
                        quantity=Decimal(quantities[i]),
                        unit=unit,
                        unit_price=price,
                    )
                    kept_line_ids.append(line.id)
        
        # Delete removed lines
        order.lines.exclude(id__in=kept_line_ids).delete()
        
        # Recalculate totals
        order.calculate_totals()
        order.refresh_from_db()
        
        messages.success(request, f"Sales order {order.order_number} updated successfully.")
        
        # Check if user clicked "Save and Continue" or "Save and Confirm"
        if 'save_and_continue' in request.POST:
            return redirect("sales:order_edit", order_id=order.id)
        elif 'save_and_confirm' in request.POST:
            order.status = 'confirmed'
            order.save(update_fields=['status'])
            messages.success(request, f"Order {order.order_number} confirmed.")
            return redirect("sales:order_detail", order_id=order.id)
        else:
            return redirect("sales:order_detail", order_id=order.id)
    
    # GET request
    items = _scope(Item.objects.filter(is_active=True), company, include_legacy=True).select_related('unit').order_by('code')
    units = _scope(Unit.objects.filter(is_active=True), company, include_legacy=True).order_by('name')
    customers = Customer.objects.filter(company=company, is_active=True).order_by('name')
    
    context = {
        'order': order,
        'customers': customers,
        'items': items,
        'units': units,
        'lines': order.lines.all(),
        'form_title': f"Edit Sales Order {order.order_number}",
    }
    return render(request, "sales/order_edit.html", context)

@login_required
def order_print(request, order_id):
    company = _current_company(request)
    if company is None:
        messages.error(request, "Please select a company first.")
        return redirect('core:home')
    
    order = get_object_or_404(
        _scope(SalesOrder.objects.select_related('customer', 'company'), company), 
        id=order_id
    )
    
    return render(request, "sales/order_print.html", {"order": order})


@login_required
def order_pdf(request, order_id):
    company = _current_company(request)
    if company is None:
        messages.error(request, "Please select a company first.")
        return redirect('core:home')
    
    order = get_object_or_404(
        _scope(SalesOrder.objects.select_related('customer', 'company'), company), 
        id=order_id
    )
    
    # You'll need to install a PDF library like weasyprint or reportlab
    # For now, we'll just redirect to the print view
    return redirect('sales:order_print', order_id=order_id)


@login_required
def order_cancel(request, order_id):
    company = _current_company(request)
    if company is None:
        messages.error(request, "Please select a company first.")
        return redirect('core:home')
    order = get_object_or_404(_scope(SalesOrder.objects.all(), company), id=order_id)
    order.status = "cancelled"
    order.save(update_fields=["status"])
    messages.success(request, "Order has been cancelled.")
    return redirect("sales:order_detail", order_id=order.id)


# =========================================================
# INVOICES
# =========================================================

@login_required
def invoice_create(request):
    """Create a new sales invoice with line items"""
    company = _current_company(request)
    if company is None:
        messages.error(request, "Please select a company first.")
        return redirect('core:home')

    if request.method == "POST":
        form = SalesInvoiceForm(request.POST, company=company)
        formset = SalesInvoiceLineFormSet(request.POST, instance=SalesInvoice(), form_kwargs={'company': company})
        
        # Check if a sales order was selected to autofill lines
        sales_order_id = request.POST.get('sales_order')
        autofill_from_order = 'autofill' in request.POST
        
        if autofill_from_order and sales_order_id:
            # Just render the form with autofilled lines
            invoice = SalesInvoice(sales_order_id=sales_order_id)
            formset = SalesInvoiceLineFormSet(instance=invoice, form_kwargs={'company': company})
            
            # Get the sales order and its lines
            try:
                sales_order = SalesOrder.objects.get(id=sales_order_id, company=company)
                # Create formset with initial data from order lines
                initial_lines = []
                for line in sales_order.lines.all():
                    initial_lines.append({
                        'item': line.item,
                        'description': line.item.name,
                        'quantity': line.quantity,
                        'unit': line.unit,
                        'unit_price': line.unit_price,
                    })
                
                formset = SalesInvoiceLineFormSet(
                    instance=SalesInvoice(sales_order=sales_order),
                    queryset=SalesInvoiceLine.objects.none(),
                    initial=initial_lines,
                    form_kwargs={'company': company}
                )
                
                # Pre-fill customer from order
                form = SalesInvoiceForm(initial={
                    'customer': sales_order.customer,
                    'invoice_date': timezone.now().date(),
                    'due_date': timezone.now().date() + timedelta(days=30),
                    'tax_rate': sales_order.tax_rate,
                }, company=company)
                
            except SalesOrder.DoesNotExist:
                messages.error(request, "Selected sales order not found.")
        
        elif form.is_valid() and formset.is_valid():
            # Save the invoice
            invoice = form.save(commit=False)
            invoice.company = company
            invoice.invoice_number = generate_invoice_number()
            invoice.save()
            
            # Save the lines
            formset.instance = invoice
            formset.save()
            
            # Calculate totals
            invoice.calculate_totals()
            
            messages.success(request, f"Invoice {invoice.invoice_number} created successfully.")
            
            if request.POST.get("save_and_new"):
                return redirect("sales:invoice_create")
            else:
                return redirect("sales:invoice_detail", invoice_id=invoice.id)
        else:
            # Form is invalid, show errors
            if not form.is_valid():
                for field, errors in form.errors.items():
                    for error in errors:
                        messages.error(request, f"{field}: {error}")
            if not formset.is_valid():
                for error in formset.non_form_errors():
                    messages.error(request, error)
    
    else:
        # GET request - show empty form
        form = SalesInvoiceForm(company=company)
        formset = SalesInvoiceLineFormSet(instance=SalesInvoice(), form_kwargs={'company': company})
    
    # Get all necessary data for the template
    customers = Customer.objects.filter(company=company, is_active=True)
    sales_orders = SalesOrder.objects.filter(
        company=company,
        status__in=['confirmed', 'processing', 'shipped']
    ).select_related('customer').order_by('-order_date')
    
    items = Item.objects.filter(company=company, is_active=True).select_related('unit')
    units = Unit.objects.filter(company=company, is_active=True)
    
    context = {
        'form': form,
        'formset': formset,
        'customers': customers,
        'sales_orders': sales_orders,
        'items': items,
        'units': units,
        'today': timezone.now().date(),
        'payment_methods': SalesInvoice.PAYMENT_METHODS,
    }
    
    return render(request, "sales/invoice_form.html", context)


@login_required
def create_invoice_from_order(request, order_id):
    company = _current_company(request)
    if company is None:
        messages.error(request, "Please select a company first.")
        return redirect('core:home')
    order = get_object_or_404(_scope(SalesOrder.objects.all(), company), id=order_id)
    if order.status == "cancelled":
        messages.error(request, "Cannot invoice a cancelled order.")
        return redirect("sales:order_detail", order_id=order.id)
    
    invoice = order.create_invoice(user=request.user)
    messages.success(request, f"Invoice {invoice.invoice_number} generated.")
    return redirect("sales:invoice_detail", invoice_id=invoice.id)


@login_required
def invoice_list(request):
    company = _current_company(request)
    if company is None:
        messages.error(request, "Please select a company first.")
        return redirect('core:home')
    invoices = _scope(SalesInvoice.objects.select_related("customer"), company).order_by("-id")
    return render(request, "sales/invoice_list.html", {"invoices": invoices, "today": timezone.now().date()})


@login_required
def invoice_detail(request, invoice_id):
    company = _current_company(request)
    if company is None:
        messages.error(request, "Please select a company first.")
        return redirect('core:home')
    invoice = get_object_or_404(_scope(SalesInvoice.objects.all(), company), id=invoice_id)
    return render(request, "sales/invoice_detail.html", {
        "invoice": invoice, 
        "lines": invoice.lines.all(),
        "payments": invoice.payments.all()
    })


@login_required
def print_invoice_view(request, invoice_id):
    company = _current_company(request)
    if company is None:
        messages.error(request, "Please select a company first.")
        return redirect('core:home')
    invoice = get_object_or_404(
        _scope(SalesInvoice.objects.select_related('customer', 'company'), company), 
        id=invoice_id
    )
    
    try:
        # Generate PDF bytes from the utility function
        pdf_bytes = generate_invoice_pdf(invoice)
        
        # Create a proper HttpResponse
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        # This header makes it open in the browser, good for printing
        response['Content-Disposition'] = f'inline; filename="invoice_{invoice.invoice_number}.pdf"'
        
        # Add cache control headers to prevent caching issues
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        return response
    except Exception as e:
        messages.error(request, f"Error generating PDF: {str(e)}")
        return redirect('sales:invoice_detail', invoice_id=invoice_id)


@login_required
def invoice_send(request, invoice_id):
    company = _current_company(request)
    if company is None:
        messages.error(request, "Please select a company first.")
        return redirect('core:home')
    invoice = get_object_or_404(_scope(SalesInvoice.objects.all(), company), id=invoice_id)
    invoice.status = "sent"
    invoice.save(update_fields=["status"])
    messages.success(request, "Invoice marked as sent.")
    return redirect("sales:invoice_detail", invoice_id=invoice.id)


@login_required
def invoice_cancel(request, invoice_id):
    company = _current_company(request)
    if company is None:
        messages.error(request, "Please select a company first.")
        return redirect('core:home')
    invoice = get_object_or_404(_scope(SalesInvoice.objects.all(), company), id=invoice_id)
    invoice.status = "cancelled"
    invoice.save(update_fields=["status"])
    messages.success(request, "Invoice has been cancelled.")
    return redirect("sales:invoice_detail", invoice_id=invoice.id)


# =========================================================
# SHIPMENTS
# =========================================================

@login_required
def create_shipment(request, order_id):
    company = _current_company(request)
    if company is None:
        messages.error(request, "Please select a company first.")
        return redirect('core:home')
    order = get_object_or_404(_scope(SalesOrder.objects.all(), company), id=order_id)

    # Group lines by warehouse
    lines_by_warehouse = defaultdict(list)
    lines_without_warehouse = []
    
    # Only consider lines that have something remaining to be shipped
    lines_to_ship = [line for line in order.lines.all() if line.quantity_remaining > 0]

    for line in lines_to_ship:
        if line.warehouse:
            lines_by_warehouse[line.warehouse].append(line)
        else:
            lines_without_warehouse.append(line)

    if not lines_by_warehouse:
        if not lines_to_ship:
            messages.info(request, "Order is already fully shipped.")
        else:
            messages.warning(request, "Cannot create shipment. No lines with remaining quantity have a warehouse assigned.")
        return redirect("sales:order_detail", order_id=order.id)

    created_shipments = []
    for warehouse, lines in lines_by_warehouse.items():
        # Create one shipment per warehouse
        shipment = SalesShipment.objects.create(
            company=company,
            sales_order=order,
            warehouse=warehouse,
            shipment_date=timezone.now().date()
        )
        created_shipments.append(shipment)
        
        # Add lines to this shipment
        for line in lines:
            if line.quantity_remaining > 0:
                SalesShipmentLine.objects.create(
                    company=company,
                    shipment=shipment,
                    sales_order_line=line,
                    quantity=line.quantity_remaining # Ship what's remaining
                )
    
    if created_shipments:
        shipment_numbers = ", ".join([s.shipment_number for s in created_shipments])
        messages.success(request, f"Created shipment(s): {shipment_numbers}.")
    
    if lines_without_warehouse:
        messages.warning(request, f"{len(lines_without_warehouse)} line(s) were not shipped as they had no warehouse assigned.")

    # Redirect to the order detail page, as there could be multiple shipments.
    return redirect("sales:order_detail", order_id=order.id)


@login_required
def shipment_list(request):
    company = _current_company(request)
    if company is None:
        messages.error(request, "Please select a company first.")
        return redirect('core:home')
    shipments = _scope(SalesShipment.objects.select_related("sales_order", "warehouse"), company).order_by("-id")
    return render(request, "sales/shipment_list.html", {"shipments": shipments})


@login_required
def shipment_detail(request, shipment_id):
    company = _current_company(request)
    if company is None:
        messages.error(request, "Please select a company first.")
        return redirect('core:home')
    shipment = get_object_or_404(_scope(SalesShipment.objects.all(), company), id=shipment_id)
    return render(request, "sales/shipment_detail.html", {
        "shipment": shipment,
        "lines": shipment.lines.all()
    })


@login_required
def shipment_ship(request, shipment_id):
    company = _current_company(request)
    if company is None:
        messages.error(request, "Please select a company first.")
        return redirect('core:home')
    shipment = get_object_or_404(_scope(SalesShipment.objects.all(), company), id=shipment_id)
    shipment.status = "shipped"
    shipment.save() # This triggers the inventory movement logic in the model
    messages.success(request, "Shipment has left the warehouse. Inventory updated.")
    return redirect("sales:shipment_detail", shipment_id=shipment.id)


@login_required
def shipment_deliver(request, shipment_id):
    company = _current_company(request)
    if company is None:
        messages.error(request, "Please select a company first.")
        return redirect('core:home')
    shipment = get_object_or_404(_scope(SalesShipment.objects.all(), company), id=shipment_id)
    shipment.status = "delivered"
    # Note: If you added a delivered_at field to the model, uncomment below:
    # shipment.delivered_at = timezone.now()
    shipment.save(update_fields=["status"])
    messages.success(request, "Shipment marked as delivered.")
    return redirect("sales:shipment_detail", shipment_id=shipment.id)


# =========================================================
# PAYMENTS
# =========================================================

@login_required
def payment_create(request, invoice_id):
    company = _current_company(request)
    if company is None:
        messages.error(request, "Please select a company first.")
        return redirect('core:home')
    invoice = get_object_or_404(_scope(SalesInvoice.objects.all(), company), id=invoice_id)
    if request.method == "POST":
        amount = Decimal(request.POST.get("amount"))
        method = request.POST.get("payment_method")
        
        SalesPayment.objects.create(
            company=company,
            invoice=invoice,
            amount=amount,
            payment_method=method,
            reference=request.POST.get("reference", "")
        )
        messages.success(request, "Payment successfully recorded.")
        return redirect("sales:invoice_detail", invoice_id=invoice.id)

    return render(request, "sales/payment_create.html", {"invoice": invoice})


@login_required
def payment_list(request):
    company = _current_company(request)
    if company is None:
        messages.error(request, "Please select a company first.")
        return redirect('core:home')
    payments = _scope(SalesPayment.objects.select_related("invoice__customer"), company).order_by("-id")
    return render(request, "sales/payment_list.html", {"payments": payments})


# =========================================================
# CUSTOMER HISTORY
# =========================================================

@login_required
def customer_history(request, customer_id):
    company = _current_company(request)
    if company is None:
        messages.error(request, "Please select a company first.")
        return redirect('core:home')
    customer = get_object_or_404(Customer, id=customer_id, company=company)
    
    # Get all related records
    orders = customer.sales_orders.all().order_by('-order_date')
    invoices = _scope(SalesInvoice.objects.filter(customer=customer), company).order_by('-invoice_date')
    
    # Financial Summary
    total_invoiced = invoices.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    total_paid = invoices.aggregate(Sum('paid_amount'))['paid_amount__sum'] or 0
    balance_due = total_invoiced - total_paid

    context = {
        "customer": customer,
        "orders": orders,
        "invoices": invoices,
        "total_invoiced": total_invoiced,
        "total_paid": total_paid,
        "balance_due": balance_due,
    }
    
    return render(request, "sales/customer_history.html", context)


# =========================================================
# EXPORT & AJAX
# =========================================================

@login_required
def export_orders(request):
    company = _current_company(request)
    if company is None:
        messages.error(request, "Please select a company first.")
        return redirect('core:home')
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="orders_{timezone.now().date()}.csv"'
    writer = csv.writer(response)
    writer.writerow(["Order Number", "Customer", "Date", "Status", "Total"])
    
    for o in _scope(SalesOrder.objects.all(), company):
        writer.writerow([o.order_number, o.customer.name, o.order_date, o.get_status_display(), o.total_amount])
    return response


@login_required
def get_sales_order_details(request):
    """
    AJAX view to fetch order lines for client-side processing.
    """
    order_id = request.GET.get("order_id")
    company = _current_company(request)
    if company is None:
        return JsonResponse({"success": False, "error": "No company selected"})
    
    order = get_object_or_404(_scope(SalesOrder.objects.all(), company), id=order_id)
    lines = order.lines.select_related("item", "unit")

    data = {
        "success": True,
        "customer_id": order.customer.id,
        "lines": []
    }
    
    for line in lines:
        data["lines"].append({
            "item_id": line.item.id,
            "quantity": float(line.quantity),
            "unit_id": line.unit.id if line.unit else None,
            "unit_price": float(line.unit_price),
        })

    return JsonResponse(data)


@login_required
def get_invoice_details(request):
    invoice_id = request.GET.get("invoice_id")
    company = _current_company(request)
    if company is None:
        return JsonResponse({"success": False, "error": "No company selected"})
    
    invoice = get_object_or_404(_scope(SalesInvoice.objects.all(), company), id=invoice_id)
    remaining = float(invoice.remaining_amount)
    status = "Fully Paid" if invoice.is_fully_paid else "Partial"
    return JsonResponse({
        "success": True,
        "customer_name": invoice.customer.name,
        "total_amount": float(invoice.total_amount),
        "remaining": remaining,
        "status": status,
    })


@login_required
def ajax_order_lines(request, order_id):
    """
    Returns a JSON list of lines for a specific Sales Order.
    """
    company = _current_company(request)
    if company is None:
        return JsonResponse({"success": False, "error": "No company selected"})
    
    lines = _scope(SalesOrderLine.objects.filter(order_id=order_id).select_related("item"), company)
    
    data = []
    for line in lines:
        data.append({
            "item": line.item.name,
            "qty": float(line.quantity),
            "price": float(line.unit_price),
            "total": float(line.total_price)
        })
        
    return JsonResponse(data, safe=False)


@login_required
def ajax_item_price(request, item_id, customer_id=None):
    """
    Fetches the price of an item for the UI. 
    Customer ID is optional if you implement customer-specific pricing later.
    """
    company = _current_company(request)
    if company is None:
        return JsonResponse({"success": False, "error": "No company selected"})
    
    item = get_object_or_404(_scope(Item.objects.all(), company, include_legacy=True), id=item_id)
    # Using getattr as a safety net in case the field name varies
    price = getattr(item, 'unit_cost', 0)  # Changed from 'price' to 'unit_cost' based on your model
    return JsonResponse({"price": float(price)})