import logging
from django.utils import timezone
from apps.accounting.models import JournalEntry, JournalLine, Account, AccountType, AccountCategory

logger = logging.getLogger(__name__)

def create_invoice_journal_entry(invoice):
    """Create journal entry for invoice"""
    try:
        company = invoice.company
        # Get accounts (with fallback creation if not exists)
        ar_account = Account.objects.filter(code='1100', company=company).first()
        sales_account = Account.objects.filter(code='4100', company=company).first()
        
        if not ar_account:
            asset_type, _ = AccountType.objects.get_or_create(name='Asset', company=company)
            current_asset_cat, _ = AccountCategory.objects.get_or_create(name='Current Asset', company=company)
            ar_account = Account.objects.create(
                company=company,
                code='1100',
                name='Accounts Receivable',
                account_type=asset_type,
                account_category=current_asset_cat
            )
        
        if not sales_account:
            revenue_type, _ = AccountType.objects.get_or_create(name='Revenue', company=company)
            revenue_cat, _ = AccountCategory.objects.get_or_create(name='Revenue', company=company)
            sales_account = Account.objects.create(
                company=company,
                code='4100',
                name='Sales Revenue',
                account_type=revenue_type,
                account_category=revenue_cat
            )
        
        # Create journal entry
        je = JournalEntry.objects.create(
            company=company,
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
            credit=invoice.total_amount - (invoice.tax_amount or 0),
            narration=f"Sales revenue - {invoice.invoice_number}"
        )
        
        # Cr VAT Payable if tax exists
        if invoice.tax_amount and invoice.tax_amount > 0:
            vat_account = Account.objects.filter(code='2200', company=company).first()
            if not vat_account:
                liability_type, _ = AccountType.objects.get_or_create(name='Liability', company=company)
                current_liability_cat, _ = AccountCategory.objects.get_or_create(name='Current Liability', company=company)
                vat_account = Account.objects.create(
                    company=company,
                    code='2200',
                    name='VAT Payable',
                    account_type=liability_type,
                    account_category=current_liability_cat
                )
            
            JournalLine.objects.create(
                journal=je,
                account=vat_account,
                credit=invoice.tax_amount,
                narration=f"VAT on {invoice.invoice_number}"
            )
        
        # Link journal entry to invoice
        invoice.journal_entry = je
        invoice.status = 'posted'
        invoice.save(update_fields=['journal_entry', 'status'])
        
    except Exception as e:
        logger.error(f"Failed to create journal entry for invoice {invoice.invoice_number}: {e}")
        raise

def create_payment_journal_entry(payment):
    """Create journal entry for payment"""
    try:
        company = payment.invoice.company
        # Get accounts
        cash_account = Account.objects.filter(code='1010', company=company).first()
        ar_account = Account.objects.filter(code='1100', company=company).first()
        
        if not cash_account or not ar_account:
            asset_type, _ = AccountType.objects.get_or_create(name='Asset', company=company)
            current_asset_cat, _ = AccountCategory.objects.get_or_create(name='Current Asset', company=company)

        if not cash_account:
            cash_account = Account.objects.create(
                company=company,
                code='1010',
                name='Cash/Bank',
                account_type=asset_type,
                account_category=current_asset_cat
            )
        
        if not ar_account:
            ar_account = Account.objects.create(
                company=company,
                code='1100',
                name='Accounts Receivable',
                account_type=asset_type,
                account_category=current_asset_cat
            )
        
        # Create journal entry
        je = JournalEntry.objects.create(
            company=company,
            entry_date=payment.payment_date,
            reference=f"PAY-{payment.id}",
            narration=f"Payment received for {payment.invoice.invoice_number}",
            is_posted=True,
            posted_at=timezone.now()
        )
        
        # Dr Cash/Bank
        JournalLine.objects.create(
            journal=je,
            account=cash_account,
            debit=payment.amount,
            narration=f"Payment from {payment.invoice.customer.name}"
        )
        
        # Cr Accounts Receivable
        JournalLine.objects.create(
            journal=je,
            account=ar_account,
            credit=payment.amount,
            narration=f"Payment for {payment.invoice.invoice_number}"
        )
        
        # Link journal entry to payment
        payment.journal_entry = je
        payment.save(update_fields=['journal_entry'])
        
    except Exception as e:
        logger.error(f"Failed to create journal entry for payment {payment.id}: {e}")