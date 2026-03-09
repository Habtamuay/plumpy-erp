from decimal import Decimal

from apps.accounting.models import JournalEntry, JournalLine


def _d(value):
    if value is None:
        return Decimal('0.00')
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def create_journal_entry(company, lines, reference=None, narration=''):
    """
    Create a balanced journal entry using existing accounting models.
    `lines` expects dicts with:
    - account: Account instance
    - debit: amount
    - credit: amount
    - description (optional)
    """
    if not lines:
        raise ValueError("Journal entry requires at least one line")

    total_debit = sum((_d(line.get('debit')) for line in lines), Decimal('0.00'))
    total_credit = sum((_d(line.get('credit')) for line in lines), Decimal('0.00'))

    if total_debit != total_credit:
        raise ValueError("Journal entry not balanced")

    entry = JournalEntry.objects.create(
        company=company,
        reference=reference or '',
        narration=narration or reference or '',
        is_posted=True,
    )

    for line in lines:
        JournalLine.objects.create(
            company=company,
            journal=entry,
            account=line['account'],
            debit=_d(line.get('debit')),
            credit=_d(line.get('credit')),
            narration=line.get('description', ''),
        )

    return entry

