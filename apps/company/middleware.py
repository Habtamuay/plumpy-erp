from django.utils.deprecation import MiddlewareMixin
from django.shortcuts import redirect
from django.urls import reverse
from apps.company.models import Company


class CompanyMiddleware(MiddlewareMixin):
    """
    Middleware to handle company context for multi-company support.
    Sets the current company in session based on user selection or default.
    """

    def process_view(self, request, view_func, view_args, view_kwargs):
        # Skip middleware for URLs that must work without a selected company
        exempt_urls = [
            '/admin/',
            '/accounts/',
            '/api/',
            reverse('core:home'),
            reverse('company:create'),
        ]

        if any(request.path.startswith(url) for url in exempt_urls):
            return None

        # If user is not authenticated, skip
        if not request.user.is_authenticated:
            return None

        # Get current company from session
        current_company_id = request.session.get('current_company_id')

        if current_company_id:
            try:
                company = Company.objects.get(id=current_company_id, is_active=True)
                request.company = company
            except Company.DoesNotExist:
                # Company doesn't exist or inactive, clear session
                request.session.pop('current_company_id', None)
                request.session.pop('current_company_name', None)
                current_company_id = None

        # If no company is selected, send user to company selector page
        if not current_company_id:
            has_company = Company.objects.filter(is_active=True).exists()
            if not has_company:
                return redirect('company:create')
            return redirect('core:home')

        return None
