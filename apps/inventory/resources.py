from import_export import resources, fields
from import_export.widgets import DecimalWidget, NumberWidget, DateWidget
from decimal import Decimal
from django.utils import timezone

from .models import CurrentStock, StockTransaction, Lot, Warehouse


class ConsumptionReportResource(resources.Resource):
    """Resource for exporting Consumption vs BOM data with advanced Excel styling"""
    
    component_code = fields.Field(attribute='component_code', column_name='Component Code')
    component_name = fields.Field(attribute='component_name', column_name='Component Name')
    std_qty_per_kg = fields.Field(attribute='std_qty_per_kg', column_name='Std Qty / kg')
    wastage_pct    = fields.Field(attribute='wastage_pct', column_name='Wastage %')
    expected_total = fields.Field(attribute='expected_total', column_name='Expected (incl. wastage)')
    actual_issued  = fields.Field(attribute='actual_issued', column_name='Actual Issued')
    variance_qty   = fields.Field(attribute='variance_qty', column_name='Variance (kg)')
    variance_pct   = fields.Field(attribute='variance_pct', column_name='Variance (%)')

    class Meta:
        export_order = (
            'component_code', 'component_name', 'std_qty_per_kg', 'wastage_pct',
            'expected_total', 'actual_issued', 'variance_qty', 'variance_pct'
        )
        title = "Consumption vs BOM Report"

    def before_export(self, queryset, *args, **kwargs):
        """Store metadata for use in after_export"""
        self.product_name = kwargs.get('product_name', 'N/A')
        self.total_produced_kg = kwargs.get('total_produced_kg', 0)
        self.period_from = kwargs.get('period_from', '')
        self.period_to = kwargs.get('period_to', '')
        self.company_name = kwargs.get('company_name', 'HILINA ENRICHED FOODS PLC')
        
        # Format the queryset data with proper decimal places
        formatted_queryset = []
        for item in queryset:
            formatted_item = {}
            for key, value in item.items():
                if isinstance(value, Decimal):
                    if key in ['std_qty_per_kg']:
                        formatted_item[key] = float(value)
                    elif key in ['wastage_pct', 'variance_pct']:
                        formatted_item[key] = float(value)
                    else:
                        formatted_item[key] = float(value)
                else:
                    formatted_item[key] = value
            formatted_queryset.append(formatted_item)
        
        return formatted_queryset

    def after_export(self, queryset, data, *args, **kwargs):
        """Advanced styling with xlsxwriter"""
        if not hasattr(data, 'get_workbook'):  # only for XLSX
            return data

        workbook = data.get_workbook()
        worksheet = workbook.get_worksheet_by_name('Sheet1')

        # Insert 4 rows at the top for header
        worksheet.insert_rows(0, 4)

        # ── Company Header (rows 1–4) ───────────────────────────────────────
        header_format = workbook.add_format({
            'bold': True, 'font_size': 14, 'align': 'center', 'valign': 'vcenter',
            'bg_color': '#004d99', 'font_color': 'white', 'border': 1
        })
        subheader_format = workbook.add_format({
            'bold': True, 'font_size': 12, 'align': 'center', 'valign': 'vcenter',
            'bg_color': '#cce0ff', 'border': 1
        })
        date_format = workbook.add_format({
            'align': 'center', 'font_size': 10, 'italic': True
        })

        # Write header rows
        worksheet.merge_range('A1:H1', self.company_name, header_format)
        worksheet.merge_range('A2:H2', 'Consumption vs BOM Standard Report', subheader_format)
        
        product_info = f'Product: {self.product_name} • Produced: {self.total_produced_kg:,.2f} kg'
        worksheet.merge_range('A3:H3', product_info, subheader_format)
        
        period_info = f'Period: {self.period_from} – {self.period_to} • Generated: {timezone.now().strftime("%d %b %Y %H:%M")}'
        worksheet.merge_range('A4:H4', period_info, date_format)

        # ── Format headers (now row 5) ──────────────────────────────────────
        header_format = workbook.add_format({
            'bold': True, 'bg_color': '#d9e6ff', 'border': 1,
            'align': 'center', 'valign': 'vcenter', 'text_wrap': True
        })
        for col_num, header in enumerate(data.headers):
            worksheet.write(4, col_num, header, header_format)

        # ── Data rows formatting (starting from row 6) ──────────────────────
        num_format = workbook.add_format({'num_format': '#,##0.00', 'align': 'right'})
        pct_format = workbook.add_format({'num_format': '0.00"%"', 'align': 'right'})
        text_format = workbook.add_format({'align': 'left'})

        red_format = workbook.add_format({
            'bg_color': '#ffe6e6', 
            'num_format': '#,##0.00', 
            'align': 'right',
            'font_color': '#9c1d1d'
        })
        green_format = workbook.add_format({
            'bg_color': '#e6ffe6', 
            'num_format': '#,##0.00', 
            'align': 'right',
            'font_color': '#1d6b1d'
        })

        # Write data rows
        for row_num, row_data in enumerate(data.dict, start=5):
            for col_num, (key, value) in enumerate(row_data.items()):
                try:
                    float_val = float(value) if value not in [None, ''] else 0
                    
                    if col_num in [3, 4, 5, 6]:  # Numeric columns (Expected, Actual, Variance kg, Variance %)
                        if col_num == 6:  # Variance kg - special coloring
                            if float_val > 0:
                                worksheet.write_number(row_num, col_num, float_val, red_format)
                            elif float_val < 0:
                                worksheet.write_number(row_num, col_num, float_val, green_format)
                            else:
                                worksheet.write_number(row_num, col_num, float_val, num_format)
                        elif col_num == 7:  # Variance %
                            worksheet.write_number(row_num, col_num, float_val, pct_format)
                        else:  # Expected, Actual
                            worksheet.write_number(row_num, col_num, float_val, num_format)
                    else:
                        worksheet.write_string(row_num, col_num, str(value or ''), text_format)
                except (ValueError, TypeError):
                    worksheet.write_string(row_num, col_num, str(value or ''), text_format)

        # ── Totals row ───────────────────────────────────────────────────────
        total_expected = 0
        total_actual = 0
        total_var_kg = 0
        
        for row in data.dict:
            try:
                total_expected += float(row.get('expected_total', 0) or 0)
                total_actual += float(row.get('actual_issued', 0) or 0)
                total_var_kg += float(row.get('variance_qty', 0) or 0)
            except (ValueError, TypeError):
                pass
                
        total_var_pct = (total_var_kg / total_expected * 100) if total_expected > 0 else 0

        totals_format = workbook.add_format({
            'bold': True, 'bg_color': '#cce0ff', 'border': 1, 'align': 'right'
        })
        totals_text_format = workbook.add_format({
            'bold': True, 'bg_color': '#cce0ff', 'border': 1, 'align': 'left'
        })
        
        last_row = 5 + len(data.dict)
        
        worksheet.write_string(last_row, 0, 'TOTAL', totals_text_format)
        worksheet.write_blank(last_row, 1, '', totals_format)
        worksheet.write_blank(last_row, 2, '', totals_format)
        worksheet.write_blank(last_row, 3, '', totals_format)
        worksheet.write_number(last_row, 4, total_expected, totals_format)
        worksheet.write_number(last_row, 5, total_actual, totals_format)
        
        if total_var_kg > 0:
            worksheet.write_number(last_row, 6, total_var_kg, red_format)
        elif total_var_kg < 0:
            worksheet.write_number(last_row, 6, total_var_kg, green_format)
        else:
            worksheet.write_number(last_row, 6, total_var_kg, totals_format)
            
        worksheet.write_number(last_row, 7, total_var_pct, pct_format)

        # ── Auto column width ────────────────────────────────────────────────
        for col in range(len(data.headers)):
            max_length = 10  # minimum width
            try:
                header_len = len(str(data.headers[col]))
                max_length = max(max_length, header_len)
                
                for row in data.dict:
                    row_keys = list(row.keys())
                    if col < len(row_keys):
                        val_len = len(str(row.get(row_keys[col], '')))
                        max_length = max(max_length, val_len)
            except:
                pass
                
            worksheet.set_column(col, col, min(max_length + 2, 30))

        # Freeze panes (header + company info)
        worksheet.freeze_panes(5, 0)

        return data


