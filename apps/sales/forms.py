from django import forms
from django.forms import inlineformset_factory
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta

from .models import SalesPayment, SalesInvoice, SalesOrder, SalesInvoiceLine, SalesOrderLine
from apps.company.models import Customer
from apps.core.models import Item, Unit
from apps.inventory.models import Warehouse


class SalesPaymentForm(forms.ModelForm):
    """Form for recording payments against invoices"""
    
    # Read-only fields for display
    customer_name = forms.CharField(
        label="Customer", 
        required=False, 
        widget=forms.TextInput(attrs={'readonly': 'readonly', 'class': 'form-control bg-light'})
    )
    invoice_total = forms.DecimalField(
        label="Invoice Total", 
        required=False, 
        widget=forms.TextInput(attrs={'readonly': 'readonly', 'class': 'form-control bg-light'})
    )
    remaining = forms.DecimalField(
        label="Remaining Balance", 
        required=False, 
        widget=forms.TextInput(attrs={'readonly': 'readonly', 'class': 'form-control bg-light'})
    )
    payment_status = forms.CharField(
        label="Payment Status", 
        required=False, 
        widget=forms.TextInput(attrs={'readonly': 'readonly', 'class': 'form-control bg-light'})
    )

    class Meta:
        model = SalesPayment
        fields = ['invoice', 'payment_date', 'amount', 'payment_method', 'reference']
        widgets = {
            'invoice': forms.Select(attrs={'class': 'form-select'}),
            'payment_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'payment_method': forms.Select(attrs={'class': 'form-select'}),
            'reference': forms.TextInput(attrs={'class': 'form-control'}),
        }

    class Media:
        js = ('sales/js/payment_form.js',)

    def __init__(self, *args, **kwargs):
        company = kwargs.pop('company', None)
        super().__init__(*args, **kwargs)
        
        # Filter invoices by company if provided
        if company and 'invoice' in self.fields:
            self.fields['invoice'].queryset = SalesInvoice.objects.filter(
                company=company, 
                status__in=['posted', 'partial', 'overdue']
            ).select_related('customer')
        
        # Populate initial data when instance exists
        invoice = None
        if self.instance and self.instance.invoice_id:
            invoice = self.instance.invoice
        elif 'invoice' in self.initial:
            try:
                invoice = SalesInvoice.objects.get(pk=self.initial['invoice'])
            except SalesInvoice.DoesNotExist:
                invoice = None

        if invoice:
            self.fields['customer_name'].initial = invoice.customer.name if invoice.customer else ''
            self.fields['invoice_total'].initial = invoice.total_amount
            remaining = invoice.total_amount - invoice.paid_amount
            self.fields['remaining'].initial = remaining
            self.fields['payment_status'].initial = 'Fully Paid' if remaining <= 0 else f'Remaining: {remaining}'
            
            # Set max amount to remaining balance
            self.fields['amount'].widget.attrs['max'] = float(remaining)
            self.fields['amount'].help_text = f"Maximum amount: {remaining}"
        
        # Insert the extra fields into field order
        new_order = ['invoice', 'customer_name', 'invoice_total', 'remaining', 'payment_status',
                     'payment_date', 'amount', 'payment_method', 'reference']
        self.order_fields(new_order)
    
    def clean_amount(self):
        """Validate that amount doesn't exceed remaining balance"""
        amount = self.cleaned_data.get('amount')
        invoice = self.cleaned_data.get('invoice')
        
        if invoice and amount:
            remaining = invoice.total_amount - invoice.paid_amount
            if amount > remaining:
                raise forms.ValidationError(
                    f"Amount cannot exceed remaining balance of {remaining}"
                )
        return amount


