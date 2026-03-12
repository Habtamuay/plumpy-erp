from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from decimal import Decimal

from .models import (
    JournalEntry, JournalLine, Account, AccountType, AccountGroup, AccountCategory,
    PurchaseBill, Payment
)
from apps.production.models import ProductionRun
from apps.purchasing.models import GoodsReceipt
from apps.inventory.models import StockTransaction
from apps.company.models import Company


# Helper to get or create common accounts
def get_account(code, name=None, account_type_name=None):
    """Get or create an account by code with proper AccountType, AccountGroup, and AccountCategory instances"""
    
    # First, get or create the account type
    if account_type_name:
        # Capitalize the account type name properly
        type_name = account_type_name.capitalize()
        
        # Map common account types to code prefixes
        prefix_map = {
            'Asset': '1',
            'Liability': '2',
            'Equity': '3',
            'Revenue': '4',
            'Income': '4',
            'Expense': '5',
        }
        
        code_prefix = prefix_map.get(type_name, code[0])
        
        account_type, _ = AccountType.objects.get_or_create(
            name=type_name,
            defaults={
                'code_prefix': code_prefix,
                'description': f'{type_name} accounts'
            }
        )
    else:
        # Default to Asset if no type specified
        account_type, _ = AccountType.objects.get_or_create(
            name='Asset',
            defaults={
                'code_prefix': '1',
                'description': 'Asset accounts'
            }
        )
    
    # Get or create a default account group for this account type
    account_group, _ = AccountGroup.objects.get_or_create(
        account_type=account_type,
        name=f"{account_type.name} Group",
        defaults={
            'code_range_start': f"{code_prefix}000",
            'code_range_end': f"{code_prefix}999",
            'description': f'Default group for {account_type.name} accounts',
            'is_active': True,
            'display_order': 0,
        }
    )
    
    # Get or create a default account category for this account group
    account_category, _ = AccountCategory.objects.get_or_create(
        account_group=account_group,
        name=f"{account_type.name} Category",
        defaults={
            'report_category': 'balance_sheet' if account_type.name in ['Asset', 'Liability', 'Equity'] else 'income_statement',
            'description': f'Default category for {account_type.name} accounts',
            'is_active': True,
            'display_order': 0,
        }
    )
    
    # Now create or get the account with all required fields
    account, created = Account.objects.get_or_create(
        code=code,
        defaults={
            'name': name or code,
            'account_type': account_type,
            'account_group': account_group,
            'account_category': account_category,
            'is_active': True,
            'opening_balance': Decimal('0.00'),
            'current_balance': Decimal('0.00'),
        }
    )
    
    # If account exists but we want to update the name
    if not created and name and account.name != name:
        account.name = name
        account.save(update_fields=['name'])
    
    return account


@receiver(post_save, sender=JournalEntry)
def post_journal_update_balances(sender, instance, created, **kwargs):
    """Update account balances when a journal entry is posted"""
    if instance.is_posted and not created:
        for line in instance.lines.all():
            line.account.update_balance()


# ─────────────────────────────────────────────────────
# Purchase Bill Signals
# ─────────────────────────────────────────────────────

@receiver(pre_save, sender=PurchaseBill)
def set_purchase_bill_overdue(sender, instance, **kwargs):
    """Auto-set overdue status if due date passed"""
    if instance.due_date and instance.due_date < timezone.now().date():
        if instance.status not in ['paid', 'cancelled']:
            instance.status = 'overdue'


