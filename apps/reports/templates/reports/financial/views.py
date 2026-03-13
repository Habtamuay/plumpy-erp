from django.shortcuts import render
from django.http import JsonResponse
from django.db.models import Sum, Count, F, DecimalField
from django.utils import timezone
from datetime import timedelta

# Try importing models safely to avoid crashes if apps are not yet loaded
try:
    from apps.sales.models import SalesInvoice, SalesInvoiceLine
except ImportError:
    SalesInvoice = None
    SalesInvoiceLine = None

try:
    from apps.inventory.models import Item
except ImportError:
    Item = None

# ============================
# API ENDPOINTS
# ============================

def api_revenue_trend(request):
    """API endpoint for revenue trend chart"""
    today = timezone.now().date()
    days = 30
    
    labels = []
    values = []
    
    if SalesInvoice:
        for i in range(days):
            date = today - timedelta(days=days-i-1)
            labels.append(date.strftime('%b %d'))
            
            # Get revenue for this date
            revenue = SalesInvoice.objects.filter(
                invoice_date=date,
                status__in=['posted', 'paid']
            ).aggregate(total=Sum('total_amount'))['total'] or 0
            
            values.append(float(revenue))
    else:
        # Return empty data if model not found
        labels = [(today - timedelta(days=i)).strftime('%b %d') for i in reversed(range(days))]
        values = [0] * days
    
    return JsonResponse({
        'labels': labels,
        'values': values
    })

def api_sales_by_product(request):
    """API endpoint for sales by product chart"""
    labels = []
    values = []
    
    if SalesInvoiceLine:
        # Get top 5 products by sales
        top_products = SalesInvoiceLine.objects.filter(
            invoice__status__in=['posted', 'paid']
        ).values(
            'item__name'
        ).annotate(
            total=Sum(
                F('quantity') * F('unit_price'),
                output_field=DecimalField()
            )
        ).order_by('-total')[:5]
        
        labels = [p['item__name'] for p in top_products]
        values = [float(p['total']) for p in top_products]
    
    return JsonResponse({
        'labels': labels,
        'values': values
    })

def api_inventory_by_category(request):
    """API endpoint for inventory by category chart"""
    labels = []
    values = []
    
    if Item:
        # Get inventory value by category
        categories = Item.objects.filter(
            is_active=True,
            current_stock__gt=0
        ).values(
            'category__name'
        ).annotate(
            total=Sum('current_stock_value')
        ).order_by('-total')[:5]
        
        labels = [c['category__name'] or 'Uncategorized' for c in categories]
        values = [float(c['total']) for c in categories]
    
    return JsonResponse({
        'labels': labels,
        'values': values
    })

# ============================
# FINANCIAL REPORTS
# ============================
def balance_sheet_report(request):
    """Balance Sheet"""
    context = {
        'today': timezone.now().date(),
        'assets_by_category': {},
        'liabilities_by_category': {},
        'equity': [],
        'total_assets': 0,
        'total_liabilities': 0,
        'total_equity': 0,
    }
    return render(request, 'reports/financial/balance_sheet.html', context)

def profit_loss_report(request):
    """Profit & Loss Statement"""
    # Template seems to have static data or self-contained logic for now
    return render(request, 'reports/financial/profit_loss.html')

def cash_flow_report(request):
    """Cash Flow Statement"""
    context = {
        'date_from': timezone.now().date() - timedelta(days=30),
        'date_to': timezone.now().date(),
        'operating_net': 0,
        'investing_net': 0,
        'financing_net': 0,
        'net_cash_flow': 0,
        'operating_flows': [],
        'investing_flows': [],
        'financing_flows': [],
    }
    return render(request, 'reports/financial/cash_flow.html', context)

def trial_balance_report(request):
    """Trial Balance"""
    context = {
        'accounts': [],
        'total_debits': 0,
        'total_credits': 0,
        'difference': 0,
        'is_balanced': True,
    }
    return render(request, 'reports/financial/trial_balance.html', context)

def general_ledger(request):
    """General Ledger"""
    context = {
        'ledger_data': [],
    }
    return render(request, 'reports/financial/general_ledger.html', context)

def sales_journal(request):
    """Sales Journal"""
    context = {
        'sales': [],
        'total_sales': 0,
        'date_from': timezone.now().date() - timedelta(days=30),
        'date_to': timezone.now().date(),
    }
    return render(request, 'reports/financial/sales_journal.html', context)