class SalesInvoiceForm(forms.ModelForm):
    """Form for creating/editing sales invoices"""
    
    invoice_type = forms.ChoiceField(
        choices=[('credit', 'Credit Invoice'), ('cash', 'Cash Invoice')],
        initial='credit',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = SalesInvoice
        fields = ['customer', 'sales_order', 'invoice_date', 'due_date', 'tax_rate', 'payment_method', 'notes']
        widgets = {
            'customer': forms.Select(attrs={'class': 'form-select select2'}),
            'sales_order': forms.Select(attrs={'class': 'form-select select2'}),
            'invoice_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'due_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'tax_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'payment_method': forms.Select(attrs={'class': 'form-select'}),
        }
    
    def __init__(self, *args, **kwargs):
        company = kwargs.pop('company', None)
        super().__init__(*args, **kwargs)
        
        if company:
            # Filter customers by company
            self.fields['customer'].queryset = Customer.objects.filter(
                company=company, 
                is_active=True
            ).order_by('name')
            
            # Filter sales orders by company
            self.fields['sales_order'].queryset = SalesOrder.objects.filter(
                company=company, 
                status__in=['confirmed', 'processing', 'shipped']
            ).order_by('-order_date').select_related('customer')
        
        self.fields['sales_order'].required = False
        self.fields['customer'].required = True
        
        # Set default dates if not set
        if not self.instance.pk:
            self.fields['invoice_date'].initial = timezone.now().date()
            self.fields['due_date'].initial = timezone.now().date() + timedelta(days=30)
    
    def clean(self):
        cleaned_data = super().clean()
        invoice_date = cleaned_data.get('invoice_date')
        due_date = cleaned_data.get('due_date')
        
        if invoice_date and due_date and due_date < invoice_date:
            raise forms.ValidationError("Due date cannot be before invoice date.")
        
        # If sales order is selected, ensure customer matches
        sales_order = cleaned_data.get('sales_order')
        customer = cleaned_data.get('customer')
        
        if sales_order and customer and sales_order.customer != customer:
            raise forms.ValidationError(
                "Customer must match the customer on the selected sales order."
            )
        
        return cleaned_data


class SalesInvoiceLineForm(forms.ModelForm):
    """Form for sales invoice line items"""
    
    class Meta:
        model = SalesInvoiceLine
        fields = ['item', 'quantity', 'unit', 'unit_price']
        widgets = {
            'item': forms.Select(attrs={'class': 'form-select item-select', 'required': True}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control quantity', 'step': '0.01', 'min': '0.01'}),
            'unit': forms.Select(attrs={'class': 'form-select unit-select'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control unit-price', 'step': '0.01', 'min': '0'}),
        }
    
    def __init__(self, *args, **kwargs):
        company = kwargs.pop('company', None)
        super().__init__(*args, **kwargs)
        
        if company:
            # Filter items by company (include legacy items)
            self.fields['item'].queryset = Item.objects.filter(
                Q(company=company) | Q(company__isnull=True),
                is_active=True
            ).order_by('code').select_related('unit')
            
            # Filter units by company (include legacy units)
            self.fields['unit'].queryset = Unit.objects.filter(
                Q(company=company) | Q(company__isnull=True),
                is_active=True
            ).order_by('name')
        
        # Make unit not required initially, will use item's default unit if not selected
        self.fields['unit'].required = False
        
        # Set default quantity
        if not self.instance.pk:
            self.fields['quantity'].initial = 1
    
    def clean_quantity(self):
        """Validate quantity is positive"""
        quantity = self.cleaned_data.get('quantity')
        if quantity and quantity <= 0:
            raise forms.ValidationError("Quantity must be greater than zero.")
        return quantity
    
    def clean_unit_price(self):
        """Validate unit price is not negative"""
        unit_price = self.cleaned_data.get('unit_price')
        if unit_price and unit_price < 0:
            raise forms.ValidationError("Unit price cannot be negative.")
        return unit_price


# Create the inline formset for invoice lines
SalesInvoiceLineFormSet = inlineformset_factory(
    SalesInvoice,
    SalesInvoiceLine,
    form=SalesInvoiceLineForm,
    fields=['item', 'quantity', 'unit', 'unit_price'],
    extra=1,
    can_delete=True,
    min_num=1,
    validate_min=True
)


class SalesOrderForm(forms.ModelForm):
    """Form for creating/editing sales orders"""
    
    class Meta:
        model = SalesOrder
        fields = ['customer', 'order_date', 'expected_ship_date', 'tax_rate', 'notes', 'terms_conditions']
        widgets = {
            'customer': forms.Select(attrs={'class': 'form-select select2'}),
            'order_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'expected_ship_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'terms_conditions': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'tax_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
        }
    
    def __init__(self, *args, **kwargs):
        company = kwargs.pop('company', None)
        super().__init__(*args, **kwargs)
        
        if company:
            self.fields['customer'].queryset = Customer.objects.filter(
                company=company, 
                is_active=True
            ).order_by('name')
        
        if not self.instance.pk:
            self.fields['order_date'].initial = timezone.now().date()
            self.fields['tax_rate'].initial = 15


class SalesOrderLineForm(forms.ModelForm):
    """Form for sales order line items"""
    
    class Meta:
        model = SalesOrderLine
        fields = ['item', 'quantity', 'unit', 'unit_price', 'warehouse']
        widgets = {
            'item': forms.Select(attrs={'class': 'form-select item-select', 'required': True}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control quantity', 'step': '0.01', 'min': '0.01'}),
            'unit': forms.Select(attrs={'class': 'form-select unit-select'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control unit-price', 'step': '0.01', 'min': '0'}),
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
        }
    
    def __init__(self, *args, **kwargs):
        company = kwargs.pop('company', None)
        super().__init__(*args, **kwargs)
        
        if company:
            self.fields['item'].queryset = Item.objects.filter(
                Q(company=company) | Q(company__isnull=True),
                is_active=True
            ).order_by('code')
            
            self.fields['unit'].queryset = Unit.objects.filter(
                Q(company=company) | Q(company__isnull=True),
                is_active=True
            ).order_by('name')
            
            self.fields['warehouse'].queryset = Warehouse.objects.filter(
                company=company,
                is_active=True
            ).order_by('name')
        
        self.fields['unit'].required = False
        self.fields['warehouse'].required = False


SalesOrderLineFormSet = inlineformset_factory(
    SalesOrder,
    SalesOrderLine,
    form=SalesOrderLineForm,
    fields=['item', 'quantity', 'unit', 'unit_price', 'warehouse'],
    extra=1,
    can_delete=True,
    min_num=1,
    validate_min=True
)