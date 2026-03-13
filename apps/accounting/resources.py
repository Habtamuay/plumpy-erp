from import_export import resources, fields
from import_export.widgets import DateWidget
from django.utils import timezone
from io import BytesIO
import openpyxl
from openpyxl.styles import Font

from apps.accounting.models import PurchaseBill
from apps.sales.models import SalesInvoice

class ExcelStylingMixin:
    def export_styled(self, queryset):
        """Exports data and applies bold styling to headers."""
        # 1. Generate standard export data
        dataset = self.export(queryset)
        
        # 2. Load into openpyxl for styling
        wb = openpyxl.load_workbook(BytesIO(dataset.xlsx))
        ws = wb.active
        
        # 3. Apply Bold Font to Header Row
        bold_font = Font(bold=True)
        for cell in ws[1]:
            cell.font = bold_font
            
        # 4. Save back to bytes
        output = BytesIO()
        wb.save(output)
        return output.getvalue()

class ARAgingResource(ExcelStylingMixin, resources.ModelResource):
    customer = fields.Field(attribute='customer__name', column_name='Customer')
    invoice_date = fields.Field(attribute='invoice_date', column_name='Invoice Date', widget=DateWidget())
    due_date = fields.Field(attribute='due_date', column_name='Due Date', widget=DateWidget())
    days_overdue = fields.Field(column_name='Days Overdue')
    remaining_amount = fields.Field(column_name='Balance')
    status = fields.Field(attribute='get_status_display', column_name='Status')

    class Meta:
        model = SalesInvoice
        fields = ('invoice_number', 'customer', 'invoice_date', 'due_date', 'status', 'total_amount', 'paid_amount', 'remaining_amount', 'days_overdue')
        export_order = ('invoice_number', 'customer', 'invoice_date', 'due_date', 'status', 'days_overdue', 'total_amount', 'paid_amount', 'remaining_amount')

    def dehydrate_days_overdue(self, obj):
        # Return days overdue if it's a property, otherwise calculate it
        if hasattr(obj, 'days_overdue'):
            return obj.days_overdue
        if obj.due_date and obj.due_date < timezone.now().date():
            return (timezone.now().date() - obj.due_date).days
        return 0

    def dehydrate_remaining_amount(self, obj):
        return getattr(obj, 'remaining_amount', obj.total_amount - (obj.paid_amount or 0))


class APAgingResource(ExcelStylingMixin, resources.ModelResource):
    supplier = fields.Field(attribute='supplier__name', column_name='Supplier')
    bill_date = fields.Field(attribute='bill_date', column_name='Bill Date', widget=DateWidget())
    due_date = fields.Field(attribute='due_date', column_name='Due Date', widget=DateWidget())
    days_overdue = fields.Field(column_name='Days Overdue')
    remaining_amount = fields.Field(column_name='Balance')
    status = fields.Field(attribute='get_status_display', column_name='Status')

    class Meta:
        model = PurchaseBill
        fields = ('bill_number', 'supplier', 'bill_date', 'due_date', 'status', 'total_amount', 'paid_amount', 'remaining_amount', 'days_overdue')
        export_order = ('bill_number', 'supplier', 'bill_date', 'due_date', 'status', 'days_overdue', 'total_amount', 'paid_amount', 'remaining_amount')

    def dehydrate_days_overdue(self, obj):
        if hasattr(obj, 'days_overdue'):
            return obj.days_overdue
        if obj.due_date and obj.due_date < timezone.now().date():
            return (timezone.now().date() - obj.due_date).days
        return 0

    def dehydrate_remaining_amount(self, obj):
        return getattr(obj, 'remaining_amount', obj.total_amount - (obj.paid_amount or 0))