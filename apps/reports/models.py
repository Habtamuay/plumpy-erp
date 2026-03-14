from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, MaxValueValidator
from apps.core.models import CompanyModel  # assuming this is your abstract base model with company scope

User = get_user_model()


class ReportCategory(CompanyModel):
    """Category for organizing reports (grouping in menu / dashboard)"""
    name = models.CharField(max_length=100, unique=True)
    icon = models.CharField(max_length=50, blank=True, help_text="Font Awesome or Bootstrap icon class")
    description = models.TextField(blank=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['display_order', 'name']
        verbose_name = "Report Category"
        verbose_name_plural = "Report Categories"

    def __str__(self):
        return self.name


class ReportTemplate(CompanyModel):
    """Master definition / template for each available report"""

    # Expanded list covering most ERP modules
    REPORT_TYPES = [
        # ── Inventory ────────────────────────────────────────
        ('inventory_stock_summary',         'Stock Summary'),
        ('inventory_stock_value',           'Stock Valuation'),
        ('inventory_stock_aging',           'Stock Aging Analysis'),
        ('inventory_low_stock',             'Low Stock Alert'),
        ('inventory_expiry',                'Expiry & Near Expiry'),
        ('inventory_movements',             'Stock Movement History'),
        ('inventory_reorder',               'Reorder Recommendations'),
        ('inventory_batch_tracking',        'Batch / Lot Tracking'),
        ('inventory_turnover',              'Inventory Turnover Ratio'),

        # ── Production ───────────────────────────────────────
        ('production_runs',                 'Production Runs'),
        ('production_cost_variance',        'Production Cost Variance'),
        ('production_yield',                'Yield & Scrap Analysis'),
        ('production_efficiency',           'Production Efficiency'),
        ('production_material_consumption', 'Material Consumption'),
        ('production_downtime',             'Downtime & OEE'),
        ('production_capacity_utilization', 'Capacity Utilization'),

        # ── Purchasing ───────────────────────────────────────
        ('purchasing_po_summary',           'Purchase Order Summary'),
        ('purchasing_supplier_performance', 'Supplier Performance'),
        ('purchasing_spend_analysis',       'Spend by Category / Supplier'),
        ('purchasing_lead_time',            'Supplier Lead Time Analysis'),
        ('purchasing_price_trend',          'Price Trend & Variance'),
        ('purchasing_open_po',              'Open Purchase Orders'),

        # ── Sales & Distribution ─────────────────────────────
        ('sales_order_summary',             'Sales Order Summary'),
        ('sales_invoice_summary',           'Invoice / Billing Summary'),
        ('sales_customer_performance',      'Customer Performance'),
        ('sales_revenue_analysis',          'Revenue & Margin Analysis'),
        ('sales_product_sales',             'Product Sales Performance'),
        ('sales_forecast',                  'Sales Forecast'),
        ('sales_return_analysis',           'Returns & Credit Notes'),

        # ── Financial / Accounting ───────────────────────────
        ('financial_profit_loss',           'Profit & Loss Statement'),
        ('financial_balance_sheet',         'Balance Sheet'),
        ('financial_cash_flow',             'Cash Flow Statement'),
        ('financial_trial_balance',         'Trial Balance'),
        ('financial_ar_aging',              'Accounts Receivable Aging'),
        ('financial_ap_aging',              'Accounts Payable Aging'),
        ('financial_budget_variance',       'Budget vs Actual'),
        ('financial_gl_transaction',        'General Ledger Transactions'),
        ('financial_journal_entry',         'Journal Entry List'),

        # ── HR & Payroll ─────────────────────────────────────
        ('hr_employee_list',                'Employee Directory'),
        ('hr_attendance_summary',           'Attendance Summary'),
        ('hr_payroll_summary',              'Payroll Summary'),
        ('hr_leave_balance',                'Leave Balance Report'),
        ('hr_turnover_analysis',            'Employee Turnover'),

        # ── Fixed Assets ─────────────────────────────────────
        ('assets_register',                 'Fixed Assets Register'),
        ('assets_depreciation',             'Depreciation Schedule'),
        ('assets_disposal',                 'Asset Disposal / Sale'),

        # ── Custom / Advanced ────────────────────────────────
        ('custom_sql',                      'Custom SQL Report'),
        ('custom_aggregate',                'Custom Aggregate / Pivot'),
        ('custom_dashboard_kpi',            'Custom KPI Set'),
    ]

    FORMAT_CHOICES = [
        ('pdf',  'PDF'),
        ('xlsx', 'Excel (.xlsx)'),
        ('csv',  'CSV'),
        ('html', 'HTML (for preview)'),
        ('json', 'JSON (for API / integration)'),
    ]

    category    = models.ForeignKey(ReportCategory, on_delete=models.PROTECT, related_name='reports', null=True, blank=True)
    name        = models.CharField(max_length=200)
    slug        = models.SlugField(max_length=200, unique=True)
    description = models.TextField(blank=True)

    report_type = models.CharField(max_length=60, choices=REPORT_TYPES)
    format      = models.CharField(max_length=10, choices=FORMAT_CHOICES, default='pdf')

    # Template & query configuration
    template_file = models.CharField(max_length=255, blank=True, help_text="Path to custom Django template (optional)")
    query_config  = models.JSONField(default=dict, blank=True, help_text="JSON config for dynamic query/filters/aggregates")

    # UI / presentation settings
    icon        = models.CharField(max_length=50, blank=True, default='bi-file-earmark-text')
    color       = models.CharField(max_length=20, blank=True, default='primary')

    # Control flags
    is_system   = models.BooleanField(default=False, help_text="System-protected report (cannot be deleted)")
    is_active   = models.BooleanField(default=True)

    # Audit
    created_by  = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_report_templates')
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category__display_order', 'name']
        verbose_name = "Report Template"
        verbose_name_plural = "Report Templates"
        indexes = [
            models.Index(fields=['report_type']),
            models.Index(fields=['slug']),
        ]

    def __str__(self):
        return self.name


class ReportRequest(CompanyModel):
    """Individual request to generate a report (on-demand or scheduled)"""

    REPORT_STATUSES = [
        ('pending',    'Pending'),
        ('processing', 'Processing'),
        ('completed',  'Completed'),
        ('failed',     'Failed'),
    ]

    user          = models.ForeignKey(User, on_delete=models.CASCADE, related_name='report_requests')
    template      = models.ForeignKey(ReportTemplate, on_delete=models.PROTECT, related_name='requests', null=True, blank=True)
    report_type   = models.CharField(max_length=60)  # copy from template at creation time
    format        = models.CharField(max_length=10, default='pdf')

    parameters    = models.JSONField(default=dict, blank=True)         # filters, date range, warehouse_id, etc.
    status        = models.CharField(max_length=20, choices=REPORT_STATUSES, default='pending')
    task_id       = models.CharField(max_length=255, blank=True, null=True)
    file          = models.FileField(upload_to='reports/%Y/%m/%d/', blank=True, null=True)
    error_message = models.TextField(blank=True)

    created_at    = models.DateTimeField(auto_now_add=True)
    completed_at  = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Report Request"
        verbose_name_plural = "Report Requests"
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.report_type} – {self.user} – {self.status}"


