from django.db.models import Sum, F, Q
from django.utils import timezone
from django.contrib.auth.models import User

# Core Inventory Imports
from apps.inventory.models import CurrentStock, Lot, StockTransaction

# Accounting & Audit Imports
# Note: Ensure these models exist in your accounting and core apps
from apps.accounting.models import Account, JournalEntry 
# If JournalItem is in accounting.models, it is included here:
try:
    from apps.accounting.models import JournalItem
except ImportError:
    # Fallback or placeholder if model name differs
    JournalItem = None

# Assuming UserActivity is in a core or audit app
try:
    from apps.core.models import UserActivity
except ImportError:
    UserActivity = None

class ReportService:

    @staticmethod
    def get_low_stock_alert():
        """
        Calculates total quantity per item across all warehouses.
        Filters for items below a threshold of 10.
        """
        return CurrentStock.objects.values(
            name=F('item__name'), 
            code=F('item__code')
        ).annotate(
            total_qty=Sum('quantity')
        ).filter(total_qty__lt=10)

    @staticmethod
    def get_expiry_report():
        """
        Fetches active batches/lots ordered by their expiry date.
        """
        return Lot.objects.filter(is_active=True).values(
            'batch_number', 
            'expiry_date', 
            'item__name'
        ).order_by('expiry_date')

    @staticmethod
    def get_user_activity_report():
        """
        Fetches the system audit log.
        """
        if UserActivity is None:
            return []
        return UserActivity.objects.all().select_related('user', 'content_type').values(
            'user__username', 
            'action', 
            'content_type__model', 
            'description', 
            'timestamp'
        ).order_by('-timestamp')

    @staticmethod
    def get_profit_loss_data():
        """
        Calculates Income vs Expenses based on Journal Items.
        """
        if JournalItem is None:
            # Return placeholder if accounting module is not fully migrated
            return {
                'groups': [
                    {'name': 'Operating Revenue', 'items': [{'label': 'Placeholder', 'value': 0}], 'total': 0},
                    {'name': 'Operating Expenses', 'items': [], 'total': 0},
                ],
                'net_profit': 0
            }

        # 1. Fetch Income (Credit - Debit for income accounts)
        income = JournalItem.objects.filter(
            account__account_type='income'
        ).aggregate(total=Sum('credit') - Sum('debit'))['total'] or 0

        # 2. Fetch Expenses per Account
        expenses_list = Account.objects.filter(account_type='expense').annotate(
            total=Sum('journalitem__debit') - Sum('journalitem__credit')
        ).filter(total__gt=0)

        total_expenses = sum(exp.total for exp in expenses_list)
        
        return {
            'groups': [
                {
                    'name': 'Operating Revenue', 
                    'items': [{'label': 'Sales Income', 'value': income}], 
                    'total': income
                },
                {
                    'name': 'Operating Expenses', 
                    'items': [{'label': exp.name, 'value': exp.total} for exp in expenses_list], 
                    'total': total_expenses
                },
            ],
            'net_profit': income - total_expenses
        }

# --- Configuration Mapping ---

REPORT_CONFIG = {
    'profit_loss': {
        'title': 'Profit and Loss Statement',
        'template': 'reports/archetypes/financial_statement.html',
        'data_func': ReportService.get_profit_loss_data,
        'permission': 'apps.view_financial_reports',
        'columns': []  # Handled by custom template logic
    },
    'low_stock': {
        'title': 'Low Stock Alert',
        'template': 'reports/archetypes/table_list.html',
        'data_func': ReportService.get_low_stock_alert,
        'permission': 'apps.view_inventory_reports',
        'columns': ['Item Name', 'Item Code', 'Total Quantity']
    },
    'expiry': {
        'title': 'Batch Expiry Report',
        'template': 'reports/archetypes/table_list.html',
        'data_func': ReportService.get_expiry_report,
        'permission': 'apps.view_inventory_reports',
        'columns': ['Batch Number', 'Expiry Date', 'Item Name']
    },
    'user_activity': {
        'title': 'System Audit Log / User Activity',
        'template': 'reports/archetypes/table_list.html',
        'data_func': ReportService.get_user_activity_report,
        'permission': 'apps.view_audit_logs',
        'columns': ['User', 'Action', 'Module', 'Details', 'Time']
    }
}