class StockSummaryResource(resources.ModelResource):
    """Resource for exporting stock summary data"""
    
    item_code = fields.Field(attribute='item__code', column_name='Item Code')
    item_name = fields.Field(attribute='item__name', column_name='Item Name')
    category = fields.Field(attribute='item__category', column_name='Category')
    warehouse = fields.Field(attribute='warehouse__name', column_name='Warehouse')
    lot_number = fields.Field(attribute='lot__batch_number', column_name='Lot Number')
    quantity = fields.Field(attribute='quantity', column_name='Quantity', widget=DecimalWidget())
    unit = fields.Field(attribute='item__unit__abbreviation', column_name='Unit')
    unit_cost = fields.Field(attribute='item__unit_cost', column_name='Unit Cost', widget=DecimalWidget())
    total_value = fields.Field(attribute='stock_value', column_name='Total Value')
    expiry_date = fields.Field(attribute='lot__expiry_date', column_name='Expiry Date', widget=DateWidget())
    status = fields.Field(attribute='stock_status', column_name='Status')

    class Meta:
        model = CurrentStock
        fields = ('item_code', 'item_name', 'category', 'warehouse', 'lot_number', 
                  'quantity', 'unit', 'unit_cost', 'total_value', 'expiry_date', 'status')
        export_order = fields

    def dehydrate_category(self, obj):
        return obj.item.get_category_display() if obj.item else ''

    def dehydrate_total_value(self, obj):
        return float(obj.quantity * (obj.item.unit_cost or 0))

    def dehydrate_status(self, obj):
        if obj.quantity <= 0:
            return 'Out of Stock'
        elif obj.quantity < obj.item.minimum_stock:
            return 'Low Stock'
        elif obj.quantity < obj.item.reorder_point:
            return 'Reorder Needed'
        else:
            return 'OK'


