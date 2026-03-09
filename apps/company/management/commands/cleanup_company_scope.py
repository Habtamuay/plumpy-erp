from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.company.models import Company
from apps.purchasing.models import (
    Supplier,
    PurchaseOrder,
    PurchaseRequisition,
    PurchaseOrderLine,
    PurchaseOrderApproval,
    GoodsReceipt,
    GoodsReceiptLine,
    PurchaseRequisitionLine,
    VendorPerformance,
)
from apps.sales.models import (
    SalesOrder,
    SalesOrderLine,
    SalesInvoice,
    SalesInvoiceLine,
    SalesShipment,
    SalesShipmentLine,
    SalesPayment,
)
from apps.accounting.models import (
    AccountType,
    AccountGroup,
    AccountCategory,
    Account,
    JournalLine,
    PurchaseBill,
    PurchaseBillLine,
    Payment,
    ReconciliationAuditLog,
)
from apps.reports.models import (
    ReportCategory,
    ReportTemplate,
    ScheduledReport,
    DashboardWidget,
)


class Command(BaseCommand):
    help = (
        "Backfill legacy company scope fields across Purchasing/Sales/Accounting/Reports. "
        "Runs in dry-run mode by default. Use --commit to apply."
    )

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, help="Default company ID to use as fallback")
        parser.add_argument("--company-name", type=str, help="Default company name to use as fallback")
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Apply updates. Without this flag, command only reports planned changes.",
        )

    def handle(self, *args, **options):
        default_company = self._resolve_default_company(options)
        if not default_company:
            raise CommandError(
                "No active company found. Create/select a company first, or pass --company-id/--company-name."
            )

        dry_run = not options["commit"]
        mode = "DRY RUN" if dry_run else "COMMIT"
        self.stdout.write(self.style.WARNING(f"Running cleanup_company_scope in {mode} mode"))
        self.stdout.write(
            f"Default fallback company: {default_company.id} - {default_company.name}"
        )

        stats = {}
        with transaction.atomic():
            # Purchasing header models with string company field
            stats["supplier_company_name"] = self._fill_supplier_company_name(default_company, dry_run)
            stats["po_company_name"] = self._fill_po_company_name(default_company, dry_run)
            stats["pr_company_name"] = self._fill_pr_company_name(default_company, dry_run)

            # Purchasing models with FK company field
            stats["po_line_company_fk"] = self._fill_po_line_company_fk(default_company, dry_run)
            stats["po_approval_company_fk"] = self._fill_po_approval_company_fk(default_company, dry_run)
            stats["goods_receipt_company_fk"] = self._fill_goods_receipt_company_fk(default_company, dry_run)
            stats["goods_receipt_line_company_fk"] = self._fill_goods_receipt_line_company_fk(default_company, dry_run)
            stats["pr_line_company_fk"] = self._fill_pr_line_company_fk(default_company, dry_run)
            stats["vendor_perf_company_fk"] = self._fill_vendor_perf_company_fk(default_company, dry_run)

            # Sales
            stats["sales_order_company_fk"] = self._fill_sales_order_company(default_company, dry_run)
            stats["sales_order_line_company_fk"] = self._fill_from_parent(SalesOrderLine, "order__company_id", dry_run)
            stats["sales_invoice_company_fk"] = self._fill_sales_invoice_company(default_company, dry_run)
            stats["sales_invoice_line_company_fk"] = self._fill_from_parent(SalesInvoiceLine, "invoice__company_id", dry_run)
            stats["sales_shipment_company_fk"] = self._fill_from_parent(SalesShipment, "sales_order__company_id", dry_run)
            stats["sales_shipment_line_company_fk"] = self._fill_from_parent(SalesShipmentLine, "shipment__company_id", dry_run)
            stats["sales_payment_company_fk"] = self._fill_from_parent(SalesPayment, "invoice__company_id", dry_run)

            # Accounting
            stats["account_type_company_fk"] = self._bulk_set_default(AccountType, default_company, dry_run)
            stats["account_group_company_fk"] = self._fill_from_parent(AccountGroup, "account_type__company_id", dry_run, default_company)
            stats["account_category_company_fk"] = self._fill_from_parent(AccountCategory, "account_group__company_id", dry_run, default_company)
            stats["account_company_fk"] = self._fill_from_parent(Account, "account_type__company_id", dry_run, default_company)
            stats["journal_line_company_fk"] = self._fill_from_parent(JournalLine, "journal__company_id", dry_run, default_company)
            stats["purchase_bill_company_fk"] = self._fill_purchase_bill_company(default_company, dry_run)
            stats["purchase_bill_line_company_fk"] = self._fill_from_parent(PurchaseBillLine, "bill__company_id", dry_run, default_company)
            stats["payment_company_fk"] = self._fill_payment_company(default_company, dry_run)
            stats["recon_audit_company_fk"] = self._fill_from_parent(
                ReconciliationAuditLog, "payment__company_id", dry_run, default_company
            )

            # Reports
            stats["report_category_company_fk"] = self._bulk_set_default(ReportCategory, default_company, dry_run)
            stats["report_template_company_fk"] = self._fill_from_parent(ReportTemplate, "category__company_id", dry_run, default_company)
            stats["scheduled_report_company_fk"] = self._fill_from_parent(ScheduledReport, "report__company_id", dry_run, default_company)
            stats["dashboard_widget_company_fk"] = self._fill_dashboard_widget_company(default_company, dry_run)

            if dry_run:
                transaction.set_rollback(True)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Cleanup summary:"))
        for key, value in stats.items():
            self.stdout.write(f"  - {key}: {value}")

        if dry_run:
            self.stdout.write(self.style.WARNING("No data changed (dry run). Re-run with --commit to apply."))
        else:
            self.stdout.write(self.style.SUCCESS("Company scope cleanup committed successfully."))

    def _resolve_default_company(self, options):
        cid = options.get("company_id")
        cname = options.get("company_name")
        if cid:
            company = Company.objects.filter(id=cid, is_active=True).first()
            if not company:
                raise CommandError(f"No active company found with id={cid}")
            return company
        if cname:
            company = Company.objects.filter(name=cname, is_active=True).first()
            if not company:
                raise CommandError(f"No active company found with name='{cname}'")
            return company
        return Company.objects.filter(is_active=True).order_by("id").first()

    def _bulk_set_default(self, model, default_company, dry_run):
        qs = model.objects.filter(company__isnull=True)
        count = qs.count()
        if count and not dry_run:
            qs.update(company=default_company)
        return count

    def _fill_from_parent(self, model, parent_company_lookup, dry_run, default_company=None):
        """
        Set model.company from related parent's company_id if present.
        """
        updated = 0
        for obj in model.objects.filter(company__isnull=True).iterator():
            parent_company_id = (
                model.objects.filter(id=obj.id)
                .values_list(parent_company_lookup, flat=True)
                .first()
            )
            company_id = parent_company_id or (default_company.id if default_company else None)
            if company_id:
                updated += 1
                if not dry_run:
                    model.objects.filter(id=obj.id).update(company_id=company_id)
        return updated

    def _company_by_name(self, name):
        if not name:
            return None
        return Company.objects.filter(name=name, is_active=True).first()

    def _fill_supplier_company_name(self, default_company, dry_run):
        qs = Supplier.objects.filter(company__isnull=True) | Supplier.objects.filter(company="")
        count = qs.count()
        if count and not dry_run:
            qs.update(company=default_company.name)
        return count

    def _fill_po_company_name(self, default_company, dry_run):
        updated = 0
        for po in PurchaseOrder.objects.filter(company__isnull=True) | PurchaseOrder.objects.filter(company=""):
            inferred = po.supplier.company if po.supplier and po.supplier.company else default_company.name
            updated += 1
            if not dry_run:
                PurchaseOrder.objects.filter(id=po.id).update(company=inferred)
        return updated

    def _fill_pr_company_name(self, default_company, dry_run):
        qs = PurchaseRequisition.objects.filter(company__isnull=True) | PurchaseRequisition.objects.filter(company="")
        count = qs.count()
        if count and not dry_run:
            qs.update(company=default_company.name)
        return count

    def _fill_po_line_company_fk(self, default_company, dry_run):
        updated = 0
        for line in PurchaseOrderLine.objects.filter(company__isnull=True).select_related("po"):
            po_name = line.po.company if line.po else None
            company = self._company_by_name(po_name) or default_company
            updated += 1
            if not dry_run:
                PurchaseOrderLine.objects.filter(id=line.id).update(company=company)
        return updated

    def _fill_po_approval_company_fk(self, default_company, dry_run):
        updated = 0
        for app in PurchaseOrderApproval.objects.filter(company__isnull=True).select_related("po"):
            po_name = app.po.company if app.po else None
            company = self._company_by_name(po_name) or default_company
            updated += 1
            if not dry_run:
                PurchaseOrderApproval.objects.filter(id=app.id).update(company=company)
        return updated

    def _fill_goods_receipt_company_fk(self, default_company, dry_run):
        updated = 0
        for gr in GoodsReceipt.objects.filter(company__isnull=True).select_related("po"):
            po_name = gr.po.company if gr.po else None
            company = self._company_by_name(po_name) or default_company
            updated += 1
            if not dry_run:
                GoodsReceipt.objects.filter(id=gr.id).update(company=company)
        return updated

    def _fill_goods_receipt_line_company_fk(self, default_company, dry_run):
        updated = 0
        for line in GoodsReceiptLine.objects.filter(company__isnull=True).select_related("receipt"):
            company_id = line.receipt.company_id if line.receipt else None
            if not company_id:
                company_id = default_company.id
            updated += 1
            if not dry_run:
                GoodsReceiptLine.objects.filter(id=line.id).update(company_id=company_id)
        return updated

    def _fill_pr_line_company_fk(self, default_company, dry_run):
        updated = 0
        for line in PurchaseRequisitionLine.objects.filter(company__isnull=True).select_related("requisition"):
            req_name = line.requisition.company if line.requisition else None
            company = self._company_by_name(req_name) or default_company
            updated += 1
            if not dry_run:
                PurchaseRequisitionLine.objects.filter(id=line.id).update(company=company)
        return updated

    def _fill_vendor_perf_company_fk(self, default_company, dry_run):
        updated = 0
        for row in VendorPerformance.objects.filter(company__isnull=True).select_related("supplier"):
            supplier_name = row.supplier.company if row.supplier else None
            company = self._company_by_name(supplier_name) or default_company
            updated += 1
            if not dry_run:
                VendorPerformance.objects.filter(id=row.id).update(company=company)
        return updated

    def _fill_sales_order_company(self, default_company, dry_run):
        updated = 0
        for order in SalesOrder.objects.filter(company__isnull=True).select_related("customer"):
            company_id = order.customer.company_id if order.customer else default_company.id
            updated += 1
            if not dry_run:
                SalesOrder.objects.filter(id=order.id).update(company_id=company_id)
        return updated

    def _fill_sales_invoice_company(self, default_company, dry_run):
        updated = 0
        for invoice in SalesInvoice.objects.filter(company__isnull=True).select_related("sales_order", "customer"):
            company_id = None
            if invoice.sales_order and invoice.sales_order.company_id:
                company_id = invoice.sales_order.company_id
            elif invoice.customer and invoice.customer.company_id:
                company_id = invoice.customer.company_id
            else:
                company_id = default_company.id
            updated += 1
            if not dry_run:
                SalesInvoice.objects.filter(id=invoice.id).update(company_id=company_id)
        return updated

    def _fill_purchase_bill_company(self, default_company, dry_run):
        updated = 0
        for bill in PurchaseBill.objects.filter(company__isnull=True).select_related("purchase_order", "supplier"):
            company_id = None
            if bill.purchase_order and bill.purchase_order.company:
                company = self._company_by_name(bill.purchase_order.company)
                company_id = company.id if company else None
            if not company_id and bill.supplier and bill.supplier.company:
                company = self._company_by_name(bill.supplier.company)
                company_id = company.id if company else None
            company_id = company_id or default_company.id
            updated += 1
            if not dry_run:
                PurchaseBill.objects.filter(id=bill.id).update(company_id=company_id)
        return updated

    def _fill_payment_company(self, default_company, dry_run):
        updated = 0
        for pay in Payment.objects.filter(company__isnull=True).select_related("customer", "supplier"):
            company_id = None
            if pay.customer and pay.customer.company_id:
                company_id = pay.customer.company_id
            elif pay.supplier and pay.supplier.company:
                company = self._company_by_name(pay.supplier.company)
                company_id = company.id if company else None
            company_id = company_id or default_company.id
            updated += 1
            if not dry_run:
                Payment.objects.filter(id=pay.id).update(company_id=company_id)
        return updated

    def _fill_dashboard_widget_company(self, default_company, dry_run):
        updated = 0
        for widget in DashboardWidget.objects.filter(company__isnull=True).select_related("report"):
            company_id = widget.report.company_id if widget.report else default_company.id
            updated += 1
            if not dry_run:
                DashboardWidget.objects.filter(id=widget.id).update(company_id=company_id)
        return updated
