from decimal import Decimal
from .models import Account, AccountType, AccountCategory, AccountGroup


def get_or_create_account_type(name, code_prefix=None):
    """Helper to get or create an account type"""
    if not code_prefix:
        prefix_map = {
            'Asset': '1',
            'Liability': '2',
            'Equity': '3',
            'Revenue': '4',
            'Expense': '5',
        }
        code_prefix = prefix_map.get(name, '1')
    
    account_type, created = AccountType.objects.get_or_create(
        name=name,
        defaults={
            'code_prefix': code_prefix,
            'description': f'{name} accounts',
            'is_active': True,
        }
    )
    return account_type


def get_or_create_account_category(name, normal_balance='debit'):
    """Helper to get or create an account category"""
    account_group, _ = AccountGroup.objects.get_or_create(
        name='Default Group',
        defaults={
            'account_type': get_or_create_account_type('Asset'),
            'code_range_start': '1000',
            'code_range_end': '9999',
            'display_order': 10,
            'is_active': True,
        }
    )
    
    category, created = AccountCategory.objects.get_or_create(
        name=name,
        defaults={
            'account_group': account_group,
            'report_category': 'balance_sheet',
            'display_order': 10,
            'is_active': True,
        }
    )
    return category


def get_or_create_account_group(name, account_type_name=None):
    """Helper to get or create an account group"""
    if not account_type_name:
        if 'asset' in name.lower():
            account_type_name = 'Asset'
        elif 'liability' in name.lower():
            account_type_name = 'Liability'
        elif 'equity' in name.lower() or 'capital' in name.lower():
            account_type_name = 'Equity'
        elif 'revenue' in name.lower() or 'sales' in name.lower() or 'income' in name.lower():
            account_type_name = 'Revenue'
        elif 'expense' in name.lower() or 'cost' in name.lower():
            account_type_name = 'Expense'
        else:
            account_type_name = 'Asset'
    
    account_type = get_or_create_account_type(account_type_name)
    
    group, created = AccountGroup.objects.get_or_create(
        name=name,
        defaults={
            'account_type': account_type,
            'display_order': 10,
            'is_active': True,
            'code_range_start': '1000',
            'code_range_end': '9999',
        }
    )
    return group


def get_account(code, name=None, account_type_name=None):
    """Get or create an account by code with all required fields."""
    if account_type_name:
        type_name = account_type_name.capitalize()
        category_map = {'Asset': 'Assets', 'Liability': 'Liabilities', 'Equity': 'Equity', 'Revenue': 'Revenue', 'Income': 'Revenue', 'Expense': 'Expenses'}
        category_name = category_map.get(type_name, 'Assets')
        group_map = {'Asset': 'Current Assets', 'Liability': 'Current Liabilities', 'Equity': 'Share Capital', 'Revenue': 'Sales Revenue', 'Income': 'Sales Revenue', 'Expense': 'Operating Expenses'}
        group_name = group_map.get(type_name, 'Other Accounts')
    else:
        if code.startswith('1'):
            category_name, type_name, group_name = 'Assets', 'Asset', 'Current Assets'
        elif code.startswith('2'):
            category_name, type_name, group_name = 'Liabilities', 'Liability', 'Current Liabilities'
        elif code.startswith('3'):
            category_name, type_name, group_name = 'Equity', 'Equity', 'Share Capital'
        elif code.startswith('4'):
            category_name, type_name, group_name = 'Revenue', 'Revenue', 'Sales Revenue'
        elif code.startswith('5'):
            category_name, type_name, group_name = 'Expenses', 'Expense', 'Operating Expenses'
        else:
            category_name, type_name, group_name = 'Assets', 'Asset', 'Other Assets'
    
    account_group = get_or_create_account_group(group_name, type_name)
    account_category = get_or_create_account_category(category_name)
    account_type = get_or_create_account_type(type_name)
    
    account, created = Account.objects.get_or_create(
        code=code,
        defaults={
            'name': name or code,
            'account_type': account_type,
            'account_category': account_category,
            'account_group': account_group,
            'is_active': True,
            'allow_manual_entries': True,
            'opening_balance': Decimal('0.00'),
            'current_balance': Decimal('0.00'),
        }
    )
    if not created and name and account.name != name:
        account.name = name
        account.save(update_fields=['name'])
    return account