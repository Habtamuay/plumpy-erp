from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q, F
from django.utils import timezone
from django.http import HttpResponse
from datetime import timedelta
from decimal import Decimal
import json

from .models import (
    Account, JournalEntry, PurchaseBill, Payment,  # Removed SalesInvoice from here
    AccountType, AccountGroup, AccountCategory, ReconciliationAuditLog
)
from .resources import ARAgingResource, APAgingResource
from apps.company.models import Customer
from apps.purchasing.models import Supplier
from apps.sales.models import SalesInvoice  # Import SalesInvoice from sales app


@login_required
def dashboard(request):
    """Enhanced Accounting Dashboard with key metrics and charts"""
    today = timezone.now().date()
    
    # AR Summary - using SalesInvoice from sales app
    ar_invoices = SalesInvoice.objects.filter(status__in=['posted', 'partial', 'overdue'])
    total_ar_outstanding = ar_invoices.aggregate(total=Sum('total_amount'))['total'] or 0
    
    # AP Summary
    ap_bills = PurchaseBill.objects.filter(status__in=['posted', 'partial', 'overdue'])
    total_ap_outstanding = ap_bills.aggregate(total=Sum('total_amount'))['total'] or 0
    
    # Overdue amounts
    overdue_ar_amount = ar_invoices.filter(due_date__lt=today).aggregate(total=Sum('total_amount'))['total'] or 0
    overdue_ap_amount = ap_bills.filter(due_date__lt=today).aggregate(total=Sum('total_amount'))['total'] or 0
    
    # Cash balance (assuming account code 1010 for cash)
    cash_account = Account.objects.filter(code='1010').first()
    cash_balance = cash_account.current_balance if cash_account else 0
    
    # Monthly revenue (current month)
    month_start = today.replace(day=1)
    monthly_revenue = SalesInvoice.objects.filter(
        status__in=['posted', 'paid'],
        invoice_date__gte=month_start
    ).aggregate(total=Sum('total_amount'))['total'] or 0
    
    # AR Aging buckets
    ar_current = ar_invoices.filter(due_date__gte=today).aggregate(total=Sum('total_amount'))['total'] or 0
    ar_1_30 = ar_invoices.filter(
        due_date__lt=today, 
        due_date__gte=today - timedelta(days=30)
    ).aggregate(total=Sum('total_amount'))['total'] or 0
    ar_31_60 = ar_invoices.filter(
        due_date__lt=today - timedelta(days=30), 
        due_date__gte=today - timedelta(days=60)
    ).aggregate(total=Sum('total_amount'))['total'] or 0
    ar_61_90 = ar_invoices.filter(
        due_date__lt=today - timedelta(days=60), 
        due_date__gte=today - timedelta(days=90)
    ).aggregate(total=Sum('total_amount'))['total'] or 0
    ar_90_plus = ar_invoices.filter(
        due_date__lt=today - timedelta(days=90)
    ).aggregate(total=Sum('total_amount'))['total'] or 0
    
    # AP Aging buckets
    ap_current = ap_bills.filter(due_date__gte=today).aggregate(total=Sum('total_amount'))['total'] or 0
    ap_1_30 = ap_bills.filter(
        due_date__lt=today, 
        due_date__gte=today - timedelta(days=30)
    ).aggregate(total=Sum('total_amount'))['total'] or 0
    ap_31_60 = ap_bills.filter(
        due_date__lt=today - timedelta(days=30), 
        due_date__gte=today - timedelta(days=60)
    ).aggregate(total=Sum('total_amount'))['total'] or 0
    ap_61_90 = ap_bills.filter(
        due_date__lt=today - timedelta(days=60), 
        due_date__gte=today - timedelta(days=90)
    ).aggregate(total=Sum('total_amount'))['total'] or 0
    ap_90_plus = ap_bills.filter(
        due_date__lt=today - timedelta(days=90)
    ).aggregate(total=Sum('total_amount'))['total'] or 0
    
    # Recent journal entries
    recent_journal_entries = JournalEntry.objects.filter(
        is_posted=True
    ).select_related('created_by').order_by('-entry_date')[:10]
    
    # Top customers
    top_customers = SalesInvoice.objects.values(
        'customer__name'
    ).annotate(
        total_invoiced=Sum('total_amount')
    ).order_by('-total_invoiced')[:5]
    
    context = {
        'total_ar_outstanding': total_ar_outstanding,
        'total_ap_outstanding': total_ap_outstanding,
        'overdue_ar_amount': overdue_ar_amount,
        'overdue_ap_amount': overdue_ap_amount,
        'cash_balance': cash_balance,
        'monthly_revenue': monthly_revenue,
        'ar_current': ar_current,
        'ar_1_30': ar_1_30,
        'ar_31_60': ar_31_60,
        'ar_61_90': ar_61_90,
        'ar_90_plus': ar_90_plus,
        'ap_current': ap_current,
        'ap_1_30': ap_1_30,
        'ap_31_60': ap_31_60,
        'ap_61_90': ap_61_90,
        'ap_90_plus': ap_90_plus,
        'recent_journal_entries': recent_journal_entries,
        'top_customers': top_customers,
        'today': today,
    }
    
    return render(request, 'accounting/dashboard.html', context)


