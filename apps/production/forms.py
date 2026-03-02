from django import forms
from django.utils import timezone
from decimal import Decimal

from .models import ProductionRun, BOM
from apps.core.models import Item  # Add this import
from apps.inventory.models import Warehouse


class StartProductionRunForm(forms.ModelForm):
    """Form for starting a new production run"""
    
    transfer_to_warehouse = forms.ModelChoiceField(
        queryset=Warehouse.objects.filter(is_active=True),
        required=False,
        label="Transfer to Warehouse",
        help_text="Optional: Select warehouse to transfer materials to (e.g., Production Floor)"
    )
    
    class Meta:
        model = ProductionRun
        fields = ['bom', 'planned_quantity', 'notes']
        widgets = {
            'planned_quantity': forms.NumberInput(attrs={
                'step': '0.001', 
                'min': '0.001',
                'class': 'form-control',
                'placeholder': 'Enter planned quantity'
            }),
            'notes': forms.Textarea(attrs={
                'rows': 3,
                'class': 'form-control',
                'placeholder': 'Optional notes about this production run'
            }),
        }
        labels = {
            'bom': 'Bill of Materials',
            'planned_quantity': 'Planned Quantity',
            'notes': 'Production Notes',
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Filter BOMs to only active ones
        self.fields['bom'].queryset = BOM.objects.filter(is_active=True).select_related('product')
        self.fields['bom'].widget.attrs.update({'class': 'form-control'})
        
        # Add help text
        self.fields['bom'].help_text = "Select the Bill of Materials for this production run"
        
        # Initialize material requirements (will be populated via JavaScript)
        self.material_requirements = []

    def clean_planned_quantity(self):
        """Validate planned quantity"""
        quantity = self.cleaned_data.get('planned_quantity')
        if quantity <= 0:
            raise forms.ValidationError("Planned quantity must be greater than zero.")
        return quantity

    def clean(self):
        """Validate BOM selection and check stock availability"""
        cleaned_data = super().clean()
        bom = cleaned_data.get('bom')
        planned_quantity = cleaned_data.get('planned_quantity')
        
        if bom and planned_quantity:
            # Check if all components have sufficient stock
            insufficient = []
            self.material_requirements = []
            
            for line in bom.lines.all().select_related('component', 'unit'):
                required = line.quantity_per_kg * planned_quantity
                required_with_wastage = required * (1 + line.wastage_percentage / 100)
                
                # Store requirement for display
                self.material_requirements.append({
                    'component': line.component,
                    'required': required,
                    'required_with_wastage': required_with_wastage,
                    'unit': line.unit,
                    'available': line.component.current_stock,
                    'wastage': line.wastage_percentage,
                })
                
                if line.component.current_stock < required_with_wastage:
                    insufficient.append({
                        'code': line.component.code,
                        'name': line.component.name,
                        'required': required_with_wastage,
                        'available': line.component.current_stock,
                        'deficit': required_with_wastage - line.component.current_stock,
                        'unit': line.unit.abbreviation,
                    })
            
            if insufficient:
                # Create detailed error message
                error_msg = "Insufficient stock for the following components:\n"
                for item in insufficient:
                    error_msg += f"  • {item['code']} - {item['name']}: Need {item['required']:.2f} {item['unit']}, "
                    error_msg += f"Have {item['available']:.2f} {item['unit']} (Deficit: {item['deficit']:.2f})\n"
                
                # Store in cleaned_data for template access
                cleaned_data['insufficient_materials'] = insufficient
                raise forms.ValidationError(error_msg)
            
            # Calculate estimated material cost
            total_cost = 0
            for req in self.material_requirements:
                component_cost = req['required_with_wastage'] * (req['component'].unit_cost or 0)
                total_cost += component_cost
            
            cleaned_data['estimated_cost'] = total_cost
        
        return cleaned_data


class CompleteProductionRunForm(forms.Form):
    """Form for completing a production run"""
    
    actual_quantity = forms.DecimalField(
        max_digits=15,
        decimal_places=4,
        min_value=0.001,
        label="Actual Produced Quantity",
        widget=forms.NumberInput(attrs={
            'step': '0.001',
            'min': '0.001',
            'class': 'form-control',
            'placeholder': 'Enter actual quantity produced'
        })
    )
    
    completion_date = forms.DateField(
        initial=timezone.now().date,
        label="Completion Date",
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control'
        })
    )
    
    waste_quantity = forms.DecimalField(
        max_digits=15,
        decimal_places=4,
        required=False,
        min_value=0,
        label="Waste/Scrap Quantity",
        help_text="Optional: Quantity of waste/scrap generated",
        widget=forms.NumberInput(attrs={
            'step': '0.001',
            'min': '0',
            'class': 'form-control'
        })
    )
    
    notes = forms.CharField(
        required=False,
        label="Completion Notes",
        widget=forms.Textarea(attrs={
            'rows': 3,
            'class': 'form-control',
            'placeholder': 'Any notes about the production completion'
        })
    )
    
    transfer_to_warehouse = forms.ModelChoiceField(
        queryset=Warehouse.objects.filter(is_active=True),
        required=True,
        label="Transfer Finished Goods to Warehouse",
        help_text="Select warehouse to store finished products",
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    def __init__(self, *args, **kwargs):
        self.production_run = kwargs.pop('production_run', None)
        super().__init__(*args, **kwargs)
        
        # Set initial actual quantity from planned if available
        if self.production_run:
            self.fields['actual_quantity'].initial = self.production_run.planned_quantity
            
        # Add yield calculation field (readonly, will be updated via JavaScript)
        self.fields['yield_percentage'] = forms.DecimalField(
            required=False,
            disabled=True,
            label="Yield %",
            widget=forms.NumberInput(attrs={'class': 'form-control', 'readonly': 'readonly'})
        )

    def clean(self):
        """Validate completion data"""
        cleaned_data = super().clean()
        actual_qty = cleaned_data.get('actual_quantity')
        waste_qty = cleaned_data.get('waste_quantity') or 0
        
        if actual_qty and waste_qty:
            total_output = actual_qty + waste_qty
            if self.production_run and total_output > self.production_run.planned_quantity * 1.2:  # Allow 20% overage
                raise forms.ValidationError(
                    f"Total output ({total_output}) exceeds planned quantity "
                    f"({self.production_run.planned_quantity}) by more than 20%."
                )
        
        return cleaned_data


class MaterialTransferForm(forms.Form):
    """Form for transferring materials to production"""
    
    transfer_date = forms.DateField(
        initial=timezone.now().date,
        label="Transfer Date",
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    
    from_warehouse = forms.ModelChoiceField(
        queryset=Warehouse.objects.filter(is_active=True),
        required=True,
        label="From Warehouse",
        help_text="Source warehouse for materials",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    to_warehouse = forms.ModelChoiceField(
        queryset=Warehouse.objects.filter(is_active=True, warehouse_type='wip'),
        required=True,
        label="To Warehouse",
        help_text="Destination warehouse (usually Production/WIP)",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    reference = forms.CharField(
        max_length=100,
        required=False,
        label="Reference Number",
        help_text="Optional: Reference number for this transfer",
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    
    notes = forms.CharField(
        required=False,
        label="Transfer Notes",
        widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control'})
    )

    def clean(self):
        """Validate warehouses are different"""
        cleaned_data = super().clean()
        from_wh = cleaned_data.get('from_warehouse')
        to_wh = cleaned_data.get('to_warehouse')
        
        if from_wh and to_wh and from_wh == to_wh:
            raise forms.ValidationError("From and To warehouses must be different.")
        
        return cleaned_data


class ProductionSearchForm(forms.Form):
    """Form for searching/filtering production runs"""
    
    search = forms.CharField(
        required=False,
        label="Search",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search by product name, code, or notes...'
        })
    )
    
    status = forms.ChoiceField(
        required=False,
        choices=[('', 'All Status')] + ProductionRun.STATUS_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    date_from = forms.DateField(
        required=False,
        label="From Date",
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    
    date_to = forms.DateField(
        required=False,
        label="To Date",
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    
    product = forms.ModelChoiceField(
        queryset=Item.objects.filter(category='finished', is_active=True),  # Now Item is defined
        required=False,
        label="Product",
        widget=forms.Select(attrs={'class': 'form-control'})
    )