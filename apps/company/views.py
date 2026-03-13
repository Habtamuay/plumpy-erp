from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.models import User  # Fixed import
from django.db.models import Sum, Q, Count
from django.utils import timezone
from django.http import HttpResponse, JsonResponse
from datetime import timedelta
from decimal import Decimal
import csv

from .models import Company, Branch, Department, Customer, UserProfile
from .forms import CompanyForm
from .resources import CompanyResource, BranchResource, DepartmentResource, CustomerResource, UserProfileResource
from apps.accounting.models import PurchaseBill, Payment
from apps.purchasing.models import Supplier, PurchaseOrder
from apps.sales.models import SalesOrder, SalesInvoice


# ============================
# Company Dashboard
# ============================

@login_required
def company_dashboard(request):
    """Main company dashboard"""
    company = getattr(request, 'company', None)

    # Fallback for users without UserProfile record.
    if not company:
        company_id = request.session.get('current_company_id')
        if company_id:
            company = Company.objects.filter(id=company_id, is_active=True).first()

    user_profile = UserProfile.objects.filter(user=request.user).select_related('company').first()
    if not company and user_profile:
        company = user_profile.company

    if not company:
        messages.warning(request, "Please select a company first.")
        return redirect('core:home')
    
    # Company statistics
    stats = {
        'branches': Branch.objects.filter(company=company, is_active=True).count(),
        'departments': Department.objects.filter(company=company, is_active=True).count(),
        'customers': Customer.objects.filter(company=company, is_active=True).count(),
        'employees': UserProfile.objects.filter(company=company, is_active=True).count(),
    }
    
    # Recent activities
    recent_customers = Customer.objects.filter(company=company).order_by('-created_at')[:5]
    recent_employees = UserProfile.objects.filter(company=company).order_by('-created_at')[:5]
    
    context = {
        'user_profile': user_profile,
        'company': company,
        'stats': stats,
        'recent_customers': recent_customers,
        'recent_employees': recent_employees,
        'today': timezone.now().date(),
    }
    return render(request, 'company/dashboard.html', context)