@login_required
def ar_dashboard(request):
    """Accounts Receivable Dashboard with aging analysis"""
    today = timezone.now().date()
    
    # Outstanding invoices from sales app
    outstanding_invoices = SalesInvoice.objects.filter(
        status__in=['posted', 'partial']
    ).select_related('customer')
    
    # Summary stats
    total_outstanding = outstanding_invoices.aggregate(
        total=Sum('total_amount')
    )['total'] or 0
    
    overdue_count = SalesInvoice.objects.filter(
        status__in=['posted', 'partial', 'overdue'],
        due_date__lt=today
    ).count()
    
    overdue_amount = SalesInvoice.objects.filter(
        status__in=['posted', 'partial', 'overdue'],
        due_date__lt=today
    ).aggregate(total=Sum('total_amount'))['total'] or 0
    
    # Aging buckets
    aging_buckets = {
        'current': SalesInvoice.objects.filter(
            status__in=['posted', 'partial'],
            due_date__gte=today
        ).aggregate(total=Sum('total_amount'))['total'] or 0,
        
        '1_30': SalesInvoice.objects.filter(
            status__in=['posted', 'partial', 'overdue'],
            due_date__lt=today,
            due_date__gte=today - timedelta(days=30)
        ).aggregate(total=Sum('total_amount'))['total'] or 0,
        
        '31_60': SalesInvoice.objects.filter(
            status__in=['posted', 'partial', 'overdue'],
            due_date__lt=today - timedelta(days=30),
            due_date__gte=today - timedelta(days=60)
        ).aggregate(total=Sum('total_amount'))['total'] or 0,
        
        '61_90': SalesInvoice.objects.filter(
            status__in=['posted', 'partial', 'overdue'],
            due_date__lt=today - timedelta(days=60),
            due_date__gte=today - timedelta(days=90)
        ).aggregate(total=Sum('total_amount'))['total'] or 0,
        
        '90_plus': SalesInvoice.objects.filter(
            status__in=['posted', 'partial', 'overdue'],
            due_date__lt=today - timedelta(days=90)
        ).aggregate(total=Sum('total_amount'))['total'] or 0,
    }
    
    # Recent payments
    recent_payments = Payment.objects.filter(
        payment_type='customer'
    ).select_related('customer').order_by('-date')[:10]
    
    context = {
        'total_outstanding': total_outstanding,
        'overdue_count': overdue_count,
        'overdue_amount': overdue_amount,
        'aging_buckets': aging_buckets,
        'recent_payments': recent_payments,
        'outstanding_invoices': outstanding_invoices[:20],
        'today': today,
    }
    
    return render(request, 'accounting/ar_dashboard.html', context)


