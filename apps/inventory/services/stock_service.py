from decimal import Decimal

from django.db.models import Sum

from apps.inventory.models import StockLedger


def _to_decimal(value):
    if value is None:
        return Decimal('0')
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def get_stock_balance(company, product, warehouse):
    """
    Return stock balance for one product in one warehouse.
    """
    entries = StockLedger.objects.filter(
        company=company,
        product=product,
        warehouse=warehouse,
    )

    qty_in = entries.aggregate(total=Sum('quantity_in'))['total'] or Decimal('0')
    qty_out = entries.aggregate(total=Sum('quantity_out'))['total'] or Decimal('0')
    return qty_in - qty_out


def create_stock_entry(
    company,
    product,
    warehouse,
    qty_in=0,
    qty_out=0,
    document_type=None,
    document_id=None,
    unit_cost=0,
    posting_date=None,
):
    """
    Create one stock ledger row and recompute running balance.
    """
    qty_in = _to_decimal(qty_in)
    qty_out = _to_decimal(qty_out)
    unit_cost = _to_decimal(unit_cost)

    last_entry = StockLedger.objects.filter(
        company=company,
        product=product,
        warehouse=warehouse,
    ).order_by('-posting_date', '-id').first()

    previous_balance = last_entry.balance_quantity if last_entry else Decimal('0')
    new_balance = previous_balance + qty_in - qty_out
    total_value = (new_balance * unit_cost).quantize(Decimal('0.01'))

    payload = {
        'company': company,
        'product': product,
        'warehouse': warehouse,
        'document_type': document_type or '',
        'document_id': document_id,
        'quantity_in': qty_in,
        'quantity_out': qty_out,
        'balance_quantity': new_balance,
        'unit_cost': unit_cost,
        'total_value': total_value,
    }
    if posting_date is not None:
        payload['posting_date'] = posting_date

    return StockLedger.objects.create(
        **payload,
    )