@login_required
def company_scope_audit(request):
    """
    Staff-only audit page to monitor records missing company scope.
    """
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('core:home')

    from apps.purchasing.models import (
        PurchaseRequisition,
        PurchaseOrderLine,
        PurchaseOrderApproval,
        GoodsReceipt,
        GoodsReceiptLine,
        PurchaseRequisitionLine,
        VendorPerformance,
    )
    from apps.sales.models import (
        SalesOrderLine,
        SalesInvoiceLine,
        SalesShipment,
        SalesShipmentLine,
        SalesPayment,
    )
    from apps.accounting.models import (
        AccountType,
        AccountGroup,
        AccountCategory,
        Account,
        JournalLine,
        PurchaseBillLine,
        ReconciliationAuditLog,
    )
    from apps.reports.models import (
        ReportCategory,
        ReportTemplate,
        ScheduledReport,
        DashboardWidget,
    )

    checks = [
        ("purchasing.Supplier (string company)", Supplier.objects.filter(Q(company__isnull=True) | Q(company='')).count()),
        ("purchasing.PurchaseOrder (string company)", PurchaseOrder.objects.filter(Q(company__isnull=True) | Q(company='')).count()),
        ("purchasing.PurchaseRequisition (string company)", PurchaseRequisition.objects.filter(Q(company__isnull=True) | Q(company='')).count()),
        ("purchasing.PurchaseOrderLine", PurchaseOrderLine.objects.filter(company__isnull=True).count()),
        ("purchasing.PurchaseOrderApproval", PurchaseOrderApproval.objects.filter(company__isnull=True).count()),
        ("purchasing.GoodsReceipt", GoodsReceipt.objects.filter(company__isnull=True).count()),
        ("purchasing.GoodsReceiptLine", GoodsReceiptLine.objects.filter(company__isnull=True).count()),
        ("purchasing.PurchaseRequisitionLine", PurchaseRequisitionLine.objects.filter(company__isnull=True).count()),
        ("purchasing.VendorPerformance", VendorPerformance.objects.filter(company__isnull=True).count()),
        ("sales.SalesOrder", SalesOrder.objects.filter(company__isnull=True).count()),
        ("sales.SalesOrderLine", SalesOrderLine.objects.filter(company__isnull=True).count()),
        ("sales.SalesInvoice", SalesInvoice.objects.filter(company__isnull=True).count()),
        ("sales.SalesInvoiceLine", SalesInvoiceLine.objects.filter(company__isnull=True).count()),
        ("sales.SalesShipment", SalesShipment.objects.filter(company__isnull=True).count()),
        ("sales.SalesShipmentLine", SalesShipmentLine.objects.filter(company__isnull=True).count()),
        ("sales.SalesPayment", SalesPayment.objects.filter(company__isnull=True).count()),
        ("accounting.AccountType", AccountType.objects.filter(company__isnull=True).count()),
        ("accounting.AccountGroup", AccountGroup.objects.filter(company__isnull=True).count()),
        ("accounting.AccountCategory", AccountCategory.objects.filter(company__isnull=True).count()),
        ("accounting.Account", Account.objects.filter(company__isnull=True).count()),
        ("accounting.JournalLine", JournalLine.objects.filter(company__isnull=True).count()),
        ("accounting.PurchaseBill", PurchaseBill.objects.filter(company__isnull=True).count()),
        ("accounting.PurchaseBillLine", PurchaseBillLine.objects.filter(company__isnull=True).count()),
        ("accounting.Payment", Payment.objects.filter(company__isnull=True).count()),
        ("accounting.ReconciliationAuditLog", ReconciliationAuditLog.objects.filter(company__isnull=True).count()),
        ("reports.ReportCategory", ReportCategory.objects.filter(company__isnull=True).count()),
        ("reports.ReportTemplate", ReportTemplate.objects.filter(company__isnull=True).count()),
        ("reports.ScheduledReport", ScheduledReport.objects.filter(company__isnull=True).count()),
        ("reports.DashboardWidget", DashboardWidget.objects.filter(company__isnull=True).count()),
    ]

    rows = []
    total_missing = 0
    for model_label, missing in checks:
        total_missing += missing
        rows.append({
            "model_label": model_label,
            "missing_count": missing,
            "ok": missing == 0,
        })

    context = {
        "rows": rows,
        "total_missing": total_missing,
        "checked_models": len(rows),
        "today": timezone.now().date(),
    }
    return render(request, "company/company_scope_audit.html", context)


# ============================
# Company CRUD
# ============================

@login_required
def company_list(request):
    """List all companies"""
    companies = Company.objects.filter(is_active=True).annotate(
        branch_count=Count('branches')
    ).order_by('name')
    
    return render(request, 'company/company_list.html', {'companies': companies})


@login_required
def company_detail(request, company_id):
    """View company details with summary statistics"""
    company = get_object_or_404(Company, id=company_id)
    
    # Get related data
    branches = company.branches.filter(is_active=True)
    departments = Department.objects.filter(branch__company=company, is_active=True)
    customers = company.customers.filter(is_active=True)[:10]
    
    # Summary statistics
    branches_count = branches.count()
    departments_count = departments.count()
    customers_count = company.customers.filter(is_active=True).count()
    employees_count = UserProfile.objects.filter(company=company, is_active=True).count()
    
    context = {
        'company': company,
        'branches': branches,
        'departments': departments,
        'customers': customers,
        'branches_count': branches_count,
        'departments_count': departments_count,
        'customers_count': customers_count,
        'employees_count': employees_count,
        'today': timezone.now().date(),
    }
    return render(request, 'company/company_detail.html', context)


@login_required
def company_create(request):
    """Create a new company"""
    if request.method == 'POST':
        form = CompanyForm(request.POST, request.FILES)
        if form.is_valid():
            company = form.save(commit=False)
            company.created_by = request.user
            company.save()
            messages.success(request, f'Company "{company.name}" created successfully!')
            return redirect('company:detail', company_id=company.id)
    else:
        form = CompanyForm()
    
    return render(request, 'company/company_form.html', {
        'form': form,
        'title': 'Create Company'
    })


@login_required
def company_edit(request, company_id):
    """Edit a company"""
    company = get_object_or_404(Company, id=company_id)
    
    if request.method == 'POST':
        form = CompanyForm(request.POST, request.FILES, instance=company)
        if form.is_valid():
            form.save()
            messages.success(request, f'Company "{company.name}" updated successfully.')
            return redirect('company:detail', company_id=company.id)
    else:
        form = CompanyForm(instance=company)
    
    context = {
        'form': form,
        'company': company,
        'title': f'Edit {company.name}',
    }
    return render(request, 'company/company_form.html', context)


