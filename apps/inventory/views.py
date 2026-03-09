from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Q, F, Count
from django.utils import timezone
from django.http import HttpResponse, JsonResponse
from datetime import timedelta, datetime
from dateutil.relativedelta import relativedelta
from decimal import Decimal
from collections import defaultdict
import json
import csv

from .models import Warehouse, Lot, StockTransaction, CurrentStock
from .resources import (
    ConsumptionReportResource, StockSummaryResource, 
    LowStockResource, StockTransactionResource
)
from apps.production.models import ProductionRun, BOMLine, InventoryMovement
from apps.core.models import Item


# ============================
# Helpers
# ============================

def _company_id(request):
    return request.session.get('current_company_id')


def _scoped(qs, company_id):
    """Scope querysets to current company while still allowing legacy NULL company rows."""
    if not company_id:
        return qs
    return qs.filter(Q(company_id=company_id) | Q(company__isnull=True))


def _ensure_current_stock_seed(company_id):
    """
    Backfill CurrentStock rows for legacy data where beginning balances were saved
    on Item.current_stock but CurrentStock rows were never created.
    """
    existing_qs = _scoped(CurrentStock.objects.all(), company_id)
    if existing_qs.exists():
        return

    # 1) Try seed from item-level beginning balances.
    item_qs = Item.objects.filter(is_active=True, current_stock__gt=0)
    if company_id:
        item_qs = item_qs.filter(Q(company_id=company_id) | Q(company__isnull=True))

    wh_qs = Warehouse.objects.filter(is_active=True)
    if company_id:
        wh_qs = wh_qs.filter(Q(company_id=company_id) | Q(company__isnull=True))
    warehouse = wh_qs.order_by('id').first()

    if not warehouse:
        warehouse = Warehouse.objects.create(
            name='Main Warehouse',
            code=f"MAIN-{company_id or 'GEN'}",
            warehouse_type='raw',
            is_active=True,
            company_id=company_id
        )

    for item in item_qs:
        CurrentStock.objects.create(
            item=item,
            warehouse=warehouse,
            lot=None,
            quantity=item.current_stock,
            company_id=item.company_id or company_id
        )

    if _scoped(CurrentStock.objects.all(), company_id).exists():
        return

    # 2) Fallback: derive balances from historical stock transactions.
    tx_qs = _scoped(
        StockTransaction.objects.select_related('item', 'warehouse_from', 'warehouse_to', 'lot').order_by('transaction_date', 'id'),
        company_id
    )
    if not tx_qs.exists():
        return

    balances = defaultdict(lambda: Decimal('0'))
    for tx in tx_qs:
        qty = tx.quantity or Decimal('0')
        if qty == 0:
            continue

        if tx.transaction_type in ['receipt', 'return'] and tx.warehouse_to:
            balances[(tx.item_id, tx.warehouse_to_id, tx.lot_id)] += qty
        elif tx.transaction_type in ['issue', 'scrap', 'adjustment', 'return_supplier', 'sample'] and tx.warehouse_from:
            balances[(tx.item_id, tx.warehouse_from_id, tx.lot_id)] -= qty
        elif tx.transaction_type == 'transfer':
            if tx.warehouse_from:
                balances[(tx.item_id, tx.warehouse_from_id, tx.lot_id)] -= qty
            if tx.warehouse_to:
                balances[(tx.item_id, tx.warehouse_to_id, tx.lot_id)] += qty

    for (item_id, warehouse_id, lot_id), qty in balances.items():
        if qty == 0 or not warehouse_id:
            continue
        CurrentStock.objects.create(
            item_id=item_id,
            warehouse_id=warehouse_id,
            lot_id=lot_id,
            quantity=qty,
            company_id=company_id
        )


# ============================
# Dashboard Views
# ============================

