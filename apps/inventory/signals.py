from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from decimal import Decimal

# Import models from this app
from .models import StockTransaction

# Import accounting models and helpers
from apps.accounting.models import JournalEntry, JournalLine
from apps.accounting.utils import get_account


@receiver(post_save, sender=StockTransaction)
def auto_post_stock_adjustment(sender, instance, created, **kwargs):
    """Create journal entry for stock adjustments/scrap"""
    try:
        if created and instance.transaction_type in ['adjustment', 'scrap']:
            with transaction.atomic():
                inventory_account = get_account('1300', 'Inventory', 'Asset')
                variance_account = get_account('5900', 'Inventory Variance / Scrap', 'Expense')
                
                company = None
                if hasattr(instance, 'warehouse_to') and instance.warehouse_to:
                    company = instance.warehouse_to.company
                elif hasattr(instance, 'warehouse_from') and instance.warehouse_from:
                    company = instance.warehouse_from.company
                
                unit_cost = getattr(instance.item, 'unit_cost', Decimal('0.00')) or Decimal('0.00')
                value = abs(instance.quantity) * unit_cost
                
                if value > 0:
                    je = JournalEntry.objects.create(
                        company=company,
                        entry_date=instance.transaction_date.date() if hasattr(instance.transaction_date, 'date') else instance.transaction_date,
                        reference=f"ST-{instance.id}",
                        narration=f"Stock {instance.transaction_type} for {instance.item.code}",
                        is_posted=True,
                        posted_at=timezone.now()
                    )
                    if instance.quantity > 0:
                        JournalLine.objects.create(journal=je, account=inventory_account, debit=value)
                        JournalLine.objects.create(journal=je, account=variance_account, credit=value)
                    else:
                        JournalLine.objects.create(journal=je, account=inventory_account, credit=value)
                        JournalLine.objects.create(journal=je, account=variance_account, debit=value)
    except Exception as e:
        print(f"Error in stock transaction signal: {e}")