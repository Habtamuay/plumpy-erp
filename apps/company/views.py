from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Q, Count
from django.utils import timezone
from django.http import HttpResponse
from datetime import timedelta
from decimal import Decimal
import csv

from .models import Company, Branch, Department, Customer, UserProfile
from apps.accounting.models import PurchaseBill, Payment
from apps.purchasing.models import Supplier, PurchaseOrder
from apps.sales.models import SalesOrder, SalesInvoice  # Change this import


# ============================
# Company Views
# ============================

@login_required
def company_detail(request, company_id):
    """View company details with summary statistics"""
    company = get_object_or_404(Company, id=company_id)
    
    # Summary statistics
    branches_count = company.branches.filter(is_active=True).count()
    departments_count = company.departments.filter(is_active=True).count()
    customers_count = company.customers.filter(is_active=True).count()
    employees_count = UserProfile.objects.filter(company=company, is_active=True).count()
    
    context = {
        'company': company,
        'branches_count': branches_count,
        'departments_count': departments_count,
        'customers_count': customers_count,
        'employees_count': employees_count,
        'today': timezone.now().date(),
    }
    return render(request, 'company/company_detail.html', context)


@login_required
def company_list(request):
    """List all companies"""
    companies = Company.objects.filter(is_active=True).order_by('name')
    return render(request, 'company/company_list.html', {'companies': companies})


# ============================
# Branch Views
# ============================

@login_required
def branch_list(request):
    """List all branches"""
    branches = Branch.objects.filter(is_active=True).select_related('company').order_by('company__name', 'name')
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


# ============================
# Department Views
# ============================

@login_required
def department_list(request):
    """List all departments"""
    departments = Department.objects.filter(is_active=True).select_related('company', 'branch', 'manager').order_by('company__name', 'name')
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


# ============================
# Customer Views
# ============================

@login_required
def customer_list(request):
    """List all customers"""
    customers = Customer.objects.filter(is_active=True).select_related('company').order_by('company__name', 'name')
    return render(request, 'company/customer_list.html', {'customers': customers})


@login_required
def customer_detail(request, pk):
    """View customer details"""
    customer = get_object_or_404(Customer.objects.select_related('company'), pk=pk)
    
    # Get recent invoices from sales app
    recent_invoices = SalesInvoice.objects.filter(customer=customer).order_by('-invoice_date')[:10]
    
    # Get recent payments from accounting app
    recent_payments = Payment.objects.filter(customer=customer).order_by('-date')[:10]
    
    # Calculate statistics
    total_invoiced = SalesInvoice.objects.filter(
        customer=customer,
        status__in=['posted', 'paid']
    ).aggregate(total=Sum('total_amount'))['total'] or 0
    
    outstanding = SalesInvoice.objects.filter(
        customer=customer,
        status__in=['posted', 'partial', 'overdue']
    ).aggregate(total=Sum('remaining_amount'))['total'] or 0
    
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


# ============================
# Supplier Views
# ============================

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
# Dashboard Views
# ============================

@login_required
def company_dashboard(request):
    """Main company dashboard"""
    user_profile = get_object_or_404(UserProfile, user=request.user)
    company = user_profile.company
    
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
        'company': company,
        'stats': stats,
        'recent_customers': recent_customers,
        'recent_employees': recent_employees,
        'today': timezone.now().date(),
    }
    return render(request, 'company/dashboard.html', context)


# ============================
# Export Views
# ============================

@login_required
def export_customers(request):
    """Export customers to CSV"""
    import csv
    from django.http import HttpResponse
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="customers_{timezone.now().strftime("%Y%m%d")}.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Company', 'Name', 'TIN', 'Phone', 'Email', 'City', 'Credit Limit', 'Status'])
    
    customers = Customer.objects.filter(is_active=True).select_related('company')
    for customer in customers:
        writer.writerow([
            customer.company.name,
            customer.name,
            customer.tin,
            customer.phone,
            customer.email,
            customer.city,
            customer.credit_limit,
            'Active' if customer.is_active else 'Inactive',
        ])
    
    return response