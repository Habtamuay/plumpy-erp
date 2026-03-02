from import_export import resources, fields
from import_export.widgets import DateWidget, DecimalWidget
from apps.sales.models import SalesInvoice  # Import from sales app
from .models import PurchaseBill


class ARAgingResource(resources.ModelResource):
    """Resource for exporting AR aging data"""
    
    invoice_number = fields.Field(attribute='invoice_number', column_name='Invoice #')
    customer_name = fields.Field(attribute='customer__name', column_name='Customer')
    invoice_date = fields.Field(attribute='invoice_date', column_name='Invoice Date', widget=DateWidget())
    due_date = fields.Field(attribute='due_date', column_name='Due Date', widget=DateWidget())
    days_overdue = fields.Field(attribute='days_overdue', column_name='Days Overdue')
    amount = fields.Field(attribute='total_amount', column_name='Amount (ETB)')
    status = fields.Field(attribute='get_status_display', column_name='Status')

    class Meta:
        model = SalesInvoice  # Use SalesInvoice from sales app
        fields = ('invoice_number', 'customer_name', 'invoice_date', 'due_date', 'days_overdue', 'amount', 'status')
        export_order = fields

    def dehydrate_amount(self, obj):
        """Format amount with 2 decimal places"""
        return float(obj.total_amount)

    def dehydrate_days_overdue(self, obj):
        """Calculate days overdue"""
        from django.utils import timezone
        if obj.due_date and obj.due_date < timezone.now().date():
            return (timezone.now().date() - obj.due_date).days
        return 0


class APAgingResource(resources.ModelResource):
    """Resource for exporting AP aging data"""
    
    bill_number = fields.Field(attribute='bill_number', column_name='Bill #')
    supplier_name = fields.Field(attribute='supplier__name', column_name='Supplier')
    bill_date = fields.Field(attribute='bill_date', column_name='Bill Date', widget=DateWidget())
    due_date = fields.Field(attribute='due_date', column_name='Due Date', widget=DateWidget())
    days_overdue = fields.Field(attribute='days_overdue', column_name='Days Overdue')
    amount = fields.Field(attribute='total_amount', column_name='Amount (ETB)')
    status = fields.Field(attribute='get_status_display', column_name='Status')

    class Meta:
        model = PurchaseBill
        fields = ('bill_number', 'supplier_name', 'bill_date', 'due_date', 'days_overdue', 'amount', 'status')
        export_order = fields

    def dehydrate_amount(self, obj):
        """Format amount with 2 decimal places"""
        return float(obj.total_amount)

    def dehydrate_days_overdue(self, obj):
        """Calculate days overdue"""
        from django.utils import timezone
        if obj.due_date and obj.due_date < timezone.now().date():
            return (timezone.now().date() - obj.due_date).days
        return 0


# Optional: Add more resources as needed
class JournalEntryResource(resources.ModelResource):
    """Resource for exporting journal entries"""
    
    class Meta:
        model = None  # Placeholder
        fields = []


class TrialBalanceResource(resources.ModelResource):
    """Resource for exporting trial balance"""
    
    class Meta:
        model = None  # Placeholder
        fields = []