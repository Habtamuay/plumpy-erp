from decimal import Decimal

from django.db.models import Sum

from apps.accounting.models import Account, JournalLine


def _sum_or_zero(value):
    return value if value is not None else Decimal('0.00')


def _account_type_name(account):
    if not account.account_type_id or not account.account_type:
        return ''
    return (account.account_type.name or '').strip().lower()


def get_trial_balance(company):
    accounts = Account.objects.filter(company=company, is_active=True).order_by('code')

    report = []
    total_debit = Decimal('0.00')
    total_credit = Decimal('0.00')

    for account in accounts:
        totals = JournalLine.objects.filter(
            company=company,
            account=account,
            journal__is_posted=True,
        ).aggregate(
            debit_sum=Sum('debit'),
            credit_sum=Sum('credit'),
        )

        debit = _sum_or_zero(totals['debit_sum'])
        credit = _sum_or_zero(totals['credit_sum'])
        total_debit += debit
        total_credit += credit

        report.append({
            'account_code': account.code,
            'account_name': account.name,
            'debit': debit,
            'credit': credit,
        })

    return {
        'accounts': report,
        'total_debit': total_debit,
        'total_credit': total_credit,
        'is_balanced': total_debit == total_credit,
    }


def get_profit_and_loss(company):
    accounts = Account.objects.filter(company=company, is_active=True).select_related('account_type')
    income_accounts = [a for a in accounts if _account_type_name(a) == 'income']
    expense_accounts = [a for a in accounts if _account_type_name(a) == 'expense']

    income_total = Decimal('0.00')
    expense_total = Decimal('0.00')

    for acc in income_accounts:
        totals = JournalLine.objects.filter(
            company=company,
            account=acc,
            journal__is_posted=True,
        ).aggregate(credit_sum=Sum('credit'))
        income_total += _sum_or_zero(totals['credit_sum'])

    for acc in expense_accounts:
        totals = JournalLine.objects.filter(
            company=company,
            account=acc,
            journal__is_posted=True,
        ).aggregate(debit_sum=Sum('debit'))
        expense_total += _sum_or_zero(totals['debit_sum'])

    return {
        'income': income_total,
        'expenses': expense_total,
        'profit': income_total - expense_total,
    }


def get_balance_sheet(company):
    accounts = Account.objects.filter(company=company, is_active=True).select_related('account_type')

    asset_accounts = [a for a in accounts if _account_type_name(a) == 'asset']
    liability_accounts = [a for a in accounts if _account_type_name(a) == 'liability']
    equity_accounts = [a for a in accounts if _account_type_name(a) == 'equity']

    def calculate_total(account_list):
        total = Decimal('0.00')
        for acc in account_list:
            totals = JournalLine.objects.filter(
                company=company,
                account=acc,
                journal__is_posted=True,
            ).aggregate(
                debit_sum=Sum('debit'),
                credit_sum=Sum('credit'),
            )
            debit = _sum_or_zero(totals['debit_sum'])
            credit = _sum_or_zero(totals['credit_sum'])
            total += debit - credit
        return total

    return {
        'assets': calculate_total(asset_accounts),
        'liabilities': calculate_total(liability_accounts),
        'equity': calculate_total(equity_accounts),
    }


def get_cash_flow(company):
    cash_accounts = Account.objects.filter(
        company=company,
        is_active=True,
        name__icontains='cash',
    )

    total_cash = Decimal('0.00')
    for acc in cash_accounts:
        totals = JournalLine.objects.filter(
            company=company,
            account=acc,
            journal__is_posted=True,
        ).aggregate(
            debit_sum=Sum('debit'),
            credit_sum=Sum('credit'),
        )
        debit = _sum_or_zero(totals['debit_sum'])
        credit = _sum_or_zero(totals['credit_sum'])
        total_cash += debit - credit

    return {'cash_balance': total_cash}

