from django.utils import timezone
from django.db.models import Sum, Count, Q
from apps.inventory.models import Item, StockTransaction
from apps.sales.models import SalesInvoice
from apps.purchasing.models import PurchaseOrder
from apps.production.models import ProductionRun
from apps.accounting.models import JournalEntry
from decimal import Decimal

class DashboardWidgets:
    """Collection of dashboard widgets for reports"""
    
    @staticmethod
    def get_kpi_widgets():
        """Return KPI widgets for dashboard"""
        today = timezone.now().date()
        month_start = today.replace(day=1)
        
        return [
            {
                'id': 'total_revenue',
                'title': 'Monthly Revenue',
                'value': SalesInvoice.objects.filter(
                    invoice_date__gte=month_start,
                    status__in=['posted', 'paid']
                ).aggregate(total=Sum('total_amount'))['total'] or 0,
                'icon': 'cash-stack',
                'color': 'success',
                'link': 'reports:sales_revenue_analysis'
            },
            {
                'id': 'total_expenses',
                'title': 'Monthly Expenses',
                'value': JournalEntry.objects.filter(
                    entry_date__gte=month_start,
                    status='posted'
                ).aggregate(total=Sum('total_debit'))['total'] or 0,
                'icon': 'arrow-down',
                'color': 'danger',
                'link': 'reports:profit_loss'
            },
            {
                'id': 'inventory_value',
                'title': 'Inventory Value',
                'value': Item.objects.aggregate(
                    total=Sum('current_stock_value')
                )['total'] or 0,
                'icon': 'box',
                'color': 'info',
                'link': 'reports:inventory_stock_value'
            },
            {
                'id': 'pending_orders',
                'title': 'Pending Orders',
                'value': PurchaseOrder.objects.filter(
                    status__in=['draft', 'confirmed', 'sent']
                ).count(),
                'icon': 'cart',
                'color': 'warning',
                'link': 'reports:purchase_order_summary'
            },
        ]
    
    @staticmethod
    def get_chart_widgets():
        """Return chart widgets for dashboard"""
        return [
            {
                'id': 'revenue_chart',
                'title': 'Revenue Trend',
                'type': 'line',
                'data_url': '/reports/api/revenue-trend/',
                'height': 300
            },
            {
                'id': 'sales_by_product',
                'title': 'Sales by Product',
                'type': 'pie',
                'data_url': '/reports/api/sales-by-product/',
                'height': 300
            },
            {
                'id': 'inventory_by_category',
                'title': 'Inventory by Category',
                'type': 'doughnut',
                'data_url': '/reports/api/inventory-by-category/',
                'height': 300
            },
            {
                'id': 'production_efficiency',
                'title': 'Production Efficiency',
                'type': 'gauge',
                'value': 85,
                'max': 100,
                'height': 200
            },
        ]
    
    @staticmethod
    def get_table_widgets():
        """Return table widgets for dashboard"""
        return [
            {
                'id': 'recent_invoices',
                'title': 'Recent Invoices',
                'headers': ['Invoice #', 'Customer', 'Date', 'Amount', 'Status'],
                'data': SalesInvoice.objects.filter(
                    status__in=['posted', 'paid']
                ).order_by('-invoice_date')[:5].values_list(
                    'invoice_number', 'customer__name', 'invoice_date', 'total_amount', 'status'
                ),
                'link': 'admin:sales_salesinvoice_changelist'
            },
            {
                'id': 'low_stock_alerts',
                'title': 'Low Stock Alerts',
                'headers': ['Item', 'Current Stock', 'Reorder Level'],
                'data': Item.objects.filter(
                    current_stock__lte=models.F('reorder_level')
                )[:5].values_list('name', 'current_stock', 'reorder_level'),
                'link': 'reports:inventory_low_stock'
            },
            {
                'id': 'production_schedule',
                'title': "Today's Production",
                'headers': ['Run ID', 'Product', 'Quantity', 'Status', 'Progress'],
                'data': ProductionRun.objects.filter(
                    start_date__date=today
                )[:5].values_list('id', 'product__name', 'planned_quantity', 'status', 'progress'),
                'link': 'reports:production_runs'
            },
        ]