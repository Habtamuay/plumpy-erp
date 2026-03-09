from decimal import Decimal
import csv
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.db.models import Q, Sum

from .models import (
    SalesOrder, SalesOrderLine,
    SalesInvoice, SalesInvoiceLine,
    SalesShipment, SalesShipmentLine,
    SalesPayment
)
from apps.company.models import Customer
from apps.core.models import Item, Unit
from apps.inventory.models import Warehouse
from apps.company.models import Company


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

# =========================================================
# DASHBOARD
# =========================================================

@login_required
def dashboard(request):
    company = _current_company(request)
    if company is None:
        messages.error(request, "Please select a company first.")
        return redirect('core:home')

    context = {
        "orders": _scope(SalesOrder.objects.all(), company).count(),
        "invoices": _scope(SalesInvoice.objects.all(), company).count(),
        "shipments": _scope(SalesShipment.objects.all(), company).count(),
        "total_revenue": _scope(SalesInvoice.objects.filter(status='paid'), company).aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    }
    return render(request, "sales/dashboard.html", context)

# =========================================================
# SALES ORDERS
# =========================================================

@login_required
def order_list(request):
    company = _current_company(request)
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
        customer = get_object_or_404(Customer, id=customer_id, company=company)
        
        order = SalesOrder.objects.create(
            company=company,
            customer=customer,
            order_date=request.POST.get("order_date", timezone.now().date()),
            discount_percent=Decimal(request.POST.get("discount_percent", 0)),
            tax_rate=Decimal(request.POST.get("tax_rate", 15)),
            created_by=request.user
        )
        messages.success(request, f"Sales order {order.order_number} created.")
        return redirect("sales:order_detail", order_id=order.id)

    customers = Customer.objects.filter(company=company)
    return render(request, "sales/order_create.html", {"customers": customers})

@login_required
def order_detail(request, order_id):
    company = _current_company(request)
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
    order = get_object_or_404(_scope(SalesOrder.objects.all(), company), id=order_id)
    order.status = "confirmed"
    order.save(update_fields=["status"])
    messages.success(request, "Order confirmed.")
    return redirect("sales:order_detail", order_id=order.id)

@login_required
def invoice_create(request):
    company = _current_company(request)
    if company is None:
        messages.error(request, "Please select a company first.")
        return redirect('core:home')

    if request.method == "POST":
        # Handle form submission
        customer_id = request.POST.get("customer")
        sales_order_id = request.POST.get("sales_order")
        invoice_date = request.POST.get("invoice_date")
        due_date = request.POST.get("due_date")
        tax_rate = Decimal(request.POST.get("tax_rate", 0))
        payment_method = request.POST.get("payment_method", "credit")
        notes = request.POST.get("notes", "")
        
        customer = get_object_or_404(Customer, id=customer_id, company=company)
        sales_order = None
        if sales_order_id:
            sales_order = get_object_or_404(_scope(SalesOrder.objects.all(), company), id=sales_order_id)
        
        invoice = SalesInvoice.objects.create(
            company=company,
            customer=customer,
            sales_order=sales_order,
            invoice_date=invoice_date,
            due_date=due_date,
            tax_rate=tax_rate,
            payment_method=payment_method,
            notes=notes
        )
        
        # Create invoice lines
        items = request.POST.getlist("item")
        quantities = request.POST.getlist("quantity")
        units = request.POST.getlist("unit")
        unit_prices = request.POST.getlist("unit_price")
        discount_percents = request.POST.getlist("discount_percent")
        
        for i in range(len(items)):
            if items[i]:  # Skip empty lines
                item = get_object_or_404(_scope(Item.objects.all(), company, include_legacy=True), id=items[i])
                unit = get_object_or_404(Unit, id=units[i]) if units[i] else None
                
                SalesInvoiceLine.objects.create(
                    company=company,
                    invoice=invoice,
                    item=item,
                    quantity=Decimal(quantities[i]),
                    unit=unit,
                    unit_price=Decimal(unit_prices[i]),
                    discount_percent=Decimal(discount_percents[i] or 0)
                )
        
        messages.success(request, f"Invoice {invoice.invoice_number} created successfully.")
        
        if request.POST.get("save_and_new"):
            return redirect("sales:invoice_create")
        else:
            return redirect("sales:invoice_detail", invoice_id=invoice.id)
    
    # GET request - show form
    customers = Customer.objects.filter(company=company)
    sales_orders = _scope(SalesOrder.objects.filter(status__in=['confirmed', 'processing', 'shipped']).select_related('customer'), company)
    items = _scope(Item.objects.all(), company, include_legacy=True)
    units = _scope(Unit.objects.all(), company, include_legacy=True)
    
    context = {
        "customers": customers,
        "sales_orders": sales_orders,
        "items": items,
        "units": units,
        "today": timezone.now().date(),
        "payment_methods": SalesInvoice.PAYMENT_METHODS,
    }
    
    return render(request, "sales/invoice_form.html", context)

# =========================================================
# INVOICES (Logic consolidated into Model method)
# =========================================================

@login_required
def create_invoice_from_order(request, order_id):
    company = _current_company(request)
    order = get_object_or_404(_scope(SalesOrder.objects.all(), company), id=order_id)
    if order.status == "cancelled":
        messages.error(request, "Cannot invoice a cancelled order.")
        return redirect("sales:order_detail", order_id=order.id)
    
    invoice = order.create_invoice(user=request.user)
    messages.success(request, f"Invoice {invoice.invoice_number} generated.")
    return redirect("sales:invoice_detail", invoice_id=invoice.id)
    order = get_object_or_404(SalesOrder, id=order_id)
    if order.status == "cancelled":
        messages.error(request, "Cannot invoice a cancelled order.")
        return redirect("sales:order_detail", order_id=order.id)
    
    invoice = order.create_invoice(user=request.user)
    messages.success(request, f"Invoice {invoice.invoice_number} generated.")
    return redirect("sales:invoice_detail", invoice_id=invoice.id)

@login_required
def invoice_list(request):
    company = _current_company(request)
    invoices = _scope(SalesInvoice.objects.select_related("customer"), company).order_by("-id")
    return render(request, "sales/invoice_list.html", {"invoices": invoices, "today": timezone.now().date()})

@login_required
def invoice_detail(request, invoice_id):
    company = _current_company(request)
    invoice = get_object_or_404(_scope(SalesInvoice.objects.all(), company), id=invoice_id)
    return render(request, "sales/invoice_detail.html", {
        "invoice": invoice, 
        "lines": invoice.lines.all(),
        "payments": invoice.payments.all()
    })

@login_required
def print_invoice_view(request, invoice_id):
    company = _current_company(request)
    invoice = get_object_or_404(_scope(SalesInvoice.objects.select_related('customer'), company), id=invoice_id)
    lines = invoice.lines.all()
    
    return render(request, "sales/invoice_print.html", {
        "invoice": invoice,
        "lines": lines,
    })
# =========================================================
# SHIPMENTS
# =========================================================

@login_required
def create_shipment(request, order_id):
    company = _current_company(request)
    order = get_object_or_404(_scope(SalesOrder.objects.all(), company), id=order_id)
    # Note: Warehouse selection usually happens in a form; defaulting for brevity
    warehouse = Warehouse.objects.filter(company=company).first()
    
    shipment = SalesShipment.objects.create(
        company=company,
        sales_order=order,
        warehouse=warehouse,
        shipment_date=timezone.now().date()
    )
    
    # Optionally auto-populate shipment lines from order lines
    for line in order.lines.all():
        SalesShipmentLine.objects.create(
            company=company,
            shipment=shipment,
            sales_order_line=line,
            quantity=line.quantity
        )
        
    messages.success(request, f"Shipment {shipment.shipment_number} created.")
    return redirect("sales:shipment_detail", shipment_id=shipment.id)

@login_required
def shipment_ship(request, shipment_id):
    company = _current_company(request)
    shipment = get_object_or_404(_scope(SalesShipment.objects.all(), company), id=shipment_id)
    shipment.status = "shipped"
    shipment.save() # This triggers the inventory movement logic in the model
    messages.success(request, "Shipment has left the warehouse. Inventory updated.")
    return redirect("sales:shipment_detail", shipment_id=shipment.id)
@login_required
def customer_history(request, customer_id):
    company = _current_company(request)
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
# PAYMENTS
# =========================================================

@login_required
def payment_create(request, invoice_id):
    company = _current_company(request)
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

# =========================================================
# EXPORT & AJAX
# =========================================================

@login_required
def export_orders(request):
    company = _current_company(request)
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="orders_{timezone.now().date()}.csv"'
    writer = csv.writer(response)
    writer.writerow(["Order Number", "Customer", "Date", "Status", "Total"])
    
    for o in _scope(SalesOrder.objects.all(), company):
        writer.writerow([o.order_number, o.customer.name, o.order_date, o.get_status_display(), o.total_amount])
    return response

