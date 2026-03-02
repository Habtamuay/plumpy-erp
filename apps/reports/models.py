from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, MaxValueValidator
import json

User = get_user_model()


class ReportCategory(models.Model):
    """Category for organizing reports"""
    name = models.CharField(max_length=100, unique=True)
    icon = models.CharField(max_length=50, blank=True, help_text="Font Awesome icon class")
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


class ReportTemplate(models.Model):
    """Template for generating reports"""
    
    REPORT_TYPES = [
        # Inventory Reports
        ('inventory_stock_summary', 'Stock Summary'),
        ('inventory_stock_value', 'Stock Value'),
        ('inventory_stock_aging', 'Stock Aging'),
        ('inventory_low_stock', 'Low Stock Alert'),
        ('inventory_expiry', 'Expiry Report'),
        ('inventory_movements', 'Stock Movements'),
        ('inventory_reorder', 'Reorder Analysis'),
        
        # Production Reports
        ('production_runs', 'Production Runs'),
        ('production_cost_variance', 'Cost Variance'),
        ('production_yield', 'Production Yield'),
        ('production_efficiency', 'Production Efficiency'),
        ('production_material_consumption', 'Material Consumption'),
        ('production_downtime', 'Downtime Analysis'),
        
        # Purchasing Reports
        ('purchasing_po_summary', 'Purchase Order Summary'),
        ('purchasing_supplier_performance', 'Supplier Performance'),
        ('purchasing_spend_analysis', 'Spend Analysis'),
        ('purchasing_lead_time', 'Lead Time Analysis'),
        ('purchasing_price_trend', 'Price Trend'),
        
        # Sales Reports
        ('sales_order_summary', 'Sales Order Summary'),
        ('sales_invoice_summary', 'Sales Invoice Summary'),
        ('sales_customer_performance', 'Customer Performance'),
        ('sales_revenue_analysis', 'Revenue Analysis'),
        ('sales_product_sales', 'Product Sales'),
        ('sales_forecast', 'Sales Forecast'),
        
        # Financial Reports
        ('financial_profit_loss', 'Profit & Loss'),
        ('financial_balance_sheet', 'Balance Sheet'),
        ('financial_cash_flow', 'Cash Flow'),
        ('financial_trial_balance', 'Trial Balance'),
        ('financial_accounts_receivable', 'Accounts Receivable Aging'),
        ('financial_accounts_payable', 'Accounts Payable Aging'),
        ('financial_budget_variance', 'Budget vs Actual'),
        
        # Company Reports
        ('company_customer_list', 'Customer List'),
        ('company_supplier_list', 'Supplier List'),
        ('company_user_activity', 'User Activity'),
        
        # Custom Reports
        ('custom_sql', 'Custom SQL Report'),
        ('custom_aggregate', 'Custom Aggregate'),
    ]
    
    FORMAT_CHOICES = [
        ('pdf', 'PDF'),
        ('excel', 'Excel'),
        ('csv', 'CSV'),
        ('html', 'HTML'),
        ('json', 'JSON'),
    ]

    category = models.ForeignKey(ReportCategory, on_delete=models.PROTECT, related_name='reports')
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    report_type = models.CharField(max_length=50, choices=REPORT_TYPES)
    format = models.CharField(max_length=10, choices=FORMAT_CHOICES, default='pdf')
    
    # Template configuration
    template_file = models.CharField(max_length=255, blank=True, help_text="Path to custom template")
    query_config = models.JSONField(default=dict, blank=True, help_text="JSON configuration for report query")
    
    # Display settings
    icon = models.CharField(max_length=50, blank=True, default='bi-file-earmark-text')
    color = models.CharField(max_length=20, blank=True, default='primary')
    
    # System report (cannot be deleted)
    is_system = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    
    # Metadata
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category__display_order', 'name']
        verbose_name = "Report Template"
        verbose_name_plural = "Report Templates"

    def __str__(self):
        return self.name