class LowStockResource(resources.ModelResource):
    """Resource for exporting low stock alerts"""
    
    item_code = fields.Field(attribute='item__code', column_name='Item Code')
    item_name = fields.Field(attribute='item__name', column_name='Item Name')
    category = fields.Field(attribute='item__category', column_name='Category')
    warehouse = fields.Field(attribute='warehouse__name', column_name='Warehouse')
    lot_number = fields.Field(attribute='lot__batch_number', column_name='Lot Number')
    current_qty = fields.Field(attribute='quantity', column_name='Current Quantity', widget=DecimalWidget())
    minimum_stock = fields.Field(attribute='item__minimum_stock', column_name='Minimum Stock', widget=DecimalWidget())
    reorder_point = fields.Field(attribute='item__reorder_point', column_name='Reorder Point', widget=DecimalWidget())
    reorder_qty = fields.Field(attribute='item__reorder_quantity', column_name='Reorder Quantity', widget=DecimalWidget())
    deficit = fields.Field(attribute='deficit', column_name='Deficit')
    status = fields.Field(attribute='alert_status', column_name='Alert Status')

    class Meta:
        model = CurrentStock
        fields = ('item_code', 'item_name', 'category', 'warehouse', 'lot_number',
                  'current_qty', 'minimum_stock', 'reorder_point', 'reorder_qty', 
                  'deficit', 'status')
        export_order = fields

    def dehydrate_category(self, obj):
        return obj.item.get_category_display() if obj.item else ''

    def dehydrate_deficit(self, obj):
        if obj.quantity < obj.item.minimum_stock:
            return float(obj.item.minimum_stock - obj.quantity)
        return 0

    def dehydrate_alert_status(self, obj):
        if obj.quantity < obj.item.minimum_stock:
            return 'CRITICAL - Below Safety Stock'
        elif obj.quantity <= obj.item.reorder_point:
            return 'WARNING - Reorder Needed'
        return 'OK'

    def get_queryset(self):
        from django.db.models import Q, F
        return super().get_queryset().filter(
            Q(quantity__lt=F('item__minimum_stock')) |
            Q(quantity__lte=F('item__reorder_point'))
        )


class StockTransactionResource(resources.ModelResource):
    """Resource for exporting stock transactions"""
    
    transaction_date = fields.Field(attribute='transaction_date', column_name='Date', widget=DateWidget())
    transaction_type = fields.Field(attribute='transaction_type', column_name='Type')
    item_code = fields.Field(attribute='item__code', column_name='Item Code')
    item_name = fields.Field(attribute='item__name', column_name='Item Name')
    lot_number = fields.Field(attribute='lot__batch_number', column_name='Lot Number')
    quantity = fields.Field(attribute='quantity', column_name='Quantity', widget=DecimalWidget())
    unit = fields.Field(attribute='item__unit__abbreviation', column_name='Unit')
    warehouse_from = fields.Field(attribute='warehouse_from__name', column_name='From Warehouse')
    warehouse_to = fields.Field(attribute='warehouse_to__name', column_name='To Warehouse')
    reference = fields.Field(attribute='reference', column_name='Reference')
    created_by = fields.Field(attribute='created_by__username', column_name='Created By')
    notes = fields.Field(attribute='notes', column_name='Notes')

    class Meta:
        model = StockTransaction
        fields = ('transaction_date', 'transaction_type', 'item_code', 'item_name',
                  'lot_number', 'quantity', 'unit', 'warehouse_from', 'warehouse_to',
                  'reference', 'created_by', 'notes')
        export_order = fields

    def dehydrate_transaction_type(self, obj):
        return obj.get_transaction_type_display()