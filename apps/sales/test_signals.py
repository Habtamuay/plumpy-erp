from django.test import TestCase
from django.utils import timezone
from decimal import Decimal

# Import relevant models
from apps.sales.models import SalesInvoice
from apps.company.models import Company, Customer
from apps.accounting.models import JournalEntry

class SalesInvoiceSignalTest(TestCase):
    def setUp(self):
        # Create required dependencies
        self.company = Company.objects.create(name="Test Tech Inc.")
        self.customer = Customer.objects.create(
            name="John Doe", 
            company=self.company
        )
        
        # Create an invoice in 'draft' status
        self.invoice = SalesInvoice.objects.create(
            company=self.company,
            customer=self.customer,
            due_date=timezone.now().date(),
            status='draft'
        )
        
        # Manually set the total_amount for testing.
        # (Normally calculated via lines, but we want to test the signal logic specifically)
        SalesInvoice.objects.filter(pk=self.invoice.pk).update(total_amount=Decimal('500.00'))
        self.invoice.refresh_from_db()

    def test_signal_creates_journal_entry_on_post(self):
        """
        Verifies that changing a SalesInvoice status to 'posted' triggers
        the signal to create a corresponding JournalEntry.
        """
        # Ensure no JE exists initially
        self.assertIsNone(self.invoice.journal_entry)

        # Action: Change status to posted
        self.invoice.status = 'posted'
        self.invoice.save()
        
        # Reload instance to get generated fields
        self.invoice.refresh_from_db()
        
        # Assertion 1: Check Journal Entry Header
        self.assertIsNotNone(self.invoice.journal_entry, "Journal Entry should be created")
        je = self.invoice.journal_entry
        
        self.assertEqual(je.company, self.company)
        self.assertEqual(je.reference, self.invoice.invoice_number)
        self.assertTrue(je.is_posted)
        self.assertEqual(je.entry_date, self.invoice.invoice_date)
        
        # Assertion 2: Check Journal Entry Lines
        self.assertEqual(je.lines.count(), 2, "Should have exactly 2 journal lines")
        
        # Check for Accounts Receivable (Debit)
        ar_line = je.lines.filter(account__code='1100').first()
        self.assertIsNotNone(ar_line, "AR Account 1100 line missing")
        self.assertEqual(ar_line.debit, Decimal('500.00'))
        self.assertEqual(ar_line.credit, Decimal('0.00'))
        
        # Check for Sales Revenue (Credit)
        rev_line = je.lines.filter(account__code='4000').first()
        self.assertIsNotNone(rev_line, "Revenue Account 4000 line missing")
        self.assertEqual(rev_line.credit, Decimal('500.00'))
        self.assertEqual(rev_line.debit, Decimal('0.00'))

    def test_signal_does_not_duplicate_entry(self):
        """Verifies that saving an already posted invoice doesn't create duplicate JEs."""
        # First post
        self.invoice.status = 'posted'
        self.invoice.save()
        self.invoice.refresh_from_db()
        first_je_id = self.invoice.journal_entry.id
        
        # Save again (e.g. updating notes)
        self.invoice.notes = "Updated notes"
        self.invoice.save()
        self.invoice.refresh_from_db()
        
        self.assertEqual(self.invoice.journal_entry.id, first_je_id, "Journal Entry ID should not change")
        self.assertEqual(JournalEntry.objects.filter(reference=self.invoice.invoice_number).count(), 1, "Should not create duplicate entries")

    def test_signal_creates_journal_entry_with_vat(self):
        """
        Verifies that an invoice with tax creates a 3-line journal entry:
        - Debit AR (Total)
        - Credit Revenue (Subtotal)
        - Credit VAT Payable (Tax)
        """
        # 1. Setup invoice with tax
        invoice = SalesInvoice.objects.create(
            company=self.company,
            customer=self.customer,
            due_date=timezone.now().date(),
            status='draft',
            subtotal=Decimal('1000.00'),
            tax_rate=Decimal('15.00'),
            tax_amount=Decimal('150.00'),
            total_amount=Decimal('1150.00')
        )
        self.assertIsNone(invoice.journal_entry)

        # 2. Action: Post the invoice
        invoice.status = 'posted'
        invoice.save()
        invoice.refresh_from_db()

        # 3. Assertions
        self.assertIsNotNone(invoice.journal_entry)
        je = invoice.journal_entry
        self.assertEqual(je.lines.count(), 3, "Should have 3 journal lines for invoice with tax")

        # Check AR line (Debit)
        self.assertTrue(je.lines.filter(account__code='1100', debit=Decimal('1150.00')).exists())

        # Check Revenue line (Credit)
        self.assertTrue(je.lines.filter(account__code='4000', credit=Decimal('1000.00')).exists())

        # Check VAT Payable line (Credit)
        self.assertTrue(je.lines.filter(account__code='2200', credit=Decimal('150.00')).exists(), "VAT Payable line is missing or incorrect.")
