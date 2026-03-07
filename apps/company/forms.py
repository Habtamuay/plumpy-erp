from django import forms
from .models import Company, Branch, Department, Customer, UserProfile


class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = [
            'name', 'legal_name', 'tin_number', 'registration_number',
            'address', 'city', 'country', 'phone', 'email', 'website',
            'logo', 'fiscal_year_start', 'fiscal_year_end', 'base_currency'
        ]
        widgets = {
            'fiscal_year_start': forms.DateInput(attrs={'type': 'date'}),
            'fiscal_year_end': forms.DateInput(attrs={'type': 'date'}),
            'address': forms.Textarea(attrs={'rows': 3}),
        }


class BranchForm(forms.ModelForm):
    class Meta:
        model = Branch
        fields = [
            'company', 'name', 'code', 'address', 'city', 'country',
            'phone', 'email', 'is_main'
        ]
        widgets = {
            'address': forms.Textarea(attrs={'rows': 3}),
        }


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ['company', 'name', 'code', 'description', 'manager']


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = [
            'company', 'name', 'customer_type', 'tin', 'address',
            'city', 'country', 'phone', 'email', 'credit_limit', 'payment_terms'
        ]
        widgets = {
            'address': forms.Textarea(attrs={'rows': 3}),
        }


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = [
            'company', 'user', 'employee_id', 'department', 'branch',
            'job_title', 'role', 'hire_date', 'phone', 'address'
        ]
        widgets = {
            'hire_date': forms.DateInput(attrs={'type': 'date'}),
            'address': forms.Textarea(attrs={'rows': 3}),
        }