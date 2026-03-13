from django.test import TestCase
from decimal import Decimal
from django.utils import timezone
from apps.inventory.models import Warehouse, StockTransaction
from apps.company.models import Company, Customer
from apps.core.models import Item, Unit
from apps.sales.models import SalesOrder, SalesOrderLine, SalesInvoice, SalesShipment, SalesShipmentLine
from apps.accounting.models import JournalEntry

class SalesInvoiceTotalsTest(TestCase):
    def setUp(self):
        """Set up base data for sales tests."""
        self.company = Company.objects.create(name="Test Corp")
        self.customer = Customer.objects.create(name="Test Customer", company=self.company)
        self.unit = Unit.objects.create(name="pcs", code="pcs")
        self.item1 = Item.objects.create(
            name="Item A",
            code="IT-A",
            unit_cost=Decimal("100.00"),
            unit=self.unit,
            company=self.company
        )
        self.item2 = Item.objects.create(
            name="Item B",
            code="IT-B",
            unit_cost=Decimal("250.00"),
            unit=self.unit,
            company=self.company
        )

    def test_invoice_totals_from_order_autofill(self):
        """
        Verify SalesInvoice totals are calculated correctly when its lines are
        autofilled from a SalesOrder on save (which uses bulk_create).
        """
        # 1. Create a SalesOrder with multiple lines and discounts
        order = SalesOrder.objects.create(
            company=self.company,
            customer=self.customer,
            tax_rate=Decimal("10.00")
        )
        SalesOrderLine.objects.create(
            order=order, item=self.item1, quantity=Decimal("2"),
            unit=self.unit, unit_price=Decimal("100.00")
        )  # Line total: 2 * 100 = 200
        SalesOrderLine.objects.create(
            order=order, item=self.item2, quantity=Decimal("3"),
            unit=self.unit, unit_price=Decimal("250.00")
        )  # Line total: 3 * 250 = 750

        # 2. Create a SalesInvoice linked to the order. This triggers `_autofill_lines_from_order`.
        invoice = SalesInvoice.objects.create(
            company=self.company,
            sales_order=order,
            due_date=timezone.now().date()
        )
        invoice.refresh_from_db()

        # 3. Define expected values and assert
        # Subtotal = 200 (line 1) + 750 (line 2) = 950
        self.assertEqual(invoice.subtotal, Decimal("950.00"))
        # Tax is 10% on subtotal: 950 * 0.10 = 95
        self.assertEqual(invoice.tax_amount, Decimal("95.00"))
        # Total = subtotal + tax: 950 + 95 = 1045
        self.assertEqual(invoice.total_amount, Decimal("1045.00"))


class SalesSignalTests(TestCase):
    def setUp(self):
        """Set up base data for sales tests."""
        self.company = Company.objects.create(name="Test Corp")
        self.customer = Customer.objects.create(name="Test Customer", company=self.company)
        self.unit = Unit.objects.create(name="pcs", code="pcs")
        self.item1 = Item.objects.create(
            name="Item A",
            code="IT-A",
            unit_cost=Decimal("100.00"),
            unit=self.unit,
            company=self.company
        )

    def test_auto_create_invoice_from_confirmed_order(self):
        """
        Verify that an invoice is automatically created via signal when a
        SalesOrder is moved to 'confirmed' status.
        """
        # 1. Create a SalesOrder in 'draft' status
        order = SalesOrder.objects.create(
            company=self.company,
            customer=self.customer,
            tax_rate=Decimal("10.00"),
            status='draft'
        )
        SalesOrderLine.objects.create(
            order=order, item=self.item1, quantity=Decimal("2"),
            unit=self.unit, unit_price=Decimal("100.00")
        )
        order.calculate_totals()

        # 2. Confirm no invoice exists yet
        self.assertEqual(order.invoices.count(), 0)

        # 3. Change status to 'confirmed' and save, which triggers the signal
        order.status = 'confirmed'
        order.save()

        # 4. Verify the invoice was created and is linked
        self.assertEqual(order.invoices.count(), 1)
        invoice = order.invoices.first()
        self.assertIsNotNone(invoice)
        self.assertEqual(invoice.lines.count(), 1)

        # 5. Verify invoice totals are correct
        # Subtotal=200. No discount. Taxable=200. Tax=200*10%=20. Total=200+20=220.
        self.assertEqual(invoice.subtotal, Decimal("200.00"))
        self.assertEqual(invoice.tax_amount, Decimal("20.00"))
        self.assertEqual(invoice.total_amount, Decimal("220.00"))

        # 6. Verify order status was updated to 'invoiced'
        order.refresh_from_db()
        self.assertEqual(order.status, 'invoiced')

        # 7. Verify invoice is 'posted'
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'posted')

    def test_confirming_order_with_existing_invoice_does_not_duplicate(self):
        """
        Verify that confirming a SalesOrder that already has an invoice
        does NOT create a second invoice.
        """
        # 1. Create a SalesOrder in 'draft'
        order = SalesOrder.objects.create(
            company=self.company,
            customer=self.customer,
            status='draft'
        )
        SalesOrderLine.objects.create(
            order=order, item=self.item1, quantity=Decimal("1"),
            unit=self.unit, unit_price=Decimal("100.00")
        )

        # 2. Manually create an invoice linked to this order (simulating existing invoice)
        invoice = SalesInvoice.objects.create(
            company=self.company,
            sales_order=order,
            customer=self.customer,
            due_date=timezone.now().date()
        )
        self.assertEqual(order.invoices.count(), 1)

        # 3. Change status to 'confirmed' and save (triggers signal)
        order.status = 'confirmed'
        order.save()

        # 4. Assert that the invoice count is still 1
        self.assertEqual(order.invoices.count(), 1)
        self.assertEqual(order.invoices.first(), invoice)

class SalesShipmentTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Test Corp")
        self.customer = Customer.objects.create(name="Test Customer", company=self.company)
        self.unit = Unit.objects.create(name="pcs", code="pcs")
        self.warehouse = Warehouse.objects.create(name="Main Warehouse", company=self.company)
        self.item = Item.objects.create(
            name="Test Item", code="TEST-ITM", unit_cost=Decimal("10.00"),
            current_stock=Decimal("100.00"), unit=self.unit, company=self.company
        )

    def test_shipment_creates_stock_transaction(self):
        """
        Verify that marking a SalesShipment as 'shipped' creates the correct StockTransaction.
        """
        # 1. Create Order
        order = SalesOrder.objects.create(company=self.company, customer=self.customer, status='confirmed')
        so_line = SalesOrderLine.objects.create(
            order=order, item=self.item, quantity=Decimal("10"), 
            unit=self.unit, unit_price=Decimal("20.00")
        )

        # 2. Create Shipment (Pending)
        shipment = SalesShipment.objects.create(
            company=self.company, sales_order=order, warehouse=self.warehouse, status='pending'
        )
        SalesShipmentLine.objects.create(
            shipment=shipment, sales_order_line=so_line, quantity=Decimal("5")
        )

        # Ensure NO transaction created yet
        self.assertEqual(StockTransaction.objects.count(), 0)

        # 3. Mark as Shipped
        shipment.status = 'shipped'
        shipment.save()

        # 4. Verify Transaction created
        self.assertEqual(StockTransaction.objects.count(), 1)
        txn = StockTransaction.objects.first()
        self.assertEqual(txn.transaction_type, 'issue')
        self.assertEqual(txn.quantity, Decimal("-5.00"))  # Negative for issue
        self.assertEqual(txn.reference, shipment.shipment_number)