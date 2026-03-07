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
        # Skip middleware for certain URLs
        exempt_urls = [
            '/admin/',
            '/accounts/',
            '/api/',
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
                current_company_id = None

        # If no company set, try to get user's default company
        if not current_company_id:
            # Try to get from user profile
            if hasattr(request.user, 'userprofile') and request.user.userprofile.company:
                company = request.user.userprofile.company
                request.company = company
                request.session['current_company_id'] = company.id
            else:
                # Get first active company as default
                try:
                    company = Company.objects.filter(is_active=True).first()
                    if company:
                        request.company = company
                        request.session['current_company_id'] = company.id
                    else:
                        # No companies exist, redirect to company creation
                        if request.path not in ['/company/create/', '/accounts/login/', '/accounts/logout/'] and not request.path.startswith('/admin/'):
                            return redirect('company:create')
                except Company.DoesNotExist:
                    if request.path not in ['/company/create/', '/accounts/login/', '/accounts/logout/'] and not request.path.startswith('/admin/'):
                        return redirect('company:create')

        return None