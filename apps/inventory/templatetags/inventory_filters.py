from django import template

register = template.Library()

@register.filter
def sub(value, arg):
    """Subtract the arg from the value"""
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return 0

@register.simple_tag
def widthdiff(value, arg):
    """Calculate percentage difference"""
    try:
        val = float(value)
        arg = float(arg)
        if arg > 0:
            return ((arg - val) / arg * 100)
        return 0
    except (ValueError, TypeError):
        return 0