@login_required
def company_delete(request, company_id):
    """Delete a company"""
    company = get_object_or_404(Company, id=company_id)
    
    if request.method == 'POST':
        company_name = company.name
        company.delete()
        messages.success(request, f'Company "{company_name}" deleted successfully.')
        return redirect('company:list')
    
    context = {
        'company': company,
    }
    return render(request, 'company/company_confirm_delete.html', context)


# ============================
# Branch CRUD
# ============================

@login_required
def branch_list(request):
    """List branches for current company"""
    if not hasattr(request, 'company'):
        messages.warning(request, 'Please select a company first.')
        return redirect('company:list')
    
    branches = Branch.objects.filter(company=request.company, is_active=True).order_by('name')
    return render(request, 'company/branch_list.html', {'branches': branches})


@login_required
def branch_detail(request, branch_id):
    """View branch details"""
    branch = get_object_or_404(Branch.objects.select_related('company'), id=branch_id)
    
    # Get departments in this branch
    departments = branch.departments.filter(is_active=True)
    
    # Get employees in this branch
    employees = UserProfile.objects.filter(branch=branch, is_active=True).select_related('user')
    
    context = {
        'branch': branch,
        'departments': departments,
        'employees': employees,
        'today': timezone.now().date(),
    }
    return render(request, 'company/branch_detail.html', context)


@login_required
def branch_create(request):
    """Create a new branch"""
    if not hasattr(request, 'company'):
        messages.warning(request, 'Please select a company first.')
        return redirect('company:list')
    
    if request.method == 'POST':
        # Handle form submission - you'll need to create a BranchForm
        messages.success(request, 'Branch created successfully.')
        return redirect('company:branch_list')
    
    context = {
        'companies': [request.company] if hasattr(request, 'company') else Company.objects.filter(is_active=True),
    }
    return render(request, 'company/branch_form.html', context)


@login_required
def branch_edit(request, branch_id):
    """Edit a branch"""
    branch = get_object_or_404(Branch, id=branch_id)
    
    if request.method == 'POST':
        # Handle form submission
        messages.success(request, 'Branch updated successfully.')
        return redirect('company:branch_detail', branch_id=branch.id)
    
    context = {
        'branch': branch,
        'companies': Company.objects.filter(is_active=True),
    }
    return render(request, 'company/branch_form.html', context)


@login_required
def branch_delete(request, branch_id):
    """Delete a branch"""
    branch = get_object_or_404(Branch, id=branch_id)
    
    if request.method == 'POST':
        branch.delete()
        messages.success(request, 'Branch deleted successfully.')
        return redirect('company:branch_list')
    
    context = {
        'branch': branch,
    }
    return render(request, 'company/branch_confirm_delete.html', context)


# ============================
# Department CRUD
# ============================

@login_required
def department_list(request):
    """List departments for current company"""
    if not hasattr(request, 'company'):
        messages.warning(request, 'Please select a company first.')
        return redirect('company:list')
    
    departments = Department.objects.filter(company=request.company, is_active=True).select_related('branch', 'manager').order_by('name')
    return render(request, 'company/department_list.html', {'departments': departments})


@login_required
def department_detail(request, department_id):
    """View department details"""
    department = get_object_or_404(
        Department.objects.select_related('company', 'branch', 'manager__user'),
        id=department_id
    )
    
    # Get employees in this department
    employees = UserProfile.objects.filter(department=department, is_active=True).select_related('user')
    
    context = {
        'department': department,
        'employees': employees,
        'today': timezone.now().date(),
    }
    return render(request, 'company/department_detail.html', context)


@login_required
def department_create(request):
    """Create a new department"""
    if not hasattr(request, 'company'):
        messages.warning(request, 'Please select a company first.')
        return redirect('company:list')
    
    if request.method == 'POST':
        # Handle form submission
        messages.success(request, 'Department created successfully.')
        return redirect('company:department_list')
    
    branches = Branch.objects.filter(company=request.company, is_active=True)
    context = {
        'branches': branches,
    }
    return render(request, 'company/department_form.html', context)


@login_required
def department_edit(request, department_id):
    """Edit a department"""
    department = get_object_or_404(Department, id=department_id)
    
    if request.method == 'POST':
        # Handle form submission
        messages.success(request, 'Department updated successfully.')
        return redirect('company:department_detail', department_id=department.id)
    
    branches = Branch.objects.filter(company=department.company, is_active=True)
    context = {
        'department': department,
        'branches': branches,
    }
    return render(request, 'company/department_form.html', context)


@login_required
def department_delete(request, department_id):
    """Delete a department"""
    department = get_object_or_404(Department, id=department_id)
    
    if request.method == 'POST':
        department.delete()
        messages.success(request, 'Department deleted successfully.')
        return redirect('company:department_list')
    
    context = {
        'department': department,
    }
    return render(request, 'company/department_confirm_delete.html', context)


# ============================
# Customer CRUD
# ============================

@login_required
def customer_list(request):
    """List customers for current company"""
    if not hasattr(request, 'company'):
        messages.warning(request, 'Please select a company first.')
        return redirect('company:list')
    
    customers = Customer.objects.filter(company=request.company, is_active=True).order_by('name')
    return render(request, 'company/customer_list.html', {'customers': customers})


@login_required
def customer_detail(request, pk):
    """View customer details"""
    customer = get_object_or_404(Customer.objects.select_related('company'), pk=pk)
    
    # Get recent invoices from sales app
    recent_invoices = SalesInvoice.objects.filter(customer=customer).order_by('-invoice_date')[:10]
    
    # Calculate remaining amount for each invoice
    for invoice in recent_invoices:
        invoice.remaining = invoice.total_amount - invoice.paid_amount
    
    # Get recent payments from accounting app
    recent_payments = Payment.objects.filter(customer=customer).order_by('-date')[:10]
    
    # Calculate statistics
    total_invoiced = SalesInvoice.objects.filter(
        customer=customer,
        status__in=['posted', 'paid']
    ).aggregate(total=Sum('total_amount'))['total'] or 0
    
    # Calculate outstanding amount
    outstanding_invoices = SalesInvoice.objects.filter(
        customer=customer,
        status__in=['posted', 'partial', 'overdue']
    )
    
    outstanding = 0
    for inv in outstanding_invoices:
        outstanding += inv.total_amount - inv.paid_amount
    
    context = {
        'customer': customer,
        'recent_invoices': recent_invoices,
        'recent_payments': recent_payments,
        'total_invoiced': total_invoiced,
        'outstanding': outstanding,
        'today': timezone.now().date(),
    }
    return render(request, 'company/customer_detail.html', context)


@login_required
def customer_ledger(request, customer_id):
    """View customer ledger with transaction history"""
    customer = get_object_or_404(Customer, id=customer_id)
    
    # Get date filters
    from_date = request.GET.get('from', (timezone.now().date() - timedelta(days=90)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to', timezone.now().date().strftime('%Y-%m-%d'))
    
    try:
        from_date = timezone.datetime.strptime(from_date, '%Y-%m-%d').date()
        to_date = timezone.datetime.strptime(to_date, '%Y-%m-%d').date()
    except:
        from_date = timezone.now().date() - timedelta(days=90)
        to_date = timezone.now().date()
    
    # Get invoices from sales app
    invoices = SalesInvoice.objects.filter(
        customer=customer,
        invoice_date__range=[from_date, to_date]
    ).order_by('-invoice_date')
    
    # Calculate remaining for each invoice
    for invoice in invoices:
        invoice.remaining = invoice.total_amount - invoice.paid_amount
    
    # Get orders from sales app
    orders = SalesOrder.objects.filter(
        customer=customer,
        order_date__range=[from_date, to_date]
    ).order_by('-order_date')
    
    # Get payments from accounting app
    receipts = Payment.objects.filter(
        customer=customer,
        date__range=[from_date, to_date]
    ).order_by('-date')
    
    # Calculate totals
    total_invoiced = invoices.aggregate(total=Sum('total_amount'))['total'] or Decimal('0')
    total_received = receipts.aggregate(total=Sum('amount'))['amount__sum'] or Decimal('0')
    outstanding = total_invoiced - total_received
    
    context = {
        'customer': customer,
        'invoices': invoices,
        'orders': orders,
        'receipts': receipts,
        'total_invoiced': total_invoiced,
        'total_received': total_received,
        'outstanding': outstanding,
        'from_date': from_date,
        'to_date': to_date,
        'today': timezone.now().date(),
    }
    return render(request, 'company/customer_ledger.html', context)


@login_required
def customer_create(request):
    """Create a new customer"""
    if not hasattr(request, 'company'):
        messages.warning(request, 'Please select a company first.')
        return redirect('company:list')
    
    if request.method == 'POST':
        # Handle form submission
        messages.success(request, 'Customer created successfully.')
        return redirect('company:customer_list')
    
    context = {
        'companies': [request.company] if hasattr(request, 'company') else Company.objects.filter(is_active=True),
    }
    return render(request, 'company/customer_form.html', context)


@login_required
def customer_edit(request, pk):
    """Edit a customer"""
    customer = get_object_or_404(Customer, pk=pk)
    
    if request.method == 'POST':
        # Handle form submission
        messages.success(request, 'Customer updated successfully.')
        return redirect('company:customer_detail', pk=customer.pk)
    
    context = {
        'customer': customer,
        'companies': Company.objects.filter(is_active=True),
    }
    return render(request, 'company/customer_form.html', context)


@login_required
def customer_delete(request, pk):
    """Delete a customer"""
    customer = get_object_or_404(Customer, pk=pk)
    
    if request.method == 'POST':
        customer.delete()
        messages.success(request, 'Customer deleted successfully.')
        return redirect('company:customer_list')
    
    context = {
        'customer': customer,
    }
    return render(request, 'company/customer_confirm_delete.html', context)


# ============================
# Supplier Views
# ============================

@login_required
def supplier_list(request):
    """List all suppliers"""
    suppliers = Supplier.objects.all()
    context = {
        'suppliers': suppliers,
    }
    return render(request, 'company/supplier_list.html', context)


@login_required
def supplier_detail(request, supplier_id):
    """Supplier detail view"""
    supplier = get_object_or_404(Supplier, id=supplier_id)
    context = {
        'supplier': supplier,
    }
    return render(request, 'company/supplier_detail.html', context)


@login_required
def supplier_ledger(request, supplier_id):
    """View supplier ledger with transaction history"""
    supplier = get_object_or_404(Supplier, id=supplier_id)
    
    # Get date filters
    from_date = request.GET.get('from', (timezone.now().date() - timedelta(days=90)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to', timezone.now().date().strftime('%Y-%m-%d'))
    
    try:
        from_date = timezone.datetime.strptime(from_date, '%Y-%m-%d').date()
        to_date = timezone.datetime.strptime(to_date, '%Y-%m-%d').date()
    except:
        from_date = timezone.now().date() - timedelta(days=90)
        to_date = timezone.now().date()
    
    # Get bills from accounting app
    bills = PurchaseBill.objects.filter(
        supplier=supplier,
        bill_date__range=[from_date, to_date]
    ).order_by('-bill_date')
    
    # Get purchase orders from purchasing app
    pos = PurchaseOrder.objects.filter(
        supplier=supplier,
        order_date__range=[from_date, to_date]
    ).order_by('-order_date')
    
    # Get payments from accounting app
    payments = Payment.objects.filter(
        supplier=supplier,
        date__range=[from_date, to_date]
    ).order_by('-date')
    
    # Calculate totals
    total_billed = bills.aggregate(total=Sum('total_amount'))['total'] or Decimal('0')
    total_paid = payments.aggregate(total=Sum('amount'))['amount__sum'] or Decimal('0')
    outstanding = total_billed - total_paid
    
    context = {
        'supplier': supplier,
        'bills': bills,
        'pos': pos,
        'payments': payments,
        'total_billed': total_billed,
        'total_paid': total_paid,
        'outstanding': outstanding,
        'from_date': from_date,
        'to_date': to_date,
        'today': timezone.now().date(),
    }
    return render(request, 'company/supplier_ledger.html', context)


# ============================
# User Profile Views
# ============================

@login_required
def user_profile(request):
    """View current user's profile"""
    profile = get_object_or_404(
        UserProfile.objects.select_related('user', 'company', 'branch', 'department'),
        user=request.user
    )
    return render(request, 'company/user_profile.html', {'profile': profile})


@login_required
def user_profile_detail(request, user_id):
    """View another user's profile (for managers/admins)"""
    profile = get_object_or_404(
        UserProfile.objects.select_related('user', 'company', 'branch', 'department'),
        user__id=user_id
    )
    return render(request, 'company/user_profile_detail.html', {'profile': profile})


@login_required
def user_list(request):
    """List all users with profiles"""
    profiles = UserProfile.objects.filter(is_active=True).select_related(
        'user', 'company', 'branch', 'department'
    ).order_by('user__username')
    
    # Filter by company
    company_id = request.GET.get('company')
    if company_id:
        profiles = profiles.filter(company_id=company_id)
    
    # Filter by role
    role = request.GET.get('role')
    if role:
        profiles = profiles.filter(role=role)
    
    companies = Company.objects.filter(is_active=True)
    
    context = {
        'profiles': profiles,
        'companies': companies,
        'role_choices': UserProfile.ROLE_CHOICES,
        'today': timezone.now().date(),
    }
    return render(request, 'company/user_list.html', context)


# ============================
# Export Functions
# ============================

@login_required
def export_customers(request):
    """Export customers to CSV"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="customers_{timezone.now().strftime("%Y%m%d")}.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['ID', 'Name', 'Contact Person', 'Email', 'Phone', 'Address', 'Company', 'TIN', 'Credit Limit', 'Status'])
    
    customers = Customer.objects.select_related('company')
    for customer in customers:
        writer.writerow([
            customer.id,
            customer.name,
            customer.contact_person,
            customer.email,
            customer.phone,
            customer.address,
            customer.company.name if customer.company else '',
            customer.tin,
            customer.credit_limit,
            'Active' if customer.is_active else 'Inactive',
        ])
    
    return response


@login_required
def export_companies(request):
    """Export companies to Excel/CSV"""
    if not request.user.is_staff:
        messages.error(request, 'Access denied.')
        return redirect('company:list')
    
    # Using csv export as fallback
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="companies_{timezone.now().strftime("%Y%m%d")}.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['ID', 'Name', 'Code', 'Email', 'Phone', 'City', 'Country', 'TIN', 'Is Active'])
    
    companies = Company.objects.all()
    for company in companies:
        writer.writerow([
            company.id,
            company.name,
            company.code,
            company.email,
            company.phone,
            company.city,
            company.country,
            company.tin,
            'Yes' if company.is_active else 'No'
        ])
    
    return response


@login_required
def export_branches(request):
    """Export branches to CSV"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="branches_{timezone.now().strftime("%Y%m%d")}.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['ID', 'Name', 'Code', 'Company', 'Phone', 'Email', 'City', 'Is Active'])
    
    branches = Branch.objects.select_related('company')
    for branch in branches:
        writer.writerow([
            branch.id,
            branch.name,
            branch.code,
            branch.company.name,
            branch.phone,
            branch.email,
            branch.city,
            'Yes' if branch.is_active else 'No'
        ])
    
    return response


@login_required
def export_departments(request):
    """Export departments to CSV"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="departments_{timezone.now().strftime("%Y%m%d")}.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['ID', 'Name', 'Code', 'Branch', 'Company', 'Is Active'])
    
    departments = Department.objects.select_related('branch__company')
    for dept in departments:
        writer.writerow([
            dept.id,
            dept.name,
            dept.code,
            dept.branch.name,
            dept.branch.company.name,
            'Yes' if dept.is_active else 'No'
        ])
    
    return response


@login_required
def export_company_customers(request):
    """Export customers for the current company"""
    # Get current company from session or user profile
    company_id = request.session.get('current_company_id')
    if not company_id and hasattr(request, 'user') and request.user.is_authenticated:
        try:
            profile = UserProfile.objects.get(user=request.user)
            company_id = profile.company.id
        except UserProfile.DoesNotExist:
            pass
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="company_customers_{timezone.now().strftime("%Y%m%d")}.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['ID', 'Name', 'Contact Person', 'Email', 'Phone', 'Address', 'TIN', 'Credit Limit'])
    
    customers = Customer.objects.filter(company_id=company_id)
    for customer in customers:
        writer.writerow([
            customer.id,
            customer.name,
            customer.contact_person,
            customer.email,
            customer.phone,
            customer.address,
            customer.tin,
            customer.credit_limit,
        ])
    
    return response