@login_required
def dashboard(request):
    """Main inventory dashboard"""
    today = timezone.now().date()
    company_id = _company_id(request)
    _ensure_current_stock_seed(company_id)
    current_stock_qs = _scoped(CurrentStock.objects.all(), company_id)
    warehouse_qs = _scoped(Warehouse.objects.filter(is_active=True), company_id)
    lot_qs = _scoped(Lot.objects.filter(is_active=True), company_id)
    tx_qs = _scoped(StockTransaction.objects.all(), company_id)
    item_qs = _scoped(Item.objects.filter(is_active=True), company_id)
    
    # Calculate key metrics
    total_stock_value = current_stock_qs.aggregate(
        total=Sum(F('quantity') * F('item__unit_cost'))
    )['total'] or 0
    
    low_stock_count = current_stock_qs.filter(
        Q(quantity__lt=F('item__minimum_stock')) |
        Q(quantity__lte=F('item__reorder_point'))
    ).count()
    
    # Stock by warehouse
    stock_by_warehouse = current_stock_qs.values(
        'warehouse__name', 'warehouse__code'
    ).annotate(
        total_qty=Sum('quantity'),
        total_value=Sum(F('quantity') * F('item__unit_cost'))
    ).order_by('-total_value')[:5]
    
    context = {
        'warehouse_count': warehouse_qs.count(),
        'active_lots': lot_qs.count(),
        'recent_transactions': tx_qs[:10],
        'total_stock_value': total_stock_value,
        'total_items': item_qs.count(),
        'total_low_items': low_stock_count,
        'stock_by_warehouse': stock_by_warehouse,
        'today': today,
    }
    return render(request, 'inventory/dashboard.html', context)


# ============================
# Warehouse Views
# ============================

@login_required
def warehouse_list(request):
    """List all warehouses"""
    warehouses = Warehouse.objects.filter(is_active=True).order_by('name')
    
    # Add stock counts
    for warehouse in warehouses:
        warehouse.stock_count = warehouse.current_stock.count()
        warehouse.stock_value = warehouse.current_stock.aggregate(
            total=Sum(F('quantity') * F('item__unit_cost'))
        )['total'] or 0
    
    context = {
        'warehouses': warehouses,
        'today': timezone.now().date(),
    }
    return render(request, 'inventory/warehouse_list.html', context)


@login_required
def warehouse_detail(request, warehouse_id):
    """View warehouse details"""
    warehouse = get_object_or_404(Warehouse, id=warehouse_id)
    
    # Get stock in this warehouse
    stock_items = CurrentStock.objects.filter(
        warehouse=warehouse
    ).select_related('item', 'lot').order_by('item__code')
    
    # Get recent transactions
    transactions = StockTransaction.objects.filter(
        Q(warehouse_from=warehouse) | Q(warehouse_to=warehouse)
    ).select_related('item', 'lot').order_by('-transaction_date')[:50]
    
    context = {
        'warehouse': warehouse,
        'stock_items': stock_items,
        'transactions': transactions,
        'today': timezone.now().date(),
    }
    return render(request, 'inventory/warehouse_detail.html', context)


# ============================
# Lot Views
# ============================

@login_required
def lot_list(request):
    """List all lots/batches with filters"""
    lots = Lot.objects.filter(is_active=True).select_related('item', 'supplier').order_by('-expiry_date')
    
    # Filter by item
    item_id = request.GET.get('item')
    if item_id:
        lots = lots.filter(item_id=item_id)
    
    # Filter by status
    status = request.GET.get('status')
    if status == 'expired':
        lots = lots.filter(expiry_date__lt=timezone.now().date())
    elif status == 'near_expiry':
        lots = lots.filter(
            expiry_date__lte=timezone.now().date() + timedelta(days=90),
            expiry_date__gte=timezone.now().date()
        )
    elif status == 'active':
        lots = lots.filter(expiry_date__gte=timezone.now().date())
    
    context = {
        'lots': lots,
        'items': Item.objects.filter(is_active=True),
        'today': timezone.now().date(),
    }
    return render(request, 'inventory/lot_list.html', context)


@login_required
def lot_detail(request, lot_id):
    """View lot details"""
    lot = get_object_or_404(
        Lot.objects.select_related('item', 'supplier', 'created_by'),
        id=lot_id
    )
    
    # Get transactions for this lot
    transactions = StockTransaction.objects.filter(
        lot=lot
    ).select_related('warehouse_from', 'warehouse_to', 'created_by').order_by('-transaction_date')
    
    # Get current stock
    current_stock = CurrentStock.objects.filter(lot=lot).select_related('warehouse')
    
    context = {
        'lot': lot,
        'transactions': transactions,
        'current_stock': current_stock,
        'today': timezone.now().date(),
    }
    return render(request, 'inventory/lot_detail.html', context)


