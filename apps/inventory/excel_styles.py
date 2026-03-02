# apps/inventory/excel_styles.py
from xlsxwriter.format import Format


class ExcelStyleConfig:
    """Central place for all Excel styling – easy to change branding"""

    # Company / Report header
    COMPANY_NAME = "HILINA ENRICHED FOODS PLC"
    REPORT_TITLE = "Consumption vs BOM Standard Report"
    HEADER_BG = '#004d99'          # dark blue
    HEADER_TEXT = 'white'
    SUBHEADER_BG = '#cce0ff'       # light blue
    SUBHEADER_TEXT = 'black'

    # Table header
    HEADER_BG = '#d9e6ff'          # very light blue
    HEADER_BOLD = True
    HEADER_BORDER = 1

    # Data rows
    NUMBER_FORMAT = '#,##0.00'
    PERCENT_FORMAT = '0.00"%"'

    # Variance conditional colors
    POSITIVE_VARIANCE_BG = '#ffe6e6'   # light red (over usage)
    NEGATIVE_VARIANCE_BG = '#e6ffe6'   # light green (under usage)
    ZERO_VARIANCE_BG = '#ffffff'

    # Totals row
    TOTALS_BG = '#cce0ff'          # same as subheader
    TOTALS_BOLD = True

    # Column widths (can be overridden)
    DEFAULT_COL_WIDTH = 15

    # Font
    DEFAULT_FONT = 'Calibri'
    HEADER_FONT_SIZE = 14
    SUBHEADER_FONT_SIZE = 12
    DATA_FONT_SIZE = 11

    @classmethod
    def apply_to_worksheet(cls, worksheet, workbook, data_rows_count, headers):
        """Apply all styles – called from after_export"""

        # ── Company Header (rows 1–4) ───────────────────────────────
        header_format = workbook.add_format({
            'bold': True,
            'font_size': cls.HEADER_FONT_SIZE,
            'font_name': cls.DEFAULT_FONT,
            'align': 'center',
            'valign': 'vcenter',
            'bg_color': cls.HEADER_BG,
            'font_color': cls.HEADER_TEXT,
            'border': 1
        })

        subheader_format = workbook.add_format({
            'bold': True,
            'font_size': cls.SUBHEADER_FONT_SIZE,
            'font_name': cls.DEFAULT_FONT,
            'align': 'center',
            'valign': 'vcenter',
            'bg_color': cls.SUBHEADER_BG,
            'border': 1
        })

        date_format = workbook.add_format({
            'align': 'center',
            'font_size': 10,
            'font_name': cls.DEFAULT_FONT
        })

        worksheet.merge_range('A1:H1', cls.COMPANY_NAME, header_format)
        worksheet.merge_range('A2:H2', cls.REPORT_TITLE, subheader_format)
        # You can make these dynamic if passed from view
        worksheet.merge_range('A3:H3', 'Product: [Product Name] • Produced: [X] kg', subheader_format)
        worksheet.merge_range('A4:H4', f'Generated: {timezone.now().strftime("%d %b %Y %H:%M")}', date_format)

        # Shift data down
        worksheet.insert_rows(1, 4)

        # ── Table headers (now row 5) ───────────────────────────────
        header_format = workbook.add_format({
            'bold': cls.HEADER_BOLD,
            'bg_color': cls.HEADER_BG,
            'border': cls.HEADER_BORDER,
            'align': 'center',
            'valign': 'vcenter',
            'text_wrap': True,
            'font_name': cls.DEFAULT_FONT,
            'font_size': cls.DATA_FONT_SIZE
        })

        for col_num, header in enumerate(headers):
            worksheet.write(4, col_num, header, header_format)

        # ── Data rows formatting ────────────────────────────────────
        num_format = workbook.add_format({
            'num_format': cls.NUMBER_FORMAT,
            'align': 'right',
            'font_name': cls.DEFAULT_FONT,
            'font_size': cls.DATA_FONT_SIZE
        })

        pct_format = workbook.add_format({
            'num_format': cls.PERCENT_FORMAT,
            'align': 'right',
            'font_name': cls.DEFAULT_FONT,
            'font_size': cls.DATA_FONT_SIZE
        })

        red_format = workbook.add_format({
            'bg_color': cls.POSITIVE_VARIANCE_BG,
            'num_format': cls.NUMBER_FORMAT,
            'align': 'right'
        })

        green_format = workbook.add_format({
            'bg_color': cls.NEGATIVE_VARIANCE_BG,
            'num_format': cls.NUMBER_FORMAT,
            'align': 'right'
        })

        # Apply to data rows (rows 6 → 6 + data_rows_count)
        for row_idx in range(5, 5 + data_rows_count):
            # Variance kg column (index 6)
            worksheet.conditional_format(row_idx, 6, row_idx, 6, {
                'type': 'cell',
                'criteria': '>',
                'value': 0,
                'format': red_format
            })
            worksheet.conditional_format(row_idx, 6, row_idx, 6, {
                'type': 'cell',
                'criteria': '<',
                'value': 0,
                'format': green_format
            })

            # Apply default number format to numeric columns
            for col in [4, 5, 6]:  # Expected, Actual, Variance kg
                worksheet.write(row_idx, col, None, num_format)

            worksheet.write(row_idx, 7, None, pct_format)  # Variance %

        # ── Totals row (after last data row) ────────────────────────
        totals_row = 5 + data_rows_count
        totals_format = workbook.add_format({
            'bold': cls.TOTALS_BOLD,
            'bg_color': cls.TOTALS_BG,
            'border': 1,
            'align': 'right',
            'font_name': cls.DEFAULT_FONT,
            'font_size': cls.DATA_FONT_SIZE
        })

        worksheet.write(totals_row, 0, 'TOTAL', totals_format)
        # ... write totals values with formats (as in previous code)

        # ── Auto column width + freeze panes ────────────────────────
        for col in range(len(headers)):
            max_len = max(
                len(str(headers[col])),
                max((len(str(row.get(headers[col], ''))) for row in queryset), default=0)
            )
            worksheet.set_column(col, col, max_len + 2)

        worksheet.freeze_panes(5, 0)  # Freeze header + company info