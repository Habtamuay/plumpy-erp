from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.db.models import Q, Sum, Count, F
from django.utils import timezone
from django.http import HttpResponse, JsonResponse
from django.core.paginator import Paginator
from datetime import timedelta
from decimal import Decimal
import csv
import json

from .models import Item, Unit
from apps.inventory.models import StockTransaction, CurrentStock, Lot, Warehouse
from apps.production.models import ProductionRun, BOM
from apps.purchasing.models import PurchaseOrder
from apps.sales.models import SalesOrder, SalesInvoice
from apps.accounting.models import Account


# ============================
# Dashboard Views
# ============================

@login_required
def core_dashboard(request):
    """Main core module dashboard"""
    today = timezone.now().date()
    
    # Item statistics
    total_items = Item.objects.filter(is_active=True).count()
    items_by_category = Item.objects.filter(is_active=True).values('category').annotate(
        count=Count('id')
    ).order_by('category')
    
    # Stock value
    total_stock_value = CurrentStock.objects.aggregate(
        total=Sum(F('quantity') * F('item__unit_cost'))
    )['total'] or 0
    
    # Low stock items
    low_stock_items = CurrentStock.objects.filter(
        Q(quantity__lt=F('item__minimum_stock')) |
        Q(quantity__lte=F('item__reorder_point'))
    ).count()
    
    # Recent items
    recent_items = Item.objects.filter(is_active=True).order_by('-created_at')[:5]
    
    # Inventory stats
    warehouse_count = Warehouse.objects.filter(is_active=True).count()
    active_lots = Lot.objects.filter(is_active=True).count()
    near_expiry_count = Lot.objects.filter(
        expiry_date__lte=today + timedelta(days=90),
        expiry_date__gte=today,
        is_active=True
    ).count()
    
    # Recent transactions
    recent_transactions = StockTransaction.objects.select_related(
        'item'
    ).order_by('-transaction_date')[:10]
    
    # Production stats
    active_production_runs = ProductionRun.objects.filter(status='in_progress').count()
    planned_runs = ProductionRun.objects.filter(status='planned').count()
    completed_runs = ProductionRun.objects.filter(status='completed').count()
    in_progress_runs = ProductionRun.objects.filter(status='in_progress').count()
    active_boms = BOM.objects.filter(is_active=True).count()
    
    # Active production runs list with calculated percentages
    active_runs = ProductionRun.objects.filter(
        status__in=['planned', 'in_progress']
    ).select_related('product').order_by('-start_date')[:5]
    
    # Calculate percentages in the view
    for run in active_runs:
        if run.planned_quantity and run.planned_quantity > 0:
            run.progress_percentage = (run.actual_quantity or 0) / run.planned_quantity * 100
            run.progress_percentage_int = int(run.progress_percentage)
        else:
            run.progress_percentage = 0
            run.progress_percentage_int = 0
    
    # Purchasing stats
    pending_pos = PurchaseOrder.objects.filter(status__in=['draft', 'approved', 'ordered']).count()
    received_pos = PurchaseOrder.objects.filter(status='received').count()
    overdue_deliveries = PurchaseOrder.objects.filter(
        expected_delivery_date__lt=today,
        status__in=['ordered', 'partial']
    ).count()
    
    # Sales stats
    monthly_sales = SalesInvoice.objects.filter(
        invoice_date__month=today.month,
        invoice_date__year=today.year,
        status__in=['posted', 'paid']
    ).aggregate(total=Sum('total_amount'))['total'] or 0
    
    pending_orders = SalesOrder.objects.filter(status__in=['confirmed', 'processing']).count()
    overdue_invoices = SalesInvoice.objects.filter(
        due_date__lt=today,
        status__in=['posted', 'partial']
    ).count()
    
    # Total alerts count
    total_alerts = low_stock_items + near_expiry_count + overdue_deliveries + overdue_invoices
    
    # Recent activities (combine recent transactions from different modules)
    recent_activities = []
    
    # Add recent stock transactions
    for trans in recent_transactions[:3]:
        recent_activities.append({
            'description': f"{trans.get_transaction_type_display()} - {trans.item.code}",
            'details': f"{trans.quantity} {trans.item.unit.abbreviation if trans.item.unit else ''}",
            'time': trans.transaction_date,
            'icon': 'arrow-left-right' if trans.transaction_type == 'transfer' else 
                   'box-seam' if trans.transaction_type == 'receipt' else 'box-arrow-right'
        })
    
    # Add recent production runs
    for run in ProductionRun.objects.filter(status='completed').order_by('-end_date')[:3]:
        recent_activities.append({
            'description': f"Production completed - {run.product.code if run.product else 'N/A'}",
            'details': f"{run.actual_quantity or 0} kg produced",
            'time': run.end_date or run.updated_at,
            'icon': 'gear-wide-connected'
        })
    
    # Add recent purchase orders
    for po in PurchaseOrder.objects.filter(status='received').order_by('-updated_at')[:2]:
        recent_activities.append({
            'description': f"PO Received - {po.po_number}",
            'details': f"From {po.supplier.name if po.supplier else 'N/A'}",
            'time': po.updated_at,
            'icon': 'truck'
        })
    
    # Sort by time
    recent_activities.sort(key=lambda x: x['time'], reverse=True)
    recent_activities = recent_activities[:10]
    
    # Format time for display
    for activity in recent_activities:
        time_diff = timezone.now() - activity['time']
        if time_diff.days > 0:
            activity['time_display'] = f"{time_diff.days} days ago"
        elif time_diff.seconds > 3600:
            activity['time_display'] = f"{time_diff.seconds // 3600} hours ago"
        elif time_diff.seconds > 60:
            activity['time_display'] = f"{time_diff.seconds // 60} minutes ago"
        else:
            activity['time_display'] = "just now"
    
    context = {
        'total_items': total_items,
        'items_by_category': items_by_category,
        'total_stock_value': total_stock_value,
        'low_stock_items': low_stock_items,
        'recent_items': recent_items,
        'warehouse_count': warehouse_count,
        'active_lots': active_lots,
        'near_expiry_count': near_expiry_count,
        'recent_transactions': recent_transactions,
        'active_production_runs': active_production_runs,
        'planned_runs': planned_runs,
        'completed_runs': completed_runs,
        'in_progress_runs': in_progress_runs,
        'active_boms': active_boms,
        'active_runs': active_runs,
        'pending_pos': pending_pos,
        'received_pos': received_pos,
        'overdue_deliveries': overdue_deliveries,
        'monthly_sales': monthly_sales,
        'pending_orders': pending_orders,
        'overdue_invoices': overdue_invoices,
        'total_alerts': total_alerts,
        'recent_activities': recent_activities,
        'today': today,
    }
    
    return render(request, 'core/dashboard.html', context)