@login_required
def ap_dashboard(request):
    """Accounts Payable Dashboard with aging analysis"""
    today = timezone.now().date()
    
    # Outstanding bills
    outstanding_bills = PurchaseBill.objects.filter(
        status__in=['posted', 'partial']
    ).select_related('supplier')
    
    # Summary stats
    total_outstanding = outstanding_bills.aggregate(
        total=Sum('total_amount')
    )['total'] or 0
    
    overdue_count = PurchaseBill.objects.filter(
        status__in=['posted', 'partial', 'overdue'],
        due_date__lt=today
    ).count()
    
    overdue_amount = PurchaseBill.objects.filter(
        status__in=['posted', 'partial', 'overdue'],
        due_date__lt=today
    ).aggregate(total=Sum('total_amount'))['total'] or 0
    
    # Aging buckets
    aging_buckets = {
        'current': PurchaseBill.objects.filter(
            status__in=['posted', 'partial'],
            due_date__gte=today
        ).aggregate(total=Sum('total_amount'))['total'] or 0,
        
        '1_30': PurchaseBill.objects.filter(
            status__in=['posted', 'partial', 'overdue'],
            due_date__lt=today,
            due_date__gte=today - timedelta(days=30)
        ).aggregate(total=Sum('total_amount'))['total'] or 0,
        
        '31_60': PurchaseBill.objects.filter(
            status__in=['posted', 'partial', 'overdue'],
            due_date__lt=today - timedelta(days=30),
            due_date__gte=today - timedelta(days=60)
        ).aggregate(total=Sum('total_amount'))['total'] or 0,
        
        '61_90': PurchaseBill.objects.filter(
            status__in=['posted', 'partial', 'overdue'],
            due_date__lt=today - timedelta(days=60),
            due_date__gte=today - timedelta(days=90)
        ).aggregate(total=Sum('total_amount'))['total'] or 0,
        
        '90_plus': PurchaseBill.objects.filter(
            status__in=['posted', 'partial', 'overdue'],
            due_date__lt=today - timedelta(days=90)
        ).aggregate(total=Sum('total_amount'))['total'] or 0,
    }
    
    # Recent payments
    recent_payments = Payment.objects.filter(
        payment_type='supplier'
    ).select_related('supplier').order_by('-date')[:10]
    
    context = {
        'total_outstanding': total_outstanding,
        'overdue_count': overdue_count,
        'overdue_amount': overdue_amount,
        'aging_buckets': aging_buckets,
        'recent_payments': recent_payments,
        'outstanding_bills': outstanding_bills[:20],
        'today': today,
    }
    
    return render(request, 'accounting/ap_dashboard.html', context)