class ScheduledReport(CompanyModel):
    """Periodic / scheduled execution of reports"""

    SCHEDULE_TYPES = [
        ('daily',     'Daily'),
        ('weekly',    'Weekly'),
        ('monthly',   'Monthly'),
        ('quarterly', 'Quarterly'),
        ('yearly',    'Yearly'),
        ('custom',    'Custom Cron'),
    ]

    name          = models.CharField(max_length=200)
    report        = models.ForeignKey(ReportTemplate, on_delete=models.CASCADE, related_name='schedules')
    description   = models.TextField(blank=True)

    schedule_type = models.CharField(max_length=20, choices=SCHEDULE_TYPES, default='monthly')
    hour          = models.PositiveSmallIntegerField(default=8, validators=[MinValueValidator(0), MaxValueValidator(23)])
    minute        = models.PositiveSmallIntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(59)])
    day_of_month  = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(31)])
    day_of_week   = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(6)], help_text="0 = Monday ... 6 = Sunday")
    custom_cron   = models.CharField(max_length=100, blank=True, help_text="Standard cron expression if schedule_type='custom'")

    recipients    = models.TextField(help_text="Comma-separated email addresses")
    email_subject = models.CharField(max_length=255, blank=True)
    email_body    = models.TextField(blank=True)

    format        = models.CharField(max_length=10, choices=ReportTemplate.FORMAT_CHOICES, default='pdf')
    include_charts = models.BooleanField(default=True)
    include_tables = models.BooleanField(default=True)

    is_active     = models.BooleanField(default=True)
    last_run      = models.DateTimeField(null=True, blank=True)
    next_run      = models.DateTimeField(null=True, blank=True)

    created_by    = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_schedules')
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['next_run', 'name']
        verbose_name = "Scheduled Report"
        verbose_name_plural = "Scheduled Reports"

    def __str__(self):
        return f"{self.name} ({self.get_schedule_type_display()})"

    def save(self, *args, **kwargs):
        if not self.next_run:
            self.calculate_next_run()
        super().save(*args, **kwargs)

    def calculate_next_run(self):
        from datetime import datetime, timedelta
        import calendar

        now = timezone.now()
        base = now.replace(minute=self.minute, second=0, microsecond=0)

        if self.schedule_type == 'daily':
            next_date = base.replace(hour=self.hour)
            if next_date <= now:
                next_date += timedelta(days=1)

        elif self.schedule_type == 'weekly':
            days_ahead = (self.day_of_week - now.weekday()) % 7
            if days_ahead == 0 and base.time() <= now.time():
                days_ahead = 7
            next_date = now + timedelta(days=days_ahead)
            next_date = next_date.replace(hour=self.hour, minute=self.minute, second=0, microsecond=0)

        elif self.schedule_type == 'monthly':
            year, month = now.year, now.month
            day = min(self.day_of_month or 1, calendar.monthrange(year, month)[1])
            next_date = now.replace(day=day, hour=self.hour, minute=self.minute, second=0, microsecond=0)
            if next_date <= now:
                month += 1
                if month > 12:
                    month = 1
                    year += 1
                day = min(self.day_of_month or 1, calendar.monthrange(year, month)[1])
                next_date = now.replace(year=year, month=month, day=day, hour=self.hour, minute=self.minute, second=0, microsecond=0)

        elif self.schedule_type == 'quarterly':
            # Every 3 months on the same day/hour
            quarter = ((now.month - 1) // 3) + 1
            next_quarter = quarter + 1 if quarter < 4 else 1
            next_month = (next_quarter - 1) * 3 + 1
            year = now.year + (1 if next_quarter == 1 else 0)
            day = min(self.day_of_month or 1, calendar.monthrange(year, next_month)[1])
            next_date = now.replace(year=year, month=next_month, day=day, hour=self.hour, minute=self.minute, second=0, microsecond=0)
            if next_date <= now:
                next_date += timedelta(days=90)  # rough fallback

        else:
            next_date = now + timedelta(days=1)  # fallback

        self.next_run = next_date


class DashboardWidget(CompanyModel):
    """User-configurable dashboard widgets linked to reports"""

    WIDGET_TYPES = [
        ('kpi',      'KPI Card'),
        ('chart',    'Chart'),
        ('table',    'Table Preview'),
        ('list',     'Record List'),
        ('number',   'Single Number'),
        ('custom',   'Custom HTML/JS'),
    ]

    SIZES = [
        ('small',  '1×1'),
        ('medium', '2×1'),
        ('large',  '2×2'),
        ('full',   'Full Width'),
    ]

    user     = models.ForeignKey(User, on_delete=models.CASCADE, related_name='dashboard_widgets')
    title    = models.CharField(max_length=120)
    widget_type = models.CharField(max_length=20, choices=WIDGET_TYPES)
    report   = models.ForeignKey(ReportTemplate, on_delete=models.SET_NULL, null=True, blank=True)
    size     = models.CharField(max_length=10, choices=SIZES, default='medium')
    position = models.PositiveIntegerField(default=0)
    config   = models.JSONField(default=dict, blank=True)  # chart type, colors, filters, etc.
    is_visible = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['position']
        unique_together = ['user', 'position']
        verbose_name = "Dashboard Widget"
        verbose_name_plural = "Dashboard Widgets"

    def __str__(self):
        return f"{self.title} – {self.user.username}"