# ... rest of the core views (item_list, item_detail, etc.) ...

# ============================
# Item Views
# ============================

@login_required
def item_list(request):
    """List all items with filtering and search"""
    items = Item.objects.filter(is_active=True).select_related('unit').order_by('code')
    
    # Search
    search_query = request.GET.get('q', '').strip()
    if search_query:
        items = items.filter(
            Q(code__icontains=search_query) |
            Q(name__icontains=search_query) |
            Q(peach_code__icontains=search_query)
        )
    
    # Filter by category
    category = request.GET.get('category')
    if category:
        items = items.filter(category=category)
    
    # Filter by product type
    product_type = request.GET.get('product_type')
    if product_type:
        items = items.filter(product_type=product_type)
    
    # Filter by stock status
    stock_status = request.GET.get('stock_status')
    if stock_status == 'low':
        items = items.filter(current_stock__lte=models.F('minimum_stock'))
    elif stock_status == 'out':
        items = items.filter(current_stock__lte=0)
    elif stock_status == 'reorder':
        items = items.filter(current_stock__lte=models.F('reorder_point'))
    
    # Pagination
    paginator = Paginator(items, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'categories': Item.ITEM_CATEGORY,
        'product_types': Item.PRODUCT_TYPE,
        'search_query': search_query,
        'selected_category': category,
        'selected_product_type': product_type,
        'selected_stock_status': stock_status,
        'today': timezone.now().date(),
    }
    
    return render(request, 'core/item_list.html', context)


@login_required
def item_detail(request, item_id):
    """View item details with transaction history"""
    item = get_object_or_404(Item.objects.select_related('unit'), id=item_id)
    
    # Get stock transactions
    transactions = StockTransaction.objects.filter(
        item=item
    ).select_related('lot', 'warehouse_to', 'warehouse_from').order_by('-transaction_date')[:50]
    
    # Get current lots
    current_lots = CurrentStock.objects.filter(
        item=item
    ).select_related('lot', 'warehouse').order_by('-quantity')
    
    # Get BOMs where this item is used
    boms_as_component = BOM.objects.filter(
        lines__component=item,
        is_active=True
    ).distinct().select_related('product')
    
    # Get BOMs where this item is the product
    boms_as_product = BOM.objects.filter(
        product=item,
        is_active=True
    )
    
    # Production runs
    production_runs = ProductionRun.objects.filter(
        product=item
    ).order_by('-start_date')[:10]
    
    # Statistics
    total_received = StockTransaction.objects.filter(
        item=item,
        transaction_type='receipt'
    ).aggregate(total=Sum('quantity'))['total'] or 0
    
    total_issued = StockTransaction.objects.filter(
        item=item,
        transaction_type='issue'
    ).aggregate(total=Sum('quantity'))['total'] or 0
    
    context = {
        'item': item,
        'transactions': transactions,
        'current_lots': current_lots,
        'boms_as_component': boms_as_component,
        'boms_as_product': boms_as_product,
        'production_runs': production_runs,
        'total_received': total_received,
        'total_issued': total_issued,
        'today': timezone.now().date(),
    }
    
    return render(request, 'core/item_detail.html', context)


@login_required
@permission_required('core.add_item', raise_exception=True)
def item_create(request):
    """Create a new item"""
    if request.method == 'POST':
        # Process form data
        try:
            item = Item(
                code=request.POST.get('code'),
                peach_code=request.POST.get('peach_code', ''),
                name=request.POST.get('name'),
                category=request.POST.get('category'),
                product_type=request.POST.get('product_type'),
                unit_id=request.POST.get('unit'),
                description=request.POST.get('description', ''),
                shelf_life_days=request.POST.get('shelf_life_days') or None,
                allergen_peanut=request.POST.get('allergen_peanut') == 'on',
                pack_size_kg=request.POST.get('pack_size_kg') or None,
                unit_cost=Decimal(request.POST.get('unit_cost', 0)),
                minimum_stock=Decimal(request.POST.get('minimum_stock', 0)),
                reorder_point=Decimal(request.POST.get('reorder_point', 0)),
                reorder_quantity=Decimal(request.POST.get('reorder_quantity', 0)),
                created_by=request.user,
            )
            item.save()
            messages.success(request, f'Item {item.code} created successfully.')
            return redirect('core:item_detail', item_id=item.id)
        except Exception as e:
            messages.error(request, f'Error creating item: {e}')
    
    units = Unit.objects.filter(is_active=True)
    
    context = {
        'units': units,
        'categories': Item.ITEM_CATEGORY,
        'product_types': Item.PRODUCT_TYPE,
        'today': timezone.now().date(),
    }
    
    return render(request, 'core/item_form.html', context)


@login_required
@permission_required('core.change_item', raise_exception=True)
def item_edit(request, item_id):
    """Edit an existing item"""
    item = get_object_or_404(Item, id=item_id)
    
    if request.method == 'POST':
        try:
            item.code = request.POST.get('code')
            item.peach_code = request.POST.get('peach_code', '')
            item.name = request.POST.get('name')
            item.category = request.POST.get('category')
            item.product_type = request.POST.get('product_type')
            item.unit_id = request.POST.get('unit')
            item.description = request.POST.get('description', '')
            item.shelf_life_days = request.POST.get('shelf_life_days') or None
            item.allergen_peanut = request.POST.get('allergen_peanut') == 'on'
            item.pack_size_kg = request.POST.get('pack_size_kg') or None
            item.unit_cost = Decimal(request.POST.get('unit_cost', 0))
            item.minimum_stock = Decimal(request.POST.get('minimum_stock', 0))
            item.reorder_point = Decimal(request.POST.get('reorder_point', 0))
            item.reorder_quantity = Decimal(request.POST.get('reorder_quantity', 0))
            item.is_active = request.POST.get('is_active') == 'on'
            item.save()
            
            messages.success(request, f'Item {item.code} updated successfully.')
            return redirect('core:item_detail', item_id=item.id)
        except Exception as e:
            messages.error(request, f'Error updating item: {e}')
    
    units = Unit.objects.filter(is_active=True)
    
    context = {
        'item': item,
        'units': units,
        'categories': Item.ITEM_CATEGORY,
        'product_types': Item.PRODUCT_TYPE,
        'today': timezone.now().date(),
    }
    
    return render(request, 'core/item_form.html', context)


@login_required
@permission_required('core.delete_item', raise_exception=True)
def item_delete(request, item_id):
    """Delete an item (soft delete by deactivating)"""
    item = get_object_or_404(Item, id=item_id)
    
    if request.method == 'POST':
        item.is_active = False
        item.save()
        messages.success(request, f'Item {item.code} deactivated successfully.')
        return redirect('core:item_list')
    
    context = {
        'item': item,
    }
    return render(request, 'core/item_confirm_delete.html', context)


# ============================
# Unit Views
# ============================

@login_required
def unit_list(request):
    """List all units"""
    units = Unit.objects.filter(is_active=True).order_by('name')
    
    # Search
    search_query = request.GET.get('q', '').strip()
    if search_query:
        units = units.filter(
            Q(name__icontains=search_query) |
            Q(abbreviation__icontains=search_query)
        )
    
    context = {
        'units': units,
        'search_query': search_query,
        'today': timezone.now().date(),
    }
    
    return render(request, 'core/unit_list.html', context)


@login_required
@permission_required('core.add_unit', raise_exception=True)
def unit_create(request):
    """Create a new unit"""
    if request.method == 'POST':
        try:
            unit = Unit(
                name=request.POST.get('name'),
                abbreviation=request.POST.get('abbreviation'),
                is_active=True
            )
            unit.save()
            messages.success(request, f'Unit {unit.name} created successfully.')
            return redirect('core:unit_list')
        except Exception as e:
            messages.error(request, f'Error creating unit: {e}')
    
    return render(request, 'core/unit_form.html', {'today': timezone.now().date()})


@login_required
@permission_required('core.change_unit', raise_exception=True)
def unit_edit(request, unit_id):
    """Edit an existing unit"""
    unit = get_object_or_404(Unit, id=unit_id)
    
    if request.method == 'POST':
        try:
            unit.name = request.POST.get('name')
            unit.abbreviation = request.POST.get('abbreviation')
            unit.is_active = request.POST.get('is_active') == 'on'
            unit.save()
            messages.success(request, f'Unit {unit.name} updated successfully.')
            return redirect('core:unit_list')
        except Exception as e:
            messages.error(request, f'Error updating unit: {e}')
    
    context = {
        'unit': unit,
        'today': timezone.now().date(),
    }
    return render(request, 'core/unit_form.html', context)


# ============================
# AJAX Views
# ============================