@receiver(post_save, sender=PurchaseBill)
def auto_post_purchase_bill(sender, instance, created, **kwargs):
    """
    Automatically create journal entry when purchase bill is posted
    Dr Inventory/Expense
    Cr Accounts Payable
    """
    if not created and instance.status == 'posted' and not instance.journal_entry:
        with transaction.atomic():
            # Get or create default accounts
            inventory_account = Account.objects.filter(code='1300').first()
            ap_account = Account.objects.filter(code='2100').first()
            
            if not inventory_account:
                inventory_account = get_account('1300', 'Raw Materials & Packing Inventory', 'asset')
            if not ap_account:
                ap_account = get_account('2100', 'Accounts Payable', 'liability')
            
            je = JournalEntry.objects.create(
                company=instance.supplier.company,
                entry_date=instance.bill_date,
                reference=instance.bill_number,
                narration=f"Purchase Bill {instance.bill_number} - {instance.supplier.name}",
                is_posted=True,
                posted_at=timezone.now()
            )
            
            # Dr Inventory/Expense
            JournalLine.objects.create(
                journal=je, 
                account=inventory_account, 
                debit=instance.total_amount,
                narration=f"Purchase Bill {instance.bill_number}"
            )
            
            # Cr Accounts Payable
            JournalLine.objects.create(
                journal=je, 
                account=ap_account, 
                credit=instance.total_amount,
                narration=f"Purchase Bill {instance.bill_number}"
            )
            
            instance.journal_entry = je
            instance.save(update_fields=['journal_entry'])


# ─────────────────────────────────────────────────────
# Payment Signals
# ─────────────────────────────────────────────────────

@receiver(post_save, sender=Payment)
def auto_post_payment(sender, instance, created, **kwargs):
    """
    Automatically create journal entry for payments
    Customer Receipt: Dr Cash, Cr Accounts Receivable
    Supplier Payment: Dr Accounts Payable, Cr Cash
    """
    if created and not instance.journal_entry:
        with transaction.atomic():
            # Get or create accounts
            cash_account = Account.objects.filter(code='1010').first()
            ar_account = Account.objects.filter(code='1100').first()
            ap_account = Account.objects.filter(code='2100').first()
            
            if not cash_account:
                cash_account = get_account('1010', 'Cash/Bank', 'asset')
            if not ar_account:
                ar_account = get_account('1100', 'Accounts Receivable', 'asset')
            if not ap_account:
                ap_account = get_account('2100', 'Accounts Payable', 'liability')
            
            # Determine company
            company = None
            party_name = ""
            if instance.payment_type == 'customer' and instance.customer:
                company = instance.customer.company
                party_name = instance.customer.name
            elif instance.payment_type == 'supplier' and instance.supplier:
                company = instance.supplier.company
                party_name = instance.supplier.name
            
            je = JournalEntry.objects.create(
                company=company,
                entry_date=instance.date,
                reference=instance.reference or f"PMT-{instance.id}",
                narration=f"Payment {'from' if instance.payment_type == 'customer' else 'to'} {party_name}",
                is_posted=True,
                posted_at=timezone.now()
            )
            
            if instance.payment_type == 'customer' and cash_account and ar_account:
                # Customer receipt: Dr Cash, Cr AR
                JournalLine.objects.create(
                    journal=je, 
                    account=cash_account, 
                    debit=instance.amount,
                    narration=f"Payment from {party_name}"
                )
                JournalLine.objects.create(
                    journal=je, 
                    account=ar_account, 
                    credit=instance.amount,
                    narration=f"Payment from {party_name}"
                )
                
            elif instance.payment_type == 'supplier' and cash_account and ap_account:
                # Supplier payment: Dr AP, Cr Cash
                JournalLine.objects.create(
                    journal=je, 
                    account=ap_account, 
                    debit=instance.amount,
                    narration=f"Payment to {party_name}"
                )
                JournalLine.objects.create(
                    journal=je, 
                    account=cash_account, 
                    credit=instance.amount,
                    narration=f"Payment to {party_name}"
                )
            
            instance.journal_entry = je
            instance.save(update_fields=['journal_entry'])


# ─────────────────────────────────────────────────────
# Goods Receipt Signals
# ─────────────────────────────────────────────────────

