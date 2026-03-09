from functools import wraps

from django.http import HttpResponseForbidden

from apps.core.services import user_has_permission


def require_permission(module, action):
    """
    Decorator for ERP RBAC checks.
    Expects company context on request.company (set by CompanyMiddleware).
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            company = getattr(request, 'company', None)
            if not user_has_permission(request.user, company, module, action):
                return HttpResponseForbidden("Permission denied")
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator

