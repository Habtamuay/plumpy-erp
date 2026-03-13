from decimal import Decimal
from django.db.models import Q, Sum
from apps.accounting.models import Account, AccountType, AccountGroup, AccountCategory, JournalLine

def _get_scoped_structure(model_class, company):
    """
    Fetch structure models (Type, Group, Category) that are either global or belong to company.
    """
    return model_class.objects.filter(
        Q(company=company) | Q(company__isnull=True),
        is_active=True
    )

def get_trial_balance(company):
    """
    Returns Trial Balance report data: list of all accounts with Debit/Credit columns.
    Ensures accounts with zero balance are included.
    """
    accounts = Account.objects.filter(company=company, is_active=True).select_related('account_type').order_by('code')
    
    lines = []
    total_debit = Decimal('0.00')
    total_credit = Decimal('0.00')
    
    for acc in accounts:
        balance = acc.current_balance
        debit = Decimal('0.00')
        credit = Decimal('0.00')
        
        # Determine placement based on Account Type
        # Assets (1) and Expenses (5): Normal Debit
        # Liabilities (2), Equity (3), Revenue (4): Normal Credit
        
        prefix = ''
        if acc.account_type:
            prefix = acc.account_type.code_prefix
            
        if prefix in ['1', '5']:
            # Normal Debit
            if balance >= 0:
                debit = balance
            else:
                credit = abs(balance)
        else:
            # Normal Credit
            if balance <= 0:
                credit = abs(balance)
            else:
                debit = balance
                
        lines.append({
            'code': acc.code,
            'name': acc.name,
            'debit': debit,
            'credit': credit,
            'account_type': acc.account_type.name if acc.account_type else ''
        })
        
        total_debit += debit
        total_credit += credit
        
    return {
        'lines': lines,
        'total_debit': total_debit,
        'total_credit': total_credit,
        'is_balanced': round(total_debit, 2) == round(total_credit, 2)
    }

def get_profit_and_loss(company, start_date=None, end_date=None, compare_start_date=None, compare_end_date=None):
    """
    Returns Income Statement (P&L) data.
    If start_date and/or end_date are provided, it calculates activity for that range.
    (e.g., start_date=None, end_date=X implies lifetime up to X).
    If compare_start_date and compare_end_date are provided, it calculates previous period activity.
    Otherwise, it uses the lifetime current_balance of accounts.
    """
    # Revenue (4) and Expenses (5)
    
    def get_section_data(code_prefix, multiplier):
        # Fetch types matching prefix (Global or Company)
        types = _get_scoped_structure(AccountType, company).filter(code_prefix__startswith=code_prefix)
        
        groups_data = []
        section_total = Decimal('0.00')
        section_prev_total = Decimal('0.00')
        section_budget_total = Decimal('0.00')
        
        # Fetch all relevant groups
        groups = _get_scoped_structure(AccountGroup, company).filter(
            account_type__in=types
        ).order_by('display_order', 'name')
        
        for group in groups:
            # Get accounts for this group and company
            accounts = Account.objects.filter(
                company=company, 
                account_group=group, 
                is_active=True
            ).order_by('code')
            
            acc_list = []
            group_total = Decimal('0.00')
            group_prev_total = Decimal('0.00')
            group_budget_total = Decimal('0.00')
            
            for acc in accounts:
                balance = Decimal('0.00')
                prev_balance = Decimal('0.00')
                if start_date or end_date:
                    filters = {'journal__is_posted': True}
                    if start_date:
                        filters['journal__entry_date__gte'] = start_date
                    if end_date:
                        filters['journal__entry_date__lte'] = end_date

                    period_activity = JournalLine.objects.filter(account=acc, **filters).aggregate(
                        debits=Sum('debit', default=Decimal('0.00')),
                        credits=Sum('credit', default=Decimal('0.00'))
                    )
                    balance = period_activity['debits'] - period_activity['credits']
                else:
                    balance = acc.current_balance

                if compare_start_date and compare_end_date:
                    prev_filters = {
                        'journal__is_posted': True,
                        'journal__entry_date__gte': compare_start_date,
                        'journal__entry_date__lte': compare_end_date
                    }
                    prev_activity = JournalLine.objects.filter(account=acc, **prev_filters).aggregate(
                        debits=Sum('debit', default=Decimal('0.00')),
                        credits=Sum('credit', default=Decimal('0.00'))
                    )
                    prev_balance = prev_activity['debits'] - prev_activity['credits']

                val = balance * multiplier
                prev_val = prev_balance * multiplier
                budget_val = acc.budget
                variance_val = val - budget_val
                
                acc_list.append({
                    'code': acc.code,
                    'name': acc.name,
                    'balance': val,
                    'previous_balance': prev_val,
                    'budget': budget_val,
                    'variance': variance_val,
                })
                group_total += val
                group_prev_total += prev_val
                group_budget_total += budget_val
            
            # Add group if it has accounts or just to show structure
            if acc_list:
                groups_data.append({
                    'name': group.name,
                    'accounts': acc_list,
                    'total': group_total,
                    'previous_total': group_prev_total,
                    'budget_total': group_budget_total,
                    'variance_total': group_total - group_budget_total
                })
                section_total += group_total
                section_prev_total += group_prev_total
                section_budget_total += group_budget_total
            
        return groups_data, section_total, section_prev_total, section_budget_total

    # Revenue: Credit normal (negative balance). Multiplier -1.
    revenues, total_revenue, total_prev_revenue, total_budget_revenue = get_section_data('4', -1)
    
    # Expenses: Debit normal (positive balance). Multiplier 1.
    expenses, total_expenses, total_prev_expenses, total_budget_expenses = get_section_data('5', 1)
    
    return {
        'revenues': revenues,
        'total_revenue': total_revenue,
        'total_prev_revenue': total_prev_revenue,
        'total_budget_revenue': total_budget_revenue,
        'total_revenue_variance': total_revenue - total_budget_revenue,
        'expenses': expenses,
        'total_expenses': total_expenses,
        'total_prev_expenses': total_prev_expenses,
        'total_budget_expenses': total_budget_expenses,
        'total_expenses_variance': total_expenses - total_budget_expenses,
        'net_income': total_revenue - total_expenses,
        'prev_net_income': total_prev_revenue - total_prev_expenses,
        'budget_net_income': total_budget_revenue - total_budget_expenses,
        'net_income_variance': (total_revenue - total_expenses) - (total_budget_revenue - total_budget_expenses)
    }

