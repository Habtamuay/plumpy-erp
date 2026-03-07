# apps/reports/dashboard_service.py
from django.db.models import Sum, F
from apps.inventory.models import CurrentStock, StockTransaction
from django.utils import timezone

class DashboardService:
    def get_kpi_metrics(self):
        """Fetches the high-level numbers for the dashboard."""
        
        # Calculate Total Stock Value using your model's fields
        # Note: Your model uses item__unit_cost for valuation
        total_stock_value = CurrentStock.objects.aggregate(
            total=Sum(F('quantity') * F('item__unit_cost'))
        )['total'] or 0

        # Count low stock items (e.g., items with quantity < 10)
        low_stock_count = CurrentStock.objects.filter(quantity__lt=10).count()

        return {
            'total_stock_value': total_stock_value,
            'low_stock_count': low_stock_count,
            'recent_transactions_count': StockTransaction.objects.filter(
                transaction_date__date=timezone.now().date()
            ).count(),
        }

    def get_recent_stock_movements(self):
        """Fetches the last 5 transactions for the dashboard table."""
        return StockTransaction.objects.select_related('item', 'warehouse_to', 'warehouse_from').all()[:5]