# ============================
# Transaction Views
# ============================

@login_required
def transaction_list(request):
    """List all stock transactions with filters"""
    transactions = StockTransaction.objects.select_related(
        'item', 'lot', 'warehouse_from', 'warehouse_to', 'production_run', 'created_by'
    ).order_by('-transaction_date')
    
    # Filter by date range
    from_date = request.GET.get('from')
    to_date = request.GET.get('to')
    if from_date and to_date:
        try:
            from_date = datetime.strptime(from_date, '%Y-%m-%d').date()
            to_date = datetime.strptime(to_date, '%Y-%m-%d').date()
            transactions = transactions.filter(transaction_date__date__range=[from_date, to_date])
        except:
            pass
    
    # Filter by type
    t_type = request.GET.get('type')
    if t_type:
        transactions = transactions.filter(transaction_type=t_type)
    
    # Filter by item
    item_id = request.GET.get('item')
    if item_id:
        transactions = transactions.filter(item_id=item_id)
    
    context = {
        'transactions': transactions,
        'transaction_types': StockTransaction.TYPE_CHOICES,
        'items': Item.objects.filter(is_active=True),
        'today': timezone.now().date(),
    }
    return render(request, 'inventory/transaction_list.html', context)


@login_required
def transaction_detail(request, transaction_id):
    """View transaction details"""
    transaction = get_object_or_404(
        StockTransaction.objects.select_related(
            'item', 'lot', 'warehouse_from', 'warehouse_to', 'production_run', 'created_by'
        ),
        id=transaction_id
    )
    
    context = {
        'transaction': transaction,
        'today': timezone.now().date(),
    }
    return render(request, 'inventory/transaction_detail.html', context)


# ============================
# Current Stock Views
# ============================

@login_required
def current_stock(request):
    """View current stock levels with filters"""
    company_id = _company_id(request)
    _ensure_current_stock_seed(company_id)
    stock_items = _scoped(CurrentStock.objects.select_related(
        'item', 'warehouse', 'lot', 'item__unit'
    ).all(), company_id).order_by('item__code', 'warehouse__name')
    
    # Filter by warehouse
    warehouse_id = request.GET.get('warehouse')
    if warehouse_id:
        stock_items = stock_items.filter(warehouse_id=warehouse_id)
    
    # Filter by item category
    category = request.GET.get('category')
    if category:
        stock_items = stock_items.filter(item__category=category)
    
    # Filter by stock status
    status = request.GET.get('status')
    if status == 'low':
        stock_items = stock_items.filter(quantity__lt=F('item__minimum_stock'))
    elif status == 'out':
        stock_items = stock_items.filter(quantity=0)
    elif status == 'reorder':
        stock_items = stock_items.filter(quantity__lte=F('item__reorder_point'))
    
    # Calculate totals
    total_value = stock_items.aggregate(
        total=Sum(F('quantity') * F('item__unit_cost'))
    )['total'] or 0
    
    context = {
        'stock_items': stock_items,
        'warehouses': _scoped(Warehouse.objects.filter(is_active=True), company_id),
        'categories': Item.ITEM_CATEGORY,
        'total_value': total_value,
        'today': timezone.now().date(),
    }
    return render(request, 'inventory/current_stock.html', context)


# ============================
# Report Views
# ============================

