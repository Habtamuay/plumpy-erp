from django import forms
from .models import SalesPayment, SalesInvoice


class SalesPaymentForm(forms.ModelForm):
    # additional read-only fields for display
    customer_name = forms.CharField(label="Customer", required=False, widget=forms.TextInput(attrs={'readonly': 'readonly'}))
    invoice_total = forms.DecimalField(label="Invoice Total", required=False, widget=forms.TextInput(attrs={'readonly': 'readonly'}))
    remaining = forms.DecimalField(label="Remaining", required=False, widget=forms.TextInput(attrs={'readonly': 'readonly'}))
    payment_status = forms.CharField(label="Payment Status", required=False, widget=forms.TextInput(attrs={'readonly': 'readonly'}))

    class Meta:
        model = SalesPayment
        fields = ['invoice', 'payment_date', 'amount', 'payment_method', 'reference']

    class Media:
        js = ('sales/js/payment_form.js',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # populate initial data when instance exists
        invoice = None
        if self.instance and self.instance.invoice_id:
            invoice = self.instance.invoice
        elif 'invoice' in self.initial:
            try:
                invoice = SalesInvoice.objects.get(pk=self.initial['invoice'])
            except SalesInvoice.DoesNotExist:
                invoice = None

        if invoice:
            self.fields['customer_name'].initial = invoice.customer.name
            self.fields['invoice_total'].initial = invoice.total_amount
            self.fields['remaining'].initial = invoice.total_amount - invoice.paid_amount
            self.fields['payment_status'].initial = 'Fully Paid' if invoice.paid_amount >= invoice.total_amount else 'Partial'
        
        # insert the extra fields into field order
        new_order = ['invoice', 'customer_name', 'invoice_total', 'remaining', 'payment_status',
                     'payment_date', 'amount', 'payment_method', 'reference']
        self.order_fields(new_order)