@receiver(post_save, sender=GoodsReceipt)
def auto_post_goods_receipt(sender, instance, created, **kwargs):
    """
    Automatically create journal entry for goods receipt
    Dr Inventory
    Cr Goods Received Not Invoiced (Accrual)
    """
    if created:
        with transaction.atomic():
            inventory_account = Account.objects.filter(code='1300').first()
            accrual_account = Account.objects.filter(code='2110').first()
            
            if not inventory_account:
                inventory_account = get_account('1300', 'Raw Materials & Packing Inventory', 'asset')
            if not accrual_account:
                accrual_account = get_account('2110', 'Goods Received Not Invoiced', 'liability')
            
            # Calculate total received value
            total_received_value = 0
            for line in instance.lines.all():
                if line.po_line and line.po_line.unit_price:
                    value = line.quantity_received * line.po_line.unit_price
                    total_received_value += value
            
            if total_received_value > 0:
                je = JournalEntry.objects.create(
                    company=instance.po.company if instance.po else None,
                    entry_date=instance.receipt_date,
                    reference=instance.receipt_number,
                    narration=f"Goods Receipt {instance.receipt_number} against PO {instance.po.po_number if instance.po else ''}",
                    is_posted=True,
                    posted_at=timezone.now()
                )

                JournalLine.objects.create(
                    journal=je, 
                    account=inventory_account, 
                    debit=total_received_value,
                    narration=f"Goods receipt {instance.receipt_number}"
                )
                JournalLine.objects.create(
                    journal=je, 
                    account=accrual_account, 
                    credit=total_received_value,
                    narration=f"Goods receipt {instance.receipt_number}"
                )


# ─────────────────────────────────────────────────────
# Stock Transaction Signals
# ─────────────────────────────────────────────────────

@receiver(post_save, sender=StockTransaction)
def auto_post_stock_adjustment(sender, instance, created, **kwargs):
    """
    Automatically create journal entry for stock adjustments/scrap
    Positive adjustment: Dr Inventory, Cr Variance
    Negative adjustment/scrap: Cr Inventory, Dr Variance
    """
    if created and instance.transaction_type in ['adjustment', 'scrap']:
        with transaction.atomic():
            inventory_account = Account.objects.filter(code='1300').first()
            variance_account = Account.objects.filter(code='5900').first()
            
            if not inventory_account:
                inventory_account = get_account('1300', 'Inventory', 'asset')
            if not variance_account:
                variance_account = get_account('5900', 'Inventory Variance / Scrap', 'expense')
            
            # Determine company
            company = None
            if hasattr(instance, 'warehouse_to') and instance.warehouse_to:
                company = instance.warehouse_to.company
            elif hasattr(instance, 'warehouse_from') and instance.warehouse_from:
                company = instance.warehouse_from.company
            
            # Calculate value
            unit_cost = instance.item.unit_cost or Decimal('0.00')
            value = abs(instance.quantity) * unit_cost
            
            if value > 0:
                je = JournalEntry.objects.create(
                    company=company,
                    entry_date=instance.transaction_date.date() if hasattr(instance.transaction_date, 'date') else instance.transaction_date,
                    reference=f"ST-{instance.id}",
                    narration=f"Stock {instance.get_transaction_type_display()} for {instance.item.code}",
                    is_posted=True,
                    posted_at=timezone.now()
                )

                if instance.quantity > 0:
                    # Positive adjustment → Inventory Dr, Variance Cr (gain)
                    JournalLine.objects.create(
                        journal=je, 
                        account=inventory_account, 
                        debit=value,
                        narration=f"Stock adjustment +{instance.quantity}"
                    )
                    JournalLine.objects.create(
                        journal=je, 
                        account=variance_account, 
                        credit=value,
                        narration=f"Stock adjustment +{instance.quantity}"
                    )
                else:
                    # Negative adjustment / scrap → Inventory Cr, Variance Dr (loss)
                    JournalLine.objects.create(
                        journal=je, 
                        account=inventory_account, 
                        credit=value,
                        narration=f"Stock adjustment {instance.quantity}"
                    )
                    JournalLine.objects.create(
                        journal=je, 
                        account=variance_account, 
                        debit=value,
                        narration=f"Stock adjustment {instance.quantity}"
                    )


# ─────────────────────────────────────────────────────
# Production Run Signals
# ─────────────────────────────────────────────────────

@receiver(post_save, sender=ProductionRun)
def auto_post_production_completion(sender, instance, created, **kwargs):
    """
    Automatically create journal entry when production run is completed
    Dr Finished Goods Inventory
    Cr Work In Process / Raw Materials
    """
    if not created and instance.status == 'completed':
        with transaction.atomic():
            # This is a placeholder - implement based on your costing method
            # You would need to calculate the cost of finished goods
            pass