def get_balance_sheet(company, end_date=None):
    """
    Returns Balance Sheet data.
    If end_date is provided, calculates balances as of that date.
    """
    # Assets (1), Liabilities (2), Equity (3)
    
    def get_section_data(code_prefix, multiplier):
        types = _get_scoped_structure(AccountType, company).filter(code_prefix__startswith=code_prefix).order_by('code_prefix')
        
        data = []
        total = Decimal('0.00')
        
        for at in types:
            groups = _get_scoped_structure(AccountGroup, company).filter(account_type=at).order_by('display_order', 'name')
            
            type_data = {
                'name': at.name,
                'groups': [],
                'total': Decimal('0.00')
            }
            
            for group in groups:
                accounts = Account.objects.filter(
                    company=company,
                    account_group=group,
                    is_active=True
                ).order_by('code')
                
                acc_list = []
                group_total = Decimal('0.00')
                
                for acc in accounts:
                    balance = Decimal('0.00')
                    if end_date:
                        activity = JournalLine.objects.filter(
                            account=acc,
                            journal__entry_date__lte=end_date,
                            journal__is_posted=True
                        ).aggregate(
                            debits=Sum('debit', default=Decimal('0.00')),
                            credits=Sum('credit', default=Decimal('0.00'))
                        )
                        balance = activity['debits'] - activity['credits']
                    else:
                        balance = acc.current_balance

                    val = balance * multiplier
                    acc_list.append({
                        'code': acc.code,
                        'name': acc.name,
                        'balance': val
                    })
                    group_total += val
                
                if acc_list:
                    type_data['groups'].append({
                        'name': group.name,
                        'accounts': acc_list,
                        'total': group_total
                    })
                    type_data['total'] += group_total
            
            if type_data['groups']:
                data.append(type_data)
                total += type_data['total']
                
        return data, total

    # Assets (1): Debit normal.
    assets, total_assets = get_section_data('1', 1)
    
    # Liabilities (2): Credit normal (neg).
    liabilities, total_liabilities = get_section_data('2', -1)
    
    # Equity (3): Credit normal (neg).
    equity, total_equity = get_section_data('3', -1)
    
    # Net Income
    pl = get_profit_and_loss(company, start_date=None, end_date=end_date)
    net_income = pl['net_income']
    
    return {
        'assets': assets,
        'total_assets': total_assets,
        'liabilities': liabilities,
        'total_liabilities': total_liabilities,
        'equity': equity,
        'total_equity': total_equity,
        'net_income': net_income,
        'total_liabilities_and_equity': total_liabilities + total_equity + net_income
    }

def get_cash_flow(company):
    """
    Returns Cash Flow data (Simplified).
    """
    # 1. Operating: Net Income
    pl = get_profit_and_loss(company)
    net_income = pl['net_income']
    
    # Find cash accounts
    cash_accounts = Account.objects.filter(
        company=company,
        is_active=True,
        name__icontains='Cash'
    )
    cash_balance = sum(acc.current_balance for acc in cash_accounts)
    
    return {
        'operating_activities': [
            {'name': 'Net Income', 'amount': net_income}
        ],
        'total_operating': net_income,
        'investing_activities': [],
        'total_investing': Decimal('0.00'),
        'financing_activities': [],
        'total_financing': Decimal('0.00'),
        'net_change': net_income, 
        'cash_beginning': Decimal('0.00'),
        'cash_ending': cash_balance
    }