@login_required
def order_edit(request, order_id):
    company = _current_company(request)
    order = get_object_or_404(_scope(SalesOrder.objects.all(), company), id=order_id)
    
    if request.method == "POST":
        customer_id = request.POST.get("customer")
        order.customer_id = customer_id
        order.order_date = request.POST.get("order_date", order.order_date)
        order.discount_percent = Decimal(request.POST.get("discount_percent", 0))
        order.tax_rate = Decimal(request.POST.get("tax_rate", 15))
        
        order.save() # This will trigger calculate_totals() inside the model's save/save_base logic
        messages.success(request, "Order updated successfully.")
        return redirect("sales:order_detail", order_id=order.id)

    customers = Customer.objects.filter(company=company)
    return render(request, "sales/order_edit.html", {
        "order": order,
        "customers": customers
    })
# =========================================================
# ADDITIONAL ORDER ACTIONS
# =========================================================

@login_required
def order_cancel(request, order_id):
    company = _current_company(request)
    order = get_object_or_404(_scope(SalesOrder.objects.all(), company), id=order_id)
    order.status = "cancelled"
    order.save(update_fields=["status"])
    messages.success(request, "Order has been cancelled.")
    return redirect("sales:order_detail", order_id=order.id)

# =========================================================
# ADDITIONAL INVOICE ACTIONS
# =========================================================

@login_required
def invoice_send(request, invoice_id):
    company = _current_company(request)
    invoice = get_object_or_404(_scope(SalesInvoice.objects.all(), company), id=invoice_id)
    invoice.status = "sent"
    invoice.save(update_fields=["status"])
    messages.success(request, "Invoice marked as sent.")
    return redirect("sales:invoice_detail", invoice_id=invoice.id)

@login_required
def invoice_cancel(request, invoice_id):
    company = _current_company(request)
    invoice = get_object_or_404(_scope(SalesInvoice.objects.all(), company), id=invoice_id)
    invoice.status = "cancelled"
    invoice.save(update_fields=["status"])
    messages.success(request, "Invoice has been cancelled.")
    return redirect("sales:invoice_detail", invoice_id=invoice.id)

# =========================================================
# ADDITIONAL SHIPMENT ACTIONS
# =========================================================

@login_required
def shipment_list(request):
    company = _current_company(request)
    shipments = _scope(SalesShipment.objects.select_related("sales_order", "warehouse"), company).order_by("-id")
    return render(request, "sales/shipment_list.html", {"shipments": shipments})

@login_required
def shipment_detail(request, shipment_id):
    company = _current_company(request)
    shipment = get_object_or_404(_scope(SalesShipment.objects.all(), company), id=shipment_id)
    return render(request, "sales/shipment_detail.html", {
        "shipment": shipment,
        "lines": shipment.lines.all()
    })

@login_required
def shipment_deliver(request, shipment_id):
    company = _current_company(request)
    shipment = get_object_or_404(_scope(SalesShipment.objects.all(), company), id=shipment_id)
    shipment.status = "delivered"
    # Note: If you added a delivered_at field to the model, uncomment below:
    # shipment.delivered_at = timezone.now()
    shipment.save(update_fields=["status"])
    messages.success(request, "Shipment marked as delivered.")
    return redirect("sales:shipment_detail", shipment_id=shipment.id)

# =========================================================
# ADDITIONAL PAYMENT ACTIONS
# =========================================================

@login_required
def payment_list(request):
    company = _current_company(request)
    payments = _scope(SalesPayment.objects.select_related("invoice__customer"), company).order_by("-id")
    return render(request, "sales/payment_list.html", {"payments": payments})


@login_required
def ajax_item_price(request, item_id):
    company = _current_company(request)
    item = get_object_or_404(_scope(Item.objects.all(), company, include_legacy=True), id=item_id)
    # Assuming Item model has a base_price field
    return JsonResponse({"price": float(getattr(item, 'price', 0))})
@login_required
def get_sales_order_details(request):
    """
    AJAX view to fetch order lines for client-side processing.
    """
    order_id = request.GET.get("order_id")
    company = _current_company(request)
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
            "discount_percent": float(line.discount_percent),
        })

    return JsonResponse(data)

@login_required
def get_invoice_details(request):
    invoice_id = request.GET.get("invoice_id")
    company = _current_company(request)
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
    item = get_object_or_404(_scope(Item.objects.all(), company, include_legacy=True), id=item_id)
    # Using getattr as a safety net in case the field name varies
    price = getattr(item, 'price', 0) 
    return JsonResponse({"price": float(price)})
