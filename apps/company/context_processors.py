from apps.company.models import Company


def company_context(request):
    """
    Context processor to add company information to all templates.
    """
    context = {}

    # Get current company from session
    company_id = request.session.get('current_company_id')
    if company_id:
        try:
            company = Company.objects.get(id=company_id, is_active=True)
            context['current_company'] = company
            request.company = company  # Set on request for backward compatibility
        except Company.DoesNotExist:
            context['current_company'] = None
            if 'current_company_id' in request.session:
                del request.session['current_company_id']
            if 'current_company_name' in request.session:
                del request.session['current_company_name']
    else:
        context['current_company'] = None

    # Get all active companies for company switcher
    context['available_companies'] = Company.objects.filter(is_active=True)

    return context