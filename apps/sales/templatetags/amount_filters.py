from django import template

register = template.Library()

@register.filter
def amount_in_words(value):
    """Convert a numeric value to words (English) and append 'Birr'.

    Requires the optional dependency `num2words`. If the package is not
    available, it will simply return the original value.
    """
    try:
        from num2words import num2words
    except ImportError:
        return value
    try:
        # num2words will output e.g. "one thousand two hundred".
        words = num2words(value, lang='en')
        return words.replace(' and', '').title() + ' Birr Only'
    except Exception:
        return value
