from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from apps.company.models import Company

from .services.report_service import (
    get_balance_sheet,
    get_cash_flow,
    get_profit_and_loss,
    get_trial_balance,
)


def _current_company(request):
    company = getattr(request, 'company', None)
    if company:
        return company

    company_id = request.session.get('current_company_id')
    if not company_id:
        return None
    return Company.objects.filter(id=company_id, is_active=True).first()


@login_required
def financial_trial_balance(request):
    company = _current_company(request)
    if not company:
        return redirect('core:home')

    report = get_trial_balance(company)
    return render(
        request,
        'accounting/financial_trial_balance.html',
        {'report': report, 'company': company},
    )


@login_required
def financial_profit_and_loss(request):
    company = _current_company(request)
    if not company:
        return redirect('core:home')

    report = get_profit_and_loss(company)
    return render(
        request,
        'accounting/financial_profit_and_loss.html',
        {'report': report, 'company': company},
    )


@login_required
def financial_balance_sheet(request):
    company = _current_company(request)
    if not company:
        return redirect('core:home')

    report = get_balance_sheet(company)
    return render(
        request,
        'accounting/financial_balance_sheet.html',
        {'report': report, 'company': company},
    )


@login_required
def financial_cash_flow(request):
    company = _current_company(request)
    if not company:
        return redirect('core:home')

    report = get_cash_flow(company)
    return render(
        request,
        'accounting/financial_cash_flow.html',
        {'report': report, 'company': company},
    )

