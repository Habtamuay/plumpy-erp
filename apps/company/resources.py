from import_export import resources
from .models import Company, Branch, Department, Customer, UserProfile


class CompanyResource(resources.ModelResource):
    class Meta:
        model = Company
        fields = (
            'id', 'name', 'legal_name', 'tin_number', 'registration_number',
            'address', 'city', 'country', 'phone', 'email', 'website',
            'fiscal_year_start', 'fiscal_year_end', 'base_currency', 'is_active',
            'created_at', 'updated_at', 'created_by__username'
        )
        export_order = fields


class BranchResource(resources.ModelResource):
    class Meta:
        model = Branch
        fields = (
            'id', 'company__name', 'name', 'code', 'address', 'city', 'country',
            'phone', 'email', 'is_main', 'is_active', 'created_at', 'updated_at'
        )
        export_order = fields


class DepartmentResource(resources.ModelResource):
    class Meta:
        model = Department
        fields = (
            'id', 'company__name', 'branch__name', 'name', 'code', 'description',
            'manager__user__username', 'is_active', 'created_at', 'updated_at'
        )
        export_order = fields


class CustomerResource(resources.ModelResource):
    class Meta:
        model = Customer
        fields = (
            'id', 'company__name', 'name', 'customer_type', 'tin_number',
            'address', 'city', 'country', 'phone', 'email', 'credit_limit',
            'payment_terms', 'is_active', 'created_at', 'updated_at'
        )
        export_order = fields


class UserProfileResource(resources.ModelResource):
    class Meta:
        model = UserProfile
        fields = (
            'id', 'company__name', 'user__username', 'employee_id',
            'department__name', 'branch__name', 'position', 'hire_date',
            'salary', 'phone', 'address', 'is_active', 'created_at', 'updated_at'
        )
        export_order = fields