class ScheduledReport(models.Model):
    """Schedule reports to run automatically"""
    
    SCHEDULE_TYPES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('yearly', 'Yearly'),
        ('custom', 'Custom'),
    ]

    name = models.CharField(max_length=200)
    report = models.ForeignKey(ReportTemplate, on_delete=models.CASCADE, related_name='schedules')
    description = models.TextField(blank=True)
    
    # Schedule configuration
    schedule_type = models.CharField(max_length=20, choices=SCHEDULE_TYPES)
    hour = models.PositiveSmallIntegerField(default=8, validators=[MinValueValidator(0), MaxValueValidator(23)])
    day_of_month = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(31)], blank=True, null=True)
    day_of_week = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(0), MaxValueValidator(6)], blank=True, null=True, help_text="0=Monday, 6=Sunday")
    time = models.TimeField(default="08:00")
    
    # Recipients
    recipients = models.TextField(help_text="Comma-separated email addresses")
    email_subject = models.CharField(max_length=255, blank=True)
    email_body = models.TextField(blank=True)
    
    # Output options
    format = models.CharField(max_length=10, choices=ReportTemplate.FORMAT_CHOICES, default='pdf')
    include_charts = models.BooleanField(default=True)
    include_tables = models.BooleanField(default=True)
    
    # Status
    is_active = models.BooleanField(default=True)
    last_run = models.DateTimeField(null=True, blank=True)
    next_run = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_schedules')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['next_run']
        verbose_name = "Scheduled Report"
        verbose_name_plural = "Scheduled Reports"

    def __str__(self):
        return f"{self.name} ({self.get_schedule_type_display()})"

    def save(self, *args, **kwargs):
        # Calculate next run
        if not self.next_run:
            self.calculate_next_run()
        super().save(*args, **kwargs)

    def calculate_next_run(self):
        """Calculate next run datetime based on schedule"""
        from datetime import datetime, timedelta
        import calendar
        
        now = timezone.now()
        
        if self.schedule_type == 'daily':
            next_date = now.replace(hour=self.hour, minute=0, second=0, microsecond=0)
            if next_date <= now:
                next_date += timedelta(days=1)
        
        elif self.schedule_type == 'weekly':
            days_ahead = (self.day_of_week - now.weekday()) % 7
            next_date = (now + timedelta(days=days_ahead)).replace(hour=self.hour, minute=0, second=0, microsecond=0)
            if next_date <= now:
                next_date += timedelta(days=7)
        
        elif self.schedule_type == 'monthly':
            year = now.year
            month = now.month
            last_day = calendar.monthrange(year, month)[1]
            day = min(self.day_of_month, last_day)
            
            next_date = now.replace(day=day, hour=self.hour, minute=0, second=0, microsecond=0)
            if next_date <= now:
                if month == 12:
                    year += 1
                    month = 1
                else:
                    month += 1
                last_day = calendar.monthrange(year, month)[1]
                day = min(self.day_of_month, last_day)
                next_date = now.replace(year=year, month=month, day=day, hour=self.hour, minute=0, second=0, microsecond=0)
        
        else:
            # Default to daily
            next_date = now.replace(hour=self.hour, minute=0, second=0, microsecond=0)
            if next_date <= now:
                next_date += timedelta(days=1)
        
        self.next_run = next_date


class DashboardWidget(models.Model):
    """Customizable dashboard widgets"""
    
    WIDGET_TYPES = [
        ('chart', 'Chart'),
        ('table', 'Table'),
        ('kpi', 'KPI Card'),
        ('list', 'List'),
        ('calendar', 'Calendar'),
        ('custom', 'Custom HTML'),
    ]
    
    SIZES = [
        ('small', 'Small'),
        ('medium', 'Medium'),
        ('large', 'Large'),
        ('full', 'Full Width'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='dashboard_widgets')
    title = models.CharField(max_length=100)
    widget_type = models.CharField(max_length=20, choices=WIDGET_TYPES)
    report = models.ForeignKey(ReportTemplate, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Layout
    size = models.CharField(max_length=10, choices=SIZES, default='medium')
    position = models.PositiveIntegerField(default=0)
    
    # Configuration (JSON)
    config = models.JSONField(default=dict, blank=True)
    
    # Visibility
    is_visible = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['position']
        unique_together = ['user', 'position']
        verbose_name = "Dashboard Widget"
        verbose_name_plural = "Dashboard Widgets"

    def __str__(self):
        return f"{self.title} - {self.user.username}"