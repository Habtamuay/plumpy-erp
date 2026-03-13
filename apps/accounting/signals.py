from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from decimal import Decimal

from .models import (
<<<<<<< HEAD
    JournalEntry, JournalLine, Account, AccountType, AccountCategory, AccountGroup,
=======
    JournalEntry, JournalLine, Account, AccountType, AccountGroup, AccountCategory,
>>>>>>> 8f6d5a6faa537f99b7aab118429879e683d07a2b
    PurchaseBill, Payment
)
from apps.production.models import ProductionRun
from apps.purchasing.models import GoodsReceipt
from apps.inventory.models import StockTransaction
from apps.company.models import Company


<<<<<<< HEAD
# ============================
# Helper Functions
# ============================

def get_or_create_account_category(name, normal_balance='debit'):
    """Helper to get or create an account category"""
    # First, get or create a default account group
    account_group, _ = AccountGroup.objects.get_or_create(
        name='Default Group',
        defaults={
            'account_type': get_or_create_account_type('Asset'),  # FIXED: Added account_type
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


def get_or_create_account_type(name, code_prefix=None):
    """Helper to get or create an account type"""
    # Map common account types to code prefixes
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
=======
# Helper to get or create common accounts
def get_account(code, name=None, account_type_name=None):
    """Get or create an account by code with proper AccountType, AccountGroup, and AccountCategory instances"""
    
    try:
        # Determine the code prefix and type name
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
            
            code_prefix = prefix_map.get(type_name, code[0] if code else '1')
        else:
            # Default to Asset if no type specified
            type_name = 'Asset'
            code_prefix = '1'
        
        # Get or create the account type
        account_type, _ = AccountType.objects.get_or_create(
            name=type_name,
            defaults={
                'code_prefix': code_prefix,
                'description': f'{type_name} accounts'
            }
        )
        
        # Get or create a default account group for this account type
        # Use a unique name that includes code_prefix to avoid conflicts
        group_name = f"{account_type.name} Group"
        try:
            account_group, _ = AccountGroup.objects.get_or_create(
                account_type=account_type,
                name=group_name,
                defaults={
                    'code_range_start': f"{code_prefix}000",
                    'code_range_end': f"{code_prefix}999",
                    'description': f'Default group for {account_type.name} accounts',
                    'is_active': True,
                    'display_order': 0,
                }
            )
        except Exception as e:
            # If group creation fails due to unique constraint, try to find existing one
            account_group = AccountGroup.objects.filter(
                account_type=account_type,
                name__icontains=account_type.name
            ).first()
            if not account_group:
                # If still not found, get any group for this account type
                account_group = AccountGroup.objects.filter(account_type=account_type).first()
            if not account_group:
                raise ValueError(f"Could not create or find AccountGroup for {account_type.name}: {e}")
        
        # Ensure account_group is set before proceeding
        if not account_group:
            raise ValueError(f"AccountGroup is None for account type {type_name}")
        
        # Get or create a default account category for this account group
        # Use a unique name that includes account_group to avoid conflicts
        category_name = f"{account_type.name} Category"
        try:
            account_category, _ = AccountCategory.objects.get_or_create(
                account_group=account_group,
                name=category_name,
                defaults={
                    'report_category': 'balance_sheet' if account_type.name in ['Asset', 'Liability', 'Equity'] else 'income_statement',
                    'description': f'Default category for {account_type.name} accounts',
                    'is_active': True,
                    'display_order': 0,
                }
            )
        except Exception as e:
            # If category creation fails due to unique constraint, try to find existing one
            account_category = AccountCategory.objects.filter(
                account_group=account_group,
                name__icontains=account_type.name
            ).first()
            if not account_category:
                # If still not found, get any category for this account group
                account_category = AccountCategory.objects.filter(account_group=account_group).first()
            if not account_category:
                raise ValueError(f"Could not create or find AccountCategory for {account_type.name}: {e}")
        
        # Ensure account_category is set before proceeding
        if not account_category:
            raise ValueError(f"AccountCategory is None for account type {type_name}")
        
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
        
    except Exception as e:
        # Log the error and re-raise with more context
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in get_account for code={code}, name={name}, type={account_type_name}: {e}")
        raise
>>>>>>> 8f6d5a6faa537f99b7aab118429879e683d07a2b


def get_or_create_account_group(name, account_type_name=None):
    """Helper to get or create an account group - FIXED: Now properly sets account_type"""
    # Determine account type name if not provided
    if not account_type_name:
        # Guess from group name
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
            account_type_name = 'Asset'  # Default
    
    # Get or create account type
    account_type = get_or_create_account_type(account_type_name)
    
    group, created = AccountGroup.objects.get_or_create(
        name=name,
        defaults={
            'account_type': account_type,  # FIXED: Now properly set
            'display_order': 10,
            'is_active': True,
            'code_range_start': '1000',
            'code_range_end': '9999',
        }
    )
    return group


def get_account(code, name=None, account_type_name=None):
    """
    Get or create an account by code with all required fields.
    This ensures account_category is always set.
    """
    # First, determine the category based on account type or code
    if account_type_name:
        type_name = account_type_name.capitalize()
        
        # Map account type to category
        category_map = {
            'Asset': 'Assets',
            'Liability': 'Liabilities',
            'Equity': 'Equity',
            'Revenue': 'Revenue',
            'Income': 'Revenue',
            'Expense': 'Expenses',
        }
        
        category_name = category_map.get(type_name, 'Assets')
        
        # Map to group name
        group_map = {
            'Asset': 'Current Assets',
            'Liability': 'Current Liabilities',
            'Equity': 'Share Capital',
            'Revenue': 'Sales Revenue',
            'Income': 'Sales Revenue',
            'Expense': 'Operating Expenses',
        }
        group_name = group_map.get(type_name, 'Other Accounts')
        
    else:
        # Guess from code prefix
        if code.startswith('1'):
            category_name = 'Assets'
            type_name = 'Asset'
            group_name = 'Current Assets'
        elif code.startswith('2'):
            category_name = 'Liabilities'
            type_name = 'Liability'
            group_name = 'Current Liabilities'
        elif code.startswith('3'):
            category_name = 'Equity'
            type_name = 'Equity'
            group_name = 'Share Capital'
        elif code.startswith('4'):
            category_name = 'Revenue'
            type_name = 'Revenue'
            group_name = 'Sales Revenue'
        elif code.startswith('5'):
            category_name = 'Expenses'
            type_name = 'Expense'
            group_name = 'Operating Expenses'
        else:
            category_name = 'Assets'
            type_name = 'Asset'
            group_name = 'Other Assets'
    
    # Get or create all required related objects
    account_group = get_or_create_account_group(group_name, type_name)
    account_category = get_or_create_account_category(category_name)
    account_type = get_or_create_account_type(type_name)
    
    # Now create or get the account with all required fields
    try:
        account = Account.objects.get(code=code)
        # Update name if provided and different
        if name and account.name != name:
            account.name = name
            account.save(update_fields=['name'])
        return account
    except Account.DoesNotExist:
        account = Account.objects.create(
            code=code,
            name=name or code,
            account_type=account_type,
            account_category=account_category,
            account_group=account_group,
            is_active=True,
            allow_manual_entries=True,
            opening_balance=Decimal('0.00'),
            current_balance=Decimal('0.00'),
        )
        return account


# ============================
# Sales Invoice Journal Entry Functions
# ============================

def create_invoice_journal_entry(invoice):
    """
    Create journal entry for sales invoice
    Dr Accounts Receivable
    Cr Sales Revenue
    Cr VAT Payable (if tax applies)
    """
    try:
        with transaction.atomic():
            # Get or create accounts
            ar_account = get_account('1100', 'Accounts Receivable - Trade', 'Asset')
            sales_account = get_account('4000', 'Sales Revenue', 'Revenue')
            
            # Calculate tax amount
            tax_amount = invoice.tax_amount if hasattr(invoice, 'tax_amount') else 0
            
            # Create journal entry
            je = JournalEntry.objects.create(
                company=invoice.company,
                entry_date=invoice.invoice_date,
                reference=invoice.invoice_number,
                narration=f"Invoice {invoice.invoice_number} for {invoice.customer.name}",
                is_posted=True,
                posted_at=timezone.now()
            )
            
            # Dr Accounts Receivable
            JournalLine.objects.create(
                journal=je,
                account=ar_account,
                debit=invoice.total_amount,
                narration=f"Invoice {invoice.invoice_number}"
            )
            
            # Cr Sales Revenue
            JournalLine.objects.create(
                journal=je,
                account=sales_account,
                credit=invoice.total_amount - tax_amount,
                narration=f"Sales revenue - {invoice.invoice_number}"
            )
            
            # Cr VAT Payable if tax exists
            if tax_amount and tax_amount > 0:
                vat_account = get_account('2200', 'VAT Payable', 'Liability')
                
                JournalLine.objects.create(
                    journal=je,
                    account=vat_account,
                    credit=tax_amount,
                    narration=f"VAT on {invoice.invoice_number}"
                )
            
            # Link journal entry to invoice
            invoice.journal_entry = je
            invoice.status = 'posted'
            invoice.save(update_fields=['journal_entry', 'status'])
            
            return je
            
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to create journal entry for invoice {invoice.invoice_number}: {e}")
        raise


def create_payment_journal_entry(payment):
    """
    Create journal entry for payment
    Customer Receipt: Dr Cash, Cr Accounts Receivable
    Supplier Payment: Dr Accounts Payable, Cr Cash
    """
    try:
        with transaction.atomic():
            # Get or create accounts
            cash_account = get_account('1010', 'Cash/Bank', 'Asset')
            ar_account = get_account('1100', 'Accounts Receivable - Trade', 'Asset')
            ap_account = get_account('2100', 'Accounts Payable - Trade', 'Liability')
            
            # Determine company and party name
            company = None
            party_name = ""
            if payment.payment_type == 'customer' and payment.customer:
                company = payment.customer.company
                party_name = payment.customer.name
            elif payment.payment_type == 'supplier' and payment.supplier:
                company = payment.supplier.company
                party_name = payment.supplier.name
            
            # Create journal entry
            je = JournalEntry.objects.create(
                company=company,
                entry_date=payment.date,
                reference=payment.reference or f"PMT-{payment.id}",
                narration=f"Payment {'from' if payment.payment_type == 'customer' else 'to'} {party_name}",
                is_posted=True,
                posted_at=timezone.now()
            )
            
            if payment.payment_type == 'customer':
                # Customer receipt: Dr Cash, Cr AR
                JournalLine.objects.create(
                    journal=je,
                    account=cash_account,
                    debit=payment.amount,
                    narration=f"Payment from {party_name}"
                )
                JournalLine.objects.create(
                    journal=je,
                    account=ar_account,
                    credit=payment.amount,
                    narration=f"Payment from {party_name}"
                )
                
            elif payment.payment_type == 'supplier':
                # Supplier payment: Dr AP, Cr Cash
                JournalLine.objects.create(
                    journal=je,
                    account=ap_account,
                    debit=payment.amount,
                    narration=f"Payment to {party_name}"
                )
                JournalLine.objects.create(
                    journal=je,
                    account=cash_account,
                    credit=payment.amount,
                    narration=f"Payment to {party_name}"
                )
            
            # Link journal entry to payment
            payment.journal_entry = je
            payment.save(update_fields=['journal_entry'])
            
            return je
            
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to create journal entry for payment {payment.id}: {e}")
        raise


# ============================
# Journal Entry Signals
# ============================

@receiver(post_save, sender=JournalEntry)
def post_journal_update_balances(sender, instance, created, **kwargs):
    """Update account balances when a journal entry is posted"""
    if instance.is_posted and not created:
        for line in instance.lines.all():
            if line.account:
                line.account.update_balance()


# ============================
# Purchase Bill Signals
# ============================

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
    try:
        if not created and instance.status == 'posted' and not instance.journal_entry:
            with transaction.atomic():
                # Get or create default accounts
                inventory_account = get_account('1300', 'Raw Materials & Packing Inventory', 'Asset')
                ap_account = get_account('2100', 'Accounts Payable - Trade', 'Liability')
                
                je = JournalEntry.objects.create(
                    company=instance.supplier.company if instance.supplier else None,
                    entry_date=instance.bill_date,
                    reference=instance.bill_number,
                    narration=f"Purchase Bill {instance.bill_number} - {instance.supplier.name if instance.supplier else ''}",
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
    except Exception as e:
        # Log error but don't crash
        print(f"Error in purchase bill signal: {e}")


# ============================
# Payment Signals
# ============================

@receiver(post_save, sender=Payment)
def auto_post_payment(sender, instance, created, **kwargs):
    """
    Automatically create journal entry for payments
    Customer Receipt: Dr Cash, Cr Accounts Receivable
    Supplier Payment: Dr Accounts Payable, Cr Cash
    """
    try:
        if created and not instance.journal_entry:
            with transaction.atomic():
                # Get or create accounts
                cash_account = get_account('1010', 'Cash/Bank', 'Asset')
                ar_account = get_account('1100', 'Accounts Receivable - Trade', 'Asset')
                ap_account = get_account('2100', 'Accounts Payable - Trade', 'Liability')
                
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
                
                if instance.payment_type == 'customer':
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
                    
                elif instance.payment_type == 'supplier':
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
    except Exception as e:
        print(f"Error in payment signal: {e}")


# ============================
# Goods Receipt Signals
# ============================

@receiver(post_save, sender=GoodsReceipt)
def auto_post_goods_receipt(sender, instance, created, **kwargs):
    """
    Automatically create journal entry for goods receipt
    Dr Inventory
    Cr Goods Received Not Invoiced (Accrual)
    """
    try:
        if created:
            with transaction.atomic():
                # Get or create accounts with proper types
                inventory_account = get_account('1300', 'Raw Materials & Packing Inventory', 'Asset')
                accrual_account = get_account('2110', 'Goods Received Not Invoiced', 'Liability')
                
                # Calculate total received value
                total_received_value = Decimal('0')
                for line in instance.lines.all():
                    if line.po_line and line.po_line.unit_price:
                        value = Decimal(str(line.quantity_received)) * Decimal(str(line.po_line.unit_price))
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
    except Exception as e:
        print(f"Error in goods receipt signal: {e}")


# ============================
# Stock Transaction Signals
# ============================

@receiver(post_save, sender=StockTransaction)
def auto_post_stock_adjustment(sender, instance, created, **kwargs):
    """
    Automatically create journal entry for stock adjustments/scrap
    Positive adjustment: Dr Inventory, Cr Variance
    Negative adjustment/scrap: Cr Inventory, Dr Variance
    """
    try:
        if created and instance.transaction_type in ['adjustment', 'scrap']:
            with transaction.atomic():
                inventory_account = get_account('1300', 'Inventory', 'Asset')
                variance_account = get_account('5900', 'Inventory Variance / Scrap', 'Expense')
                
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
    except Exception as e:
        print(f"Error in stock transaction signal: {e}")


# ============================
# Production Run Signals
# ============================

@receiver(post_save, sender=ProductionRun)
def auto_post_production_completion(sender, instance, created, **kwargs):
    """
    Automatically create journal entry when production run is completed
    Dr Finished Goods Inventory
    Cr Work In Process / Raw Materials
    """
    try:
        if not created and instance.status == 'completed':
            # This is a placeholder - implement based on your costing method
            # You would need to calculate the cost of finished goods
            pass
    except Exception as e:
        print(f"Error in production run signal: {e}")