@login_required
def ajax_search_items(request):
    """AJAX endpoint for item search (used in autocomplete)"""
    query = request.GET.get('q', '')
    items = Item.objects.filter(
        Q(code__icontains=query) |
        Q(name__icontains=query)
    ).filter(is_active=True)[:20]
    
    results = []
    for item in items:
        results.append({
            'id': item.id,
            'text': f"{item.code} - {item.name}",
            'code': item.code,
            'name': item.name,
            'unit': item.unit.abbreviation if item.unit else '',
            'current_stock': float(item.current_stock),
        })
    
    return JsonResponse({'results': results})


@login_required
def ajax_item_detail(request, item_id):
    """AJAX endpoint to get item details"""
    item = get_object_or_404(Item, id=item_id)
    
    data = {
        'id': item.id,
        'code': item.code,
        'name': item.name,
        'category': item.get_category_display(),
        'unit': item.unit.abbreviation if item.unit else '',
        'current_stock': float(item.current_stock),
        'unit_cost': float(item.unit_cost),
        'minimum_stock': float(item.minimum_stock),
        'reorder_point': float(item.reorder_point),
        'is_active': item.is_active,
    }
    
    return JsonResponse(data)


# ============================
# Export Views
# ============================

@login_required
def export_items(request):
    """Export items to CSV"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="items_{timezone.now().strftime("%Y%m%d")}.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'Code', 'Name', 'Category', 'Product Type', 'Unit', 
        'Current Stock', 'Unit Cost', 'Stock Value',
        'Minimum Stock', 'Reorder Point', 'Reorder Quantity',
        'Status', 'Created At'
    ])
    
    items = Item.objects.filter(is_active=True).select_related('unit')
    for item in items:
        writer.writerow([
            item.code,
            item.name,
            item.get_category_display(),
            item.get_product_type_display() if item.product_type else '',
            item.unit.abbreviation if item.unit else '',
            float(item.current_stock),
            float(item.unit_cost),
            float(item.stock_value),
            float(item.minimum_stock),
            float(item.reorder_point),
            float(item.reorder_quantity),
            'Active' if item.is_active else 'Inactive',
            item.created_at.strftime('%Y-%m-%d'),
        ])
    
    return response


@login_required
def export_units(request):
    """Export units to CSV"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="units_{timezone.now().strftime("%Y%m%d")}.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Name', 'Abbreviation', 'Status', 'Created At'])
    
    units = Unit.objects.all()
    for unit in units:
        writer.writerow([
            unit.name,
            unit.abbreviation,
            'Active' if unit.is_active else 'Inactive',
            unit.created_at.strftime('%Y-%m-%d'),
        ])
    
    return response


# ============================
# Bulk Operations
# ============================

@login_required
@permission_required('core.change_item', raise_exception=True)
def bulk_item_update(request):
    """Bulk update items (prices, reorder levels, etc.)"""
    if request.method == 'POST':
        action = request.POST.get('action')
        item_ids = request.POST.getlist('item_ids')
        items = Item.objects.filter(id__in=item_ids)
        
        if action == 'update_cost':
            new_cost = Decimal(request.POST.get('new_cost', 0))
            items.update(unit_cost=new_cost)
            messages.success(request, f'Updated cost for {items.count()} items.')
        
        elif action == 'update_reorder':
            multiplier = Decimal(request.POST.get('multiplier', 1.5))
            for item in items:
                item.reorder_point = item.minimum_stock * multiplier
                item.save()
            messages.success(request, f'Updated reorder points for {items.count()} items.')
        
        elif action == 'activate':
            items.update(is_active=True)
            messages.success(request, f'Activated {items.count()} items.')
        
        elif action == 'deactivate':
            items.update(is_active=False)
            messages.success(request, f'Deactivated {items.count()} items.')
        
        return redirect('core:item_list')
    
    # GET - show bulk update form
    item_ids = request.GET.getlist('item_ids')
    items = Item.objects.filter(id__in=item_ids)
    
    context = {
        'items': items,
        'count': items.count(),
    }
    return render(request, 'core/bulk_item_update.html', context)