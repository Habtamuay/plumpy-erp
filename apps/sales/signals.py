import logging
from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from decimal import Decimal

logger = logging.getLogger(__name__)

# Import helper for getting models dynamically to avoid circular imports
from django.apps import apps

# ============================
# Helper Functions
# ============================

def get_or_create_account_type(name, code_prefix=None):
    AccountType = apps.get_model('account', 'AccountType')
    if not code_prefix:
        prefix_map = {'Asset': '1', 'Liability': '2', 'Equity': '3', 'Revenue': '4', 'Expense': '5'}
        code_prefix = prefix_map.get(name, '1')
    
    account_type, _ = AccountType.objects.get_or_create(
        name=name,
        defaults={'code_prefix': code_prefix, 'description': f'{name} accounts', 'is_active': True}
    )
    return account_type

def get_account(code, name=None, account_type_name=None):
    Account = apps.get_model('account', 'Account')
    AccountGroup = apps.get_model('account', 'AccountGroup')
    AccountCategory = apps.get_model('account', 'AccountCategory')

    try:
        return Account.objects.get(code=code)
    except Account.DoesNotExist:
        # Determine types/groups for automatic creation
        type_name = account_type_name or 'Asset'
        
        # This is a simplified version of your logic to ensure the account exists
        acc_type = get_or_create_account_type(type_name)
        
        # Ensure Group and Category exist (Simplified)
        group, _ = AccountGroup.objects.get_or_create(
            name=f"Default {type_name} Group", 
            defaults={'account_type': acc_type, 'code_range_start': '1000', 'code_range_end': '9999'}
        )
        category, _ = AccountCategory.objects.get_or_create(
            name=f"Default {type_name} Category",
            defaults={'account_group': group}
        )

        return Account.objects.create(
            code=code,
            name=name or code,
            account_type=acc_type,
            account_category=category,
            account_group=group,
            is_active=True,
            opening_balance=Decimal('0.00'),
            current_balance=Decimal('0.00')
        )

# ============================
# Journal Entry Signals
# ============================

@receiver(post_save, sender='account.JournalEntry')
def post_journal_update_balances(sender, instance, created, **kwargs):
    """Update account balances when a journal entry is posted"""
    if instance.is_posted:
        for line in instance.lines.all():
            if line.account:
                line.account.update_balance()

# ============================
# Sales Invoice Signals (Replaces PurchaseBill logic if in Sales)
# ============================

@receiver(post_save, sender='sales.SalesInvoice')
def auto_post_sales_invoice(sender, instance, created, **kwargs):
    """
    Automatically create journal entry when sales invoice is posted
    Dr Accounts Receivable
    Cr Sales Revenue
    """
    JournalEntry = apps.get_model('account', 'JournalEntry')
    JournalLine = apps.get_model('account', 'JournalLine')

    try:
        if not created and instance.status == 'posted':
            with transaction.atomic():
                ar_account = get_account('1100', 'Accounts Receivable - Trade', 'Asset')
                sales_account = get_account('4100', 'Sales Revenue', 'Revenue')
                
                je = JournalEntry.objects.create(
                    company=instance.company,
                    entry_date=instance.invoice_date,
                    reference=instance.invoice_number,
                    narration=f"Sales Invoice {instance.invoice_number} - {instance.customer.name}",
                    is_posted=True,
                    posted_at=timezone.now()
                )
                
                # Dr AR
                JournalLine.objects.create(journal=je, account=ar_account, debit=instance.total_amount)
                # Cr Revenue
                JournalLine.objects.create(journal=je, account=sales_account, credit=instance.total_amount)
    except Exception as e:
        logger.exception(f"Failed to auto-post journal entry for Sales Invoice {instance.invoice_number}")

# ============================
# Sales Payment Signals
# ============================

@receiver(post_save, sender='sales.SalesPayment')
def auto_post_payment(sender, instance, created, **kwargs):
    """
    Automatically create journal entry for payments
    Dr Cash/Bank
    Cr Accounts Receivable
    """
    JournalEntry = apps.get_model('account', 'JournalEntry')
    JournalLine = apps.get_model('account', 'JournalLine')

    try:
        if created and instance.amount > 0:
            with transaction.atomic():
                cash_account = get_account('1010', 'Cash/Bank', 'Asset')
                ar_account = get_account('1100', 'Accounts Receivable - Trade', 'Asset')
                
                je = JournalEntry.objects.create(
                    company=instance.company,
                    entry_date=instance.payment_date,
                    reference=instance.reference or f"PAY-{instance.id}",
                    narration=f"Payment from {instance.invoice.customer.name}",
                    is_posted=True,
                    posted_at=timezone.now()
                )
                
                # Dr Cash
                JournalLine.objects.create(journal=je, account=cash_account, debit=instance.amount)
                # Cr AR
                JournalLine.objects.create(journal=je, account=ar_account, credit=instance.amount)
    except Exception as e:
        logger.exception(f"Error in auto-posting sales payment {instance.id}: {e}")

# ============================
# Stock / Production Signals
# ============================

@receiver(post_save, sender='inventory.StockTransaction')
def auto_post_stock_adjustment(sender, instance, created, **kwargs):
    JournalEntry = apps.get_model('account', 'JournalEntry')
    JournalLine = apps.get_model('account', 'JournalLine')

    try:
        if created and instance.transaction_type in ['adjustment', 'scrap']:
            with transaction.atomic():
                inventory_account = get_account('1300', 'Inventory', 'Asset')
                variance_account = get_account('5900', 'Inventory Variance', 'Expense')
                
                unit_cost = getattr(instance.item, 'unit_cost', Decimal('0.00')) or Decimal('0.00')
                value = abs(instance.quantity) * unit_cost
                
                if value > 0:
                    je = JournalEntry.objects.create(
                        company=instance.company if hasattr(instance, 'company') else None,
                        entry_date=timezone.now().date(),
                        reference=f"ST-{instance.id}",
                        narration=f"Stock adjustment for {instance.item.code}",
                        is_posted=True
                    )
                    if instance.quantity > 0:
                        JournalLine.objects.create(journal=je, account=inventory_account, debit=value)
                        JournalLine.objects.create(journal=je, account=variance_account, credit=value)
                    else:
                        JournalLine.objects.create(journal=je, account=inventory_account, credit=value)
                        JournalLine.objects.create(journal=je, account=variance_account, debit=value)
    except Exception as e:
        logger.exception(f"Failed to auto-post stock adjustment for Transaction {instance.id}")