@login_required
def stock_summary(request):
    """Stock summary report with totals by item and expiry information"""
    company_id = _company_id(request)
    _ensure_current_stock_seed(company_id)
    current_stock_qs = _scoped(CurrentStock.objects.all(), company_id)
    lot_qs = _scoped(Lot.objects.filter(is_active=True), company_id)

    # All current stock grouped by item
    stock_by_item = (
        current_stock_qs
        .values('item__code', 'item__name', 'item__unit__abbreviation', 'item__category')
        .annotate(
            total_qty=Sum('quantity'),
            total_value=Sum(F('quantity') * F('item__unit_cost'))
        )
        .order_by('item__code')
    )

    # Near expiry (90 days or less) and expired
    today = timezone.now().date()
    near_expiry_lots = lot_qs.filter(
        expiry_date__lte=today + timedelta(days=90),
        expiry_date__gte=today
    ).select_related('item').order_by('expiry_date')

    expired_lots = lot_qs.filter(expiry_date__lt=today).select_related('item').order_by('expiry_date')
    
    # Stock by warehouse
    stock_by_warehouse = current_stock_qs.values(
        'warehouse__name', 'warehouse__code'
    ).annotate(
        total_qty=Sum('quantity'),
        total_value=Sum(F('quantity') * F('item__unit_cost'))
    ).order_by('-total_value')
    
    # Handle export
    if request.GET.get('export') == 'excel':
        resource = StockSummaryResource()
        dataset = resource.export(current_stock_qs.select_related('item', 'warehouse', 'lot'))
        
        response = HttpResponse(
            dataset.xlsx,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="stock_summary_{today.strftime("%Y%m%d")}.xlsx"'
        return response

    context = {
        'stock_by_item': stock_by_item,
        'near_expiry_lots': near_expiry_lots,
        'expired_lots': expired_lots,
        'stock_by_warehouse': stock_by_warehouse,
        'today': today,
    }
    return render(request, 'inventory/stock_summary.html', context)


@login_required
def consumption_vs_bom(request):
    """
    Report comparing actual consumption vs BOM standard consumption
    for completed production runs within a date range.
    """
    company_id = _company_id(request)

    # Default: last 30 days
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=30)

    # Optional filters from GET params
    requested_product = (request.GET.get('product') or '').strip()
    date_from = request.GET.get('from', start_date.strftime('%Y-%m-%d'))
    date_to = request.GET.get('to', end_date.strftime('%Y-%m-%d'))

    try:
        start_date = datetime.strptime(date_from, '%Y-%m-%d').date()
        end_date = datetime.strptime(date_to, '%Y-%m-%d').date()
    except ValueError:
        pass

    # Build selectable finished products from DB (not hardcoded codes)
    product_choices = _scoped(
        Item.objects.filter(category='finished', is_active=True).order_by('name', 'code'),
        company_id
    )

    # Resolve product by id or code (case-insensitive), then fallback to first finished product
    product_item = None
    if requested_product:
        if requested_product.isdigit():
            product_item = product_choices.filter(id=int(requested_product)).first()
        if not product_item:
            product_item = product_choices.filter(code__iexact=requested_product).first()
        if not product_item:
            product_item = product_choices.filter(name__iexact=requested_product).first()
    if not product_item:
        product_item = product_choices.first()

    if not product_item:
        return render(request, 'inventory/consumption_vs_bom.html', {
            'error': 'No finished products found.',
            'no_data': True,
            'report_rows': [],
            'product_choices': product_choices,
            'selected_product': requested_product,
            'period_from': start_date,
            'period_to': end_date,
            'total_produced_kg': Decimal('0.00'),
            'total_expected': Decimal('0.00'),
            'total_actual': Decimal('0.00'),
            'total_variance_qty': Decimal('0.00'),
            'total_variance_pct': Decimal('0.00'),
            'bom_version': '',
        })

    # Use product code as stable selected value for template
    selected_product = product_item.code

    # Filter production runs by status + product + date range.
    # Some completed runs may not have end_date set, so fallback to start_date.
    production_runs = _scoped(
        ProductionRun.objects.filter(status='completed'),
        company_id
    ).filter(
        Q(product=product_item) | Q(bom__product=product_item)
    ).filter(
        Q(end_date__date__range=[start_date, end_date]) |
        Q(end_date__isnull=True, start_date__date__range=[start_date, end_date])
    )

    total_produced_kg = production_runs.aggregate(total=Sum('actual_quantity'))['total'] or Decimal('0')

    # Get active BOMs by type (raw/formula + packing)
    formula_bom = product_item.boms.filter(is_active=True, bom_type='formula').order_by('-version').first()
    packing_bom = product_item.boms.filter(is_active=True, bom_type='packing').order_by('-version').first()
    active_boms = [b for b in [formula_bom, packing_bom] if b]

    if not active_boms:
        return render(request, 'inventory/consumption_vs_bom.html', {
            'error': f'No active BOM found for {product_item.code}.',
            'no_data': True,
            'product': product_item,
            'product_choices': product_choices,
            'selected_product': selected_product,
            'period_from': start_date,
            'period_to': end_date,
            'report_rows': [],
            'total_produced_kg': Decimal('0.00'),
            'total_expected': Decimal('0.00'),
            'total_actual': Decimal('0.00'),
            'total_variance_qty': Decimal('0.00'),
            'total_variance_pct': Decimal('0.00'),
            'bom_version': '',
        })

    # Build report rows
    report_rows = []
    for bom in active_boms:
        for line in bom.lines.select_related('component', 'component__unit').all():
            component = line.component

            # Theoretical / standard consumption (incl. wastage)
            std_qty_per_kg = line.quantity_per_kg * (Decimal('1') + line.wastage_percentage / Decimal('100'))
            expected_total = total_produced_kg * std_qty_per_kg

            # Actual issued quantity from stock transactions
            actual_issued_tx = _scoped(StockTransaction.objects.filter(
                item=component,
                transaction_type='issue',
                production_run__in=production_runs
            ), company_id).aggregate(total=Sum('quantity'))['total'] or Decimal('0')

            # Fallback to production movements if transaction-based issue is empty
            # Production completion currently logs 'out_production' as negative quantities.
            actual_issued_mv = _scoped(InventoryMovement.objects.filter(
                item=component,
                movement_type='out_production',
                production_run__in=production_runs
            ), company_id).aggregate(total=Sum('quantity'))['total'] or Decimal('0')
            actual_issued_mv = abs(actual_issued_mv)

            actual_issued = actual_issued_tx if actual_issued_tx > 0 else actual_issued_mv

            variance_qty = actual_issued - expected_total
            variance_pct = (variance_qty / expected_total * 100) if expected_total > 0 else Decimal('0')

            report_rows.append({
                'bom_type': bom.bom_type,
                'component_code': component.code,
                'component_name': component.name,
                'unit': component.unit.abbreviation,
                'std_qty_per_kg': line.quantity_per_kg,
                'wastage_pct': line.wastage_percentage,
                'expected_total': expected_total.quantize(Decimal('0.00')),
                'actual_issued': actual_issued.quantize(Decimal('0.00')),
                'variance_qty': variance_qty.quantize(Decimal('0.00')),
                'variance_pct': variance_pct.quantize(Decimal('0.00')),
            })

    # Calculate totals
    total_expected = sum(row['expected_total'] for row in report_rows) if report_rows else Decimal('0')
    total_actual = sum(row['actual_issued'] for row in report_rows) if report_rows else Decimal('0')
    total_variance_qty = sum(row['variance_qty'] for row in report_rows) if report_rows else Decimal('0')
    total_variance_pct = (total_variance_qty / total_expected * 100) if total_expected > 0 else Decimal('0')

    export_format = request.GET.get('export')

    # Handle Excel export
    if export_format == 'excel':
        resource = ConsumptionReportResource()
        
        dataset = resource.export(
            report_rows,
            product_name=product_item.name,
            total_produced_kg=float(total_produced_kg),
            period_from=start_date.strftime('%d %b %Y'),
            period_to=end_date.strftime('%d %b %Y')
        )
        
        response = HttpResponse(
            dataset.xlsx,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        
        filename = f"consumption_vs_bom_{product_item.code}_{timezone.now().strftime('%Y%m%d_%H%M')}.xlsx"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    # Handle PDF export (server-side, no browser JS dependency)
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
        filename = f"consumption_vs_bom_{product_item.code}_{timezone.now().strftime('%Y%m%d_%H%M')}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        page_size = landscape(A4)
        pdf = canvas.Canvas(response, pagesize=page_size)
        width, height = page_size

        # Header
        y = height - 35
        pdf.setFont("Helvetica-Bold", 14)
        pdf.drawString(30, y, "Consumption vs BOM Standard Report")
        y -= 18
        pdf.setFont("Helvetica", 10)
        pdf.drawString(30, y, f"Product: {product_item.name} ({product_item.code})")
        y -= 14
        pdf.drawString(30, y, f"Period: {start_date.strftime('%d %b %Y')} - {end_date.strftime('%d %b %Y')}")
        y -= 14
        pdf.drawString(30, y, f"BOM Version: {' + '.join([f'{b.get_bom_type_display()} v{b.version}' for b in active_boms])}")
        y -= 14
        pdf.drawString(30, y, f"Total Production: {total_produced_kg.quantize(Decimal('0.00'))} kg")
        y -= 20

        # Table header
        headers = ["Type", "Component", "Std/kg", "Wast%", "Expected", "Actual", "Var(kg)", "Var(%)"]
        col_x = [30, 95, 290, 350, 410, 485, 560, 640]
        pdf.setFont("Helvetica-Bold", 9)
        for i, h in enumerate(headers):
            pdf.drawString(col_x[i], y, h)
        y -= 12
        pdf.line(25, y + 8, width - 25, y + 8)
        pdf.setFont("Helvetica", 8)

        # Table rows
        for row in report_rows:
            if y < 40:
                pdf.showPage()
                y = height - 35
                pdf.setFont("Helvetica-Bold", 9)
                for i, h in enumerate(headers):
                    pdf.drawString(col_x[i], y, h)
                y -= 12
                pdf.line(25, y + 8, width - 25, y + 8)
                pdf.setFont("Helvetica", 8)

            row_type = "Raw" if row.get('bom_type') == 'formula' else "Packing"
            pdf.drawString(col_x[0], y, row_type)
            pdf.drawString(col_x[1], y, f"{row['component_code']} {row['component_name'][:28]}")
            pdf.drawRightString(col_x[3] - 6, y, f"{row['std_qty_per_kg']:.6f}")
            pdf.drawRightString(col_x[4] - 6, y, f"{row['wastage_pct']:.1f}")
            pdf.drawRightString(col_x[5] - 6, y, f"{row['expected_total']:.2f}")
            pdf.drawRightString(col_x[6] - 6, y, f"{row['actual_issued']:.2f}")
            pdf.drawRightString(col_x[7] - 6, y, f"{row['variance_qty']:.2f}")
            pdf.drawRightString(width - 30, y, f"{row['variance_pct']:.1f}")
            y -= 11

        # Totals
        y -= 5
        pdf.line(25, y + 8, width - 25, y + 8)
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(30, y - 3, "TOTAL")
        pdf.drawRightString(col_x[5] - 6, y - 3, f"{total_expected.quantize(Decimal('0.00'))}")
        pdf.drawRightString(col_x[6] - 6, y - 3, f"{total_actual.quantize(Decimal('0.00'))}")
        pdf.drawRightString(col_x[7] - 6, y - 3, f"{total_variance_qty.quantize(Decimal('0.00'))}")
        pdf.drawRightString(width - 30, y - 3, f"{total_variance_pct.quantize(Decimal('0.00'))}")

        pdf.showPage()
        pdf.save()
        return response

    context = {
        'product': product_item,
        'selected_product': selected_product,
        'product_choices': product_choices,
        'total_produced_kg': total_produced_kg.quantize(Decimal('0.00')),
        'period_from': start_date,
        'period_to': end_date,
        'report_rows': report_rows,
        'bom_version': " + ".join([f"{b.get_bom_type_display()} v{b.version}" for b in active_boms]),
        'no_data': total_produced_kg == 0,
        'total_expected': total_expected.quantize(Decimal('0.00')),
        'total_actual': total_actual.quantize(Decimal('0.00')),
        'total_variance_qty': total_variance_qty.quantize(Decimal('0.00')),
        'total_variance_pct': total_variance_pct.quantize(Decimal('0.00')),
    }

    return render(request, 'inventory/consumption_vs_bom.html', context)


@login_required
def low_stock_alerts(request):
    """View for low stock and reorder alerts"""
    company_id = _company_id(request)
    _ensure_current_stock_seed(company_id)
    low_stock_items = _scoped(CurrentStock.objects.select_related('item', 'warehouse', 'lot'), company_id).filter(
        Q(quantity__lt=F('item__minimum_stock')) |
        Q(quantity__lte=F('item__reorder_point'))
    ).order_by('item__code', 'warehouse__name')

    # Summary stats
    total_low_items = low_stock_items.count()
    critical = low_stock_items.filter(quantity__lt=F('item__minimum_stock')).count()
    reorder_needed = low_stock_items.filter(
        quantity__lte=F('item__reorder_point'),
        quantity__gte=F('item__minimum_stock')
    ).count()
    
    # Handle export
    if request.GET.get('export') == 'excel':
        resource = LowStockResource()
        dataset = resource.export(low_stock_items)
        
        response = HttpResponse(
            dataset.xlsx,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="low_stock_alerts_{timezone.now().strftime("%Y%m%d")}.xlsx"'
        return response

    context = {
        'low_stock_items': low_stock_items,
        'total_low_items': total_low_items,
        'critical': critical,
        'reorder_needed': reorder_needed,
        'today': timezone.now().date(),
    }
    return render(request, 'inventory/low_stock_alerts.html', context)


@login_required
def low_stock_widget(request):
    """
    Returns data for low stock summary widget (can be used in dashboard or standalone)
    """
    low_stock_qs = CurrentStock.objects.select_related(
        'item', 'warehouse', 'lot'
    ).filter(
        Q(quantity__lte=F('item__reorder_point')) |
        Q(quantity__lt=F('item__minimum_stock'))
    ).order_by('item__code', '-quantity')

    total_alerts = low_stock_qs.count()
    critical_count = low_stock_qs.filter(quantity__lt=F('item__minimum_stock')).count()
    reorder_count = low_stock_qs.filter(
        quantity__lte=F('item__reorder_point'),
        quantity__gte=F('item__minimum_stock')
    ).count()

    critical_items = low_stock_qs[:10]

    context = {
        'total_alerts': total_alerts,
        'critical_count': critical_count,
        'reorder_count': reorder_count,
        'critical_items': critical_items,
        'today': timezone.now().date(),
    }

    return render(request, 'inventory/low_stock_widget.html', context)


@login_required
def inventory_analytics(request):
    """Inventory analytics dashboard with charts"""
    today = timezone.now().date()
    company_id = _company_id(request)
    _ensure_current_stock_seed(company_id)
    current_stock_qs = _scoped(CurrentStock.objects.all(), company_id)
    lot_qs = _scoped(Lot.objects.filter(is_active=True), company_id)
    
    # Total stock value
    total_stock_value = current_stock_qs.aggregate(
        total=Sum(F('quantity') * F('item__unit_cost'))
    )['total'] or 0
    
    # Stock by category
    stock_by_category = current_stock_qs.values(
        'item__category'
    ).annotate(
        total_qty=Sum('quantity'),
        total_value=Sum(F('quantity') * F('item__unit_cost'))
    ).order_by('item__category')
    
    # Near expiry lots
    near_expiry = lot_qs.filter(
        expiry_date__lte=today + timedelta(days=90),
        expiry_date__gte=today
    ).select_related('item').order_by('expiry_date')[:10]
    
    # Low stock alerts count
    low_stock_count = current_stock_qs.filter(
        Q(quantity__lt=F('item__minimum_stock')) |
        Q(quantity__lte=F('item__reorder_point'))
    ).count()
    
    # Top warehouses by value
    top_warehouses = current_stock_qs.values(
        'warehouse__name'
    ).annotate(
        total_value=Sum(F('quantity') * F('item__unit_cost'))
    ).order_by('-total_value')[:5]
    
    # Prepare data for Chart.js
    category_labels = [cat['item__category'].title() for cat in stock_by_category]
    category_values = [float(cat['total_value'] or 0) for cat in stock_by_category]
    
    context = {
        'total_stock_value': total_stock_value,
        'stock_by_category': stock_by_category,
        'near_expiry': near_expiry,
        'expired_count': lot_qs.filter(expiry_date__lt=today).count(),
        'low_stock_count': low_stock_count,
        'top_warehouses': top_warehouses,
        'today': today,
        'category_labels_json': json.dumps(category_labels),
        'category_values_json': json.dumps(category_values),
    }
    
    return render(request, 'inventory/analytics_dashboard.html', context)


@login_required
def inventory_trends(request):
    """
    Inventory trends dashboard showing monthly inventory value,
    consumption of key raw materials, and production output over time.
    """
    today = timezone.now().date()
    months_back = 24

    # Generate month labels
    labels = []
    start_date = today - relativedelta(months=months_back-1)
    current = start_date
    while current <= today:
        labels.append(current.strftime("%Y-%m"))
        current += relativedelta(months=1)

    # Monthly inventory value
    monthly_inventory_value = []
    monthly_total_qty = []
    
    current_value = CurrentStock.objects.aggregate(
        total=Sum(F('quantity') * F('item__unit_cost'))
    )['total'] or 0
    current_qty = CurrentStock.objects.aggregate(total=Sum('quantity'))['total'] or 0
    
    monthly_inventory_value = [float(current_value)] * len(labels)
    monthly_total_qty = [float(current_qty)] * len(labels)

    # Monthly consumption of key raw materials
    key_raw_codes = ['RAW-GRNDPEANUT', 'RAW-SUGAR', 'RAW-PALMOIL']
    monthly_consumption = {code: [0] * len(labels) for code in key_raw_codes}

    issues = StockTransaction.objects.filter(
        transaction_type='issue',
        transaction_date__date__gte=start_date,
        item__code__in=key_raw_codes
    ).values('item__code', 'transaction_date__year', 'transaction_date__month').annotate(
        total_qty=Sum('quantity')
    )

    for issue in issues:
        code = issue['item__code']
        year = issue['transaction_date__year']
        month = issue['transaction_date__month']
        label = f"{year}-{month:02d}"
        if label in labels:
            idx = labels.index(label)
            monthly_consumption[code][idx] = float(issue['total_qty'])

    # Monthly production output
    monthly_production = [0] * len(labels)

    production = ProductionRun.objects.filter(
        status='completed',
        end_date__date__gte=start_date,
        product__product_type__in=['plumpy_nut', 'plumpy_sup']
    ).values('end_date__year', 'end_date__month').annotate(
        total_produced=Sum('actual_quantity')
    )

    for prod in production:
        year = prod['end_date__year']
        month = prod['end_date__month']
        label = f"{year}-{month:02d}"
        if label in labels:
            idx = labels.index(label)
            monthly_production[idx] = float(prod['total_produced'] or 0)

    context = {
        'labels_json': json.dumps(labels),
        'inventory_value_json': json.dumps(monthly_inventory_value),
        'total_qty_json': json.dumps(monthly_total_qty),
        'production_json': json.dumps(monthly_production),
        'consumption_ground_peanut_json': json.dumps(monthly_consumption['RAW-GRNDPEANUT']),
        'consumption_sugar_json': json.dumps(monthly_consumption['RAW-SUGAR']),
        'consumption_palm_oil_json': json.dumps(monthly_consumption['RAW-PALMOIL']),
        'months_back': months_back,
        'today': today,
    }

    return render(request, 'inventory/trends_dashboard.html', context)


# ============================
# Export Views
# ============================

@login_required
def export_transactions(request):
    """Export stock transactions to Excel"""
    transactions = StockTransaction.objects.select_related(
        'item', 'lot', 'warehouse_from', 'warehouse_to', 'production_run', 'created_by'
    ).all()
    
    # Apply filters from request
    from_date = request.GET.get('from')
    to_date = request.GET.get('to')
    if from_date and to_date:
        try:
            from_date = datetime.strptime(from_date, '%Y-%m-%d').date()
            to_date = datetime.strptime(to_date, '%Y-%m-%d').date()
            transactions = transactions.filter(transaction_date__date__range=[from_date, to_date])
        except:
            pass
    
    t_type = request.GET.get('type')
    if t_type:
        transactions = transactions.filter(transaction_type=t_type)
    
    resource = StockTransactionResource()
    dataset = resource.export(transactions)
    
    response = HttpResponse(
        dataset.xlsx,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="transactions_{timezone.now().strftime("%Y%m%d")}.xlsx"'
    return response


# ============================
# AJAX Views
# ============================

@login_required
def ajax_lot_info(request, lot_id):
    """AJAX endpoint to get lot information"""
    lot = get_object_or_404(Lot, id=lot_id)
    
    data = {
        'id': lot.id,
        'batch_number': lot.batch_number,
        'item_code': lot.item.code,
        'item_name': lot.item.name,
        'current_quantity': float(lot.current_quantity),
        'expiry_date': lot.expiry_date.strftime('%Y-%m-%d'),
        'days_to_expire': lot.days_to_expire,
        'quality_status': lot.quality_status,
    }
    
    return JsonResponse(data)


@login_required
def ajax_warehouse_stock(request, warehouse_id):
    """AJAX endpoint to get warehouse stock summary"""
    stock = CurrentStock.objects.filter(
        warehouse_id=warehouse_id
    ).select_related('item', 'lot').values(
        'item__code', 'item__name', 'lot__batch_number', 'quantity'
    )[:50]
    
    return JsonResponse(list(stock), safe=False)
