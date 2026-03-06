from django import forms
from django.utils import timezone
from django.db import models
from .models import ReportTemplate, ScheduledReport, DashboardWidget, ReportCategory


class ReportFilterForm(forms.Form):
    """Base form for report filters"""
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    
    def clean(self):
        cleaned_data = super().clean()
        date_from = cleaned_data.get('date_from')
        date_to = cleaned_data.get('date_to')
        
        if date_from and date_to and date_from > date_to:
            raise forms.ValidationError("Start date cannot be after end date.")
        
        return cleaned_data


class InventoryReportFilterForm(ReportFilterForm):
    """Filter form for inventory reports"""
    warehouse = forms.ChoiceField(
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    category = forms.ChoiceField(
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    item = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Search item...'})
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.inventory.models import Warehouse
        from apps.core.models import Item
        
        warehouses = Warehouse.objects.filter(is_active=True)
        self.fields['warehouse'].choices = [('', 'All Warehouses')] + [(w.id, w.name) for w in warehouses]
        
        categories = Item.ITEM_CATEGORY
        self.fields['category'].choices = [('', 'All Categories')] + list(categories)


class ProductionReportFilterForm(ReportFilterForm):
    """Filter form for production reports"""
    product = forms.ChoiceField(
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    status = forms.ChoiceField(
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.core.models import Item
        from apps.production.models import ProductionRun
        
        # include finished items plus any product referenced by a run (even if category differs)
        prod_ids = ProductionRun.objects.values_list('product_id', flat=True).distinct()
        products = Item.objects.filter(is_active=True).filter(
            models.Q(category='finished') | models.Q(id__in=prod_ids)
        )
        self.fields['product'].choices = [('', 'All Products')] + [(p.id, p.name) for p in products.distinct()]
        
        self.fields['status'].choices = [('', 'All Status')] + list(ProductionRun.STATUS_CHOICES)


class PurchasingReportFilterForm(ReportFilterForm):
    """Filter form for purchasing reports"""
    supplier = forms.ChoiceField(
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    status = forms.ChoiceField(
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.purchasing.models import Supplier, PurchaseOrder
        
        suppliers = Supplier.objects.filter(is_active=True)
        self.fields['supplier'].choices = [('', 'All Suppliers')] + [(s.id, s.name) for s in suppliers]
        
        self.fields['status'].choices = [('', 'All Status')] + list(PurchaseOrder.STATUS_CHOICES)


class SalesReportFilterForm(ReportFilterForm):
    """Filter form for sales reports"""
    customer = forms.ChoiceField(
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    product = forms.ChoiceField(
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    status = forms.ChoiceField(
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.company.models import Customer
        from apps.core.models import Item
        from apps.sales.models import SalesOrder
        
        customers = Customer.objects.filter(is_active=True)
        self.fields['customer'].choices = [('', 'All Customers')] + [(c.id, c.name) for c in customers]
        
        products = Item.objects.filter(category='finished', is_active=True)
        self.fields['product'].choices = [('', 'All Products')] + [(p.id, p.name) for p in products]
        
        self.fields['status'].choices = [('', 'All Status')] + list(SalesOrder.STATUS_CHOICES)


class FinancialReportFilterForm(ReportFilterForm):
    """Filter form for financial reports"""
    account_type = forms.ChoiceField(
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    period = forms.ChoiceField(
        required=False,
        choices=[
            ('', 'Custom Period'),
            ('today', 'Today'),
            ('this_week', 'This Week'),
            ('this_month', 'This Month'),
            ('this_quarter', 'This Quarter'),
            ('this_year', 'This Year'),
            ('last_month', 'Last Month'),
            ('last_quarter', 'Last Quarter'),
            ('last_year', 'Last Year'),
        ],
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.accounting.models import AccountType
        
        account_types = AccountType.objects.filter(is_active=True)
        self.fields['account_type'].choices = [('', 'All Account Types')] + [(at.id, at.name) for at in account_types]
    
    def clean(self):
        cleaned_data = super().clean()
        period = cleaned_data.get('period')
        
        if period and period != '':
            from datetime import datetime, timedelta
            today = timezone.now().date()
            
            period_map = {
                'today': (today, today),
                'this_week': (today - timedelta(days=today.weekday()), today),
                'this_month': (today.replace(day=1), today),
                'this_quarter': (today.replace(month=((today.month-1)//3)*3+1, day=1), today),
                'this_year': (today.replace(month=1, day=1), today),
                'last_month': ((today.replace(day=1) - timedelta(days=1)).replace(day=1), today.replace(day=1) - timedelta(days=1)),
                'last_quarter': (today.replace(month=((today.month-4)//3)*3+1, day=1), today.replace(month=((today.month-1)//3)*3+1, day=1) - timedelta(days=1)),
                'last_year': (today.replace(year=today.year-1, month=1, day=1), today.replace(year=today.year-1, month=12, day=31)),
            }
            
            if period in period_map:
                cleaned_data['date_from'], cleaned_data['date_to'] = period_map[period]
        
        return cleaned_data


class ScheduledReportForm(forms.ModelForm):
    """Form for creating/editing scheduled reports"""
    
    class Meta:
        model = ScheduledReport
        fields = [
            'name', 'report', 'description', 'schedule_type', 'hour',
            'day_of_month', 'day_of_week', 'time', 'recipients',
            'email_subject', 'email_body', 'format', 'include_charts',
            'include_tables', 'is_active'
        ]
        widgets = {
            'time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'recipients': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'email_body': forms.Textarea(attrs={'rows': 5, 'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            if field not in ['email_body']:
                self.fields[field].widget.attrs.update({'class': 'form-control'})
    
    def clean_recipients(self):
        recipients = self.cleaned_data['recipients']
        emails = [email.strip() for email in recipients.split(',')]
        for email in emails:
            if email and '@' not in email:
                raise forms.ValidationError(f"Invalid email address: {email}")
        return recipients


class DashboardWidgetForm(forms.ModelForm):
    """Form for adding/editing dashboard widgets"""
    
    class Meta:
        model = DashboardWidget
        fields = ['title', 'widget_type', 'report', 'size', 'config', 'is_visible']
        widgets = {
            'config': forms.Textarea(attrs={'rows': 5, 'class': 'form-control font-monospace'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            if field != 'config':
                self.fields[field].widget.attrs.update({'class': 'form-control'})
    
    def clean_config(self):
        config = self.cleaned_data['config']
        if config:
            try:
                import json
                if isinstance(config, str):
                    json.loads(config)
            except json.JSONDecodeError:
                raise forms.ValidationError("Invalid JSON format")
        return config