def purchase_journal(request):
    """Purchase Journal"""
    context = {
        'purchases': [],
        'total_purchases': 0,
        'date_from': timezone.now().date() - timedelta(days=30),
        'date_to': timezone.now().date(),
    }
    return render(request, 'reports/financial/purchase_journal.html', context)

def cash_payment_journal(request):
    """Cash Payment Journal"""
    context = {
        'payments': [],
        'total_payments': 0,
        'date_from': timezone.now().date() - timedelta(days=30),
        'date_to': timezone.now().date(),
    }
    return render(request, 'reports/financial/cash_payment_journal.html', context)

def receipt_journal(request):
    """Receipt Journal"""
    context = {
        'receipts': [],
        'total_receipts': 0,
        'date_from': timezone.now().date() - timedelta(days=30),
        'date_to': timezone.now().date(),
    }
    return render(request, 'reports/financial/receipt_journal.html', context)

def inventory_journal(request):
    """Inventory Journal"""
    context = {
        'journal_entries': [],
        'today': timezone.now().date(),
    }
    return render(request, 'reports/financial/inventory_journal.html', context)

def ar_aging_report(request):
    """Accounts Receivable Aging"""
    context = {
        'today': timezone.now().date(),
        'bucket_totals': {'current': {}, '1_30': {}, '31_60': {}, '61_90': {}, '90_plus': {}},
        'invoices': [],
        'total_invoices': 0,
        'total_outstanding': 0,
    }
    return render(request, 'reports/financial/ar_aging.html', context)

def ap_aging_report(request):
    """Accounts Payable Aging"""
    return render(request, 'reports/financial/ap_aging.html')

# ============================
# INVENTORY REPORTS
# ============================
def stock_summary_report(request):
    """Stock Summary"""
    return render(request, 'reports/inventory/stock_summary.html')

def stock_value_report(request):
    """Stock Value"""
    return render(request, 'reports/inventory/stock_value.html')

def stock_aging_report(request):
    """Stock Aging"""
    return render(request, 'reports/inventory/stock_aging.html')

def expiry_report(request):
    """Expiry Report"""
    return render(request, 'reports/inventory/expiry_report.html')

def low_stock_report(request):
    """Low Stock Report"""
    return render(request, 'reports/inventory/low_stock_report.html')

def inventory_movements_report(request):
    """Stock Movements"""
    return render(request, 'reports/financial/inventory_journal.html')

# ============================
# SALES REPORTS
# ============================
def revenue_analysis_report(request):
    """Revenue Analysis"""
    return render(request, 'reports/sales/revenue_analysis.html')

def product_sales_report(request):
    """Product Sales"""
    return render(request, 'reports/sales/product_sales.html')

def customer_performance_report(request):
    """Customer Performance"""
    return render(request, 'reports/sales/customer_performance.html')

# ============================
# PURCHASING REPORTS
# ============================
def supplier_performance_report(request):
    """Supplier Performance"""
    return render(request, 'reports/purchasing/supplier_performance.html')

def spend_analysis_report(request):
    """Spend Analysis"""
    return render(request, 'reports/purchasing/spend_analysis.html')

def po_summary_report(request):
    """Purchase Order Summary"""
    return render(request, 'reports/purchasing/po_summary.html')

def lead_time_report(request):
    """Lead Time Analysis"""
    return render(request, 'reports/purchasing/lead_time.html')

# ============================
# PRODUCTION REPORTS
# ============================
def production_runs_report(request):
    """Production Runs"""
    return render(request, 'reports/production/production_runs.html')

def production_yield_report(request):
    """Yield Analysis"""
    return render(request, 'reports/production/yield_analysis.html')

def cost_variance_report(request):
    """Cost Variance"""
    return render(request, 'reports/production/cost_variance.html')

def consumption_report(request):
    """Material Consumption"""
    return render(request, 'reports/production/consumption_report.html')

# ============================
# CUSTOM REPORTS
# ============================
def kpi_dashboard(request):
    """KPI Dashboard"""
    return render(request, 'reports/custom/kpi_dashboard.html')

def comparative_analysis(request):
    """Comparative Analysis"""
    return render(request, 'reports/custom/comparative_analysis.html')

def executive_summary(request):
    """Executive Summary"""
    return render(request, 'reports/custom/executive_summary.html')