@login_required
def ar_aging_report(request):
    """Detailed AR Aging Report with export functionality"""
    today = timezone.now().date()
    
    # Get all AR invoices from sales app
    invoices = SalesInvoice.objects.filter(
        status__in=['posted', 'partial', 'overdue']
    ).select_related('customer').order_by('due_date')
    
    # Calculate aging buckets
    aging_buckets = {
        'current': invoices.filter(due_date__gte=today),
        '1_30': invoices.filter(due_date__lt=today, due_date__gte=today - timedelta(days=30)),
        '31_60': invoices.filter(due_date__lt=today - timedelta(days=30), due_date__gte=today - timedelta(days=60)),
        '61_90': invoices.filter(due_date__lt=today - timedelta(days=60), due_date__gte=today - timedelta(days=90)),
        '90_plus': invoices.filter(due_date__lt=today - timedelta(days=90)),
    }
    
    # Calculate totals for each bucket
    bucket_totals = {}
    for bucket_name, qs in aging_buckets.items():
        bucket_totals[bucket_name] = {
            'count': qs.count(),
            'amount': qs.aggregate(total=Sum('total_amount'))['total'] or 0,
        }
    
    # Handle Excel export
    if request.GET.get('export') == 'excel':
        resource = ARAgingResource()
        dataset = resource.export(invoices)
        response = HttpResponse(
            dataset.xlsx, 
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        filename = f"AR_Aging_{today.strftime('%Y%m%d')}.xlsx"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    
    context = {
        'invoices': invoices,
        'bucket_totals': bucket_totals,
        'today': today,
    }
    
    return render(request, 'accounting/ar_aging.html', context)


@login_required
def ap_aging_report(request):
    """Detailed AP Aging Report with export functionality"""
    today = timezone.now().date()
    
    # Get all AP bills
    bills = PurchaseBill.objects.filter(
        status__in=['posted', 'partial', 'overdue']
    ).select_related('supplier').order_by('due_date')
    
    # Calculate aging buckets
    aging_buckets = {
        'current': bills.filter(due_date__gte=today),
        '1_30': bills.filter(due_date__lt=today, due_date__gte=today - timedelta(days=30)),
        '31_60': bills.filter(due_date__lt=today - timedelta(days=30), due_date__gte=today - timedelta(days=60)),
        '61_90': bills.filter(due_date__lt=today - timedelta(days=60), due_date__gte=today - timedelta(days=90)),
        '90_plus': bills.filter(due_date__lt=today - timedelta(days=90)),
    }
    
    # Calculate totals for each bucket
    bucket_totals = {}
    for bucket_name, qs in aging_buckets.items():
        bucket_totals[bucket_name] = {
            'count': qs.count(),
            'amount': qs.aggregate(total=Sum('total_amount'))['total'] or 0,
        }
    
    # Handle Excel export
    if request.GET.get('export') == 'excel':
        resource = APAgingResource()
        dataset = resource.export(bills)
        response = HttpResponse(
            dataset.xlsx, 
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        filename = f"AP_Aging_{today.strftime('%Y%m%d')}.xlsx"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    
    context = {
        'bills': bills,
        'bucket_totals': bucket_totals,
        'today': today,
    }
    
    return render(request, 'accounting/ap_aging.html', context)


@login_required
def trial_balance(request):
    """Trial Balance report"""
    accounts = Account.objects.filter(is_active=True).select_related(
        'account_type', 'account_group', 'account_category'
    ).order_by('code')
    
    total_debits = sum(acc.current_balance for acc in accounts if acc.current_balance > 0)
    total_credits = abs(sum(acc.current_balance for acc in accounts if acc.current_balance < 0))
    
    context = {
        'accounts': accounts,
        'total_debits': total_debits,
        'total_credits': total_credits,
        'is_balanced': abs(total_debits - total_credits) < 0.01,
        'today': timezone.now().date(),
    }
    
    return render(request, 'accounting/trial_balance.html', context)


@login_required
def chart_of_accounts(request):
    """Chart of Accounts view with hierarchy"""
    account_types = AccountType.objects.filter(is_active=True).prefetch_related(
        'groups__categories__accounts'
    ).order_by('code_prefix')
    
    context = {
        'account_types': account_types,
        'today': timezone.now().date(),
    }
    
    return render(request, 'accounting/chart_of_accounts.html', context)


@login_required
def general_ledger(request):
    """General Ledger view with filters"""
    account_id = request.GET.get('account')
    from_date = request.GET.get('from', (timezone.now().date() - timedelta(days=30)).strftime('%Y-%m-%d'))
    to_date = request.GET.get('to', timezone.now().date().strftime('%Y-%m-%d'))
    
    try:
        from_date = timezone.datetime.strptime(from_date, '%Y-%m-%d').date()
        to_date = timezone.datetime.strptime(to_date, '%Y-%m-%d').date()
    except:
        from_date = timezone.now().date() - timedelta(days=30)
        to_date = timezone.now().date()
    
    journal_entries = JournalEntry.objects.filter(
        is_posted=True,
        entry_date__range=[from_date, to_date]
    ).select_related('created_by').prefetch_related('lines__account').order_by('entry_date', 'id')
    
    if account_id:
        journal_entries = journal_entries.filter(lines__account_id=account_id).distinct()
    
    accounts = Account.objects.filter(is_active=True).order_by('code')
    
    context = {
        'journal_entries': journal_entries,
        'accounts': accounts,
        'selected_account': int(account_id) if account_id and account_id.isdigit() else None,
        'from_date': from_date,
        'to_date': to_date,
        'today': timezone.now().date(),
    }
    
    return render(request, 'accounting/general_ledger.html', context)


@login_required
def payment_reconciliation(request):
    """Payment reconciliation screen"""
    today = timezone.now().date()
    cutoff = today - timedelta(days=90)

    ar_invoices = SalesInvoice.objects.filter(
        status__in=['posted', 'partial', 'overdue'],
        invoice_date__gte=cutoff
    ).select_related('customer').order_by('due_date')

    ap_bills = PurchaseBill.objects.filter(
        status__in=['posted', 'partial', 'overdue'],
        bill_date__gte=cutoff
    ).select_related('supplier').order_by('due_date')

    recent_payments = Payment.objects.filter(
        date__gte=cutoff
    ).select_related('customer', 'supplier').order_by('-date')[:20]

    tab = request.GET.get('tab', 'ar')

    context = {
        'tab': tab,
        'ar_invoices': ar_invoices if tab == 'ar' else [],
        'ap_bills': ap_bills if tab == 'ap' else [],
        'recent_payments': recent_payments,
        'today': today,
    }

    return render(request, 'accounting/reconciliation.html', context)


@login_required
def reconcile_payment(request, payment_id):
    """Reconcile a payment against invoices or bills"""
    payment = get_object_or_404(Payment, id=payment_id)

    if request.method == 'POST':
        doc_type = request.POST.get('doc_type')  # 'invoice' or 'bill'
        doc_id = request.POST.get('doc_id')
        amount_applied = Decimal(request.POST.get('amount_applied', '0'))
        notes = request.POST.get('notes', '')

        if amount_applied <= 0:
            messages.error(request, "Amount must be positive.")
            return redirect('accounting:reconcile_payment', payment_id=payment.id)

        if doc_type == 'invoice':
            doc = get_object_or_404(SalesInvoice, id=doc_id, customer=payment.customer)
            remaining = doc.total_amount - (doc.paid_amount or 0)
        else:
            doc = get_object_or_404(PurchaseBill, id=doc_id, supplier=payment.supplier)
            remaining = doc.total_amount - (doc.paid_amount or 0)

        if amount_applied > remaining:
            messages.error(request, f"Amount exceeds remaining balance of {remaining} ETB.")
            return redirect('accounting:reconcile_payment', payment_id=payment.id)

        # Apply payment
        doc.paid_amount = (doc.paid_amount or 0) + amount_applied

        # Update status
        if doc.paid_amount >= doc.total_amount:
            doc.status = 'paid'
        elif doc.paid_amount > 0:
            doc.status = 'partial'
        doc.save()

        # Log audit
        ReconciliationAuditLog.objects.create(
            payment=payment,
            reconciled_by=request.user,
            action=f"applied_to_{doc_type}",
            document_number=doc.invoice_number if doc_type == 'invoice' else doc.bill_number,
            amount_applied=amount_applied,
            remaining_after=remaining - amount_applied,
            notes=notes
        )

        # If fully paid
        if doc.paid_amount >= doc.total_amount:
            ReconciliationAuditLog.objects.create(
                payment=payment,
                reconciled_by=request.user,
                action='fully_reconciled',
                document_number=doc.invoice_number if doc_type == 'invoice' else doc.bill_number,
                amount_applied=amount_applied,
                notes="Document fully reconciled"
            )

        messages.success(request, f"Successfully applied {amount_applied} ETB to {doc_type}.")
        return redirect('accounting:payment_reconciliation')

    # GET: show available documents
    if payment.payment_type == 'customer':
        docs = SalesInvoice.objects.filter(
            customer=payment.customer, 
            status__in=['posted', 'partial']
        ).order_by('due_date')
    else:
        docs = PurchaseBill.objects.filter(
            supplier=payment.supplier, 
            status__in=['posted', 'partial']
        ).order_by('due_date')

    context = {
        'payment': payment,
        'documents': docs,
    }
    return render(request, 'accounting/reconcile_form.html', context)


@login_required
def payment_entry(request):
    """Record a new payment/receipt"""
    from apps.company.models import Customer
    from apps.purchasing.models import Supplier
    
    if request.method == 'POST':
        payment_type = request.POST.get('payment_type')
        party_id = request.POST.get('party_id')
        amount = Decimal(request.POST.get('amount', '0'))
        date_str = request.POST.get('date')
        reference = request.POST.get('reference', '')
        notes = request.POST.get('notes', '')

        try:
            date = timezone.datetime.strptime(date_str, '%Y-%m-%d').date()
        except:
            date = timezone.now().date()

        if payment_type == 'customer':
            party = get_object_or_404(Customer, id=party_id)
            payment = Payment.objects.create(
                payment_type='customer',
                customer=party,
                date=date,
                amount=amount,
                reference=reference,
                notes=notes,
                created_by=request.user
            )
            messages.success(request, f"Receipt of {amount} ETB from {party.name} recorded successfully.")
        else:
            party = get_object_or_404(Supplier, id=party_id)
            payment = Payment.objects.create(
                payment_type='supplier',
                supplier=party,
                date=date,
                amount=amount,
                reference=reference,
                notes=notes,
                created_by=request.user
            )
            messages.success(request, f"Payment of {amount} ETB to {party.name} recorded successfully.")

        return redirect('accounting:payment_reconciliation')

    customers = Customer.objects.filter(is_active=True).order_by('name')
    suppliers = Supplier.objects.filter(is_active=True).order_by('name')

    context = {
        'customers': customers,
        'suppliers': suppliers,
        'today': timezone.now().date(),
    }
    return render(request, 'accounting/payment_entry.html', context)