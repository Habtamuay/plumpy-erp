from apps.company.models import Company


def company_context(request):
    """
    Context processor to add company information to all templates.
    """
    context = {}

    if hasattr(request, 'company'):
        context['current_company'] = request.company
        # Get all active companies for company switcher
        context['available_companies'] = Company.objects.filter(is_active=True)
    else:
        context['current_company'] = None
        context['available_companies'] = []

    return context