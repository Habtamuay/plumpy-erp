import requests
from django.conf import settings
from .models import Currency, RolePermission, UserRole

class CurrencyService:
    @staticmethod
    def update_live_rates():
        # Example using a free API
        api_url = "https://open.er-api.com/v6/latest/USD" 
        response = requests.get(api_url).json()
        
        if response.get('result') == 'success':
            rates = response.get('rates')
            for code, rate in rates.items():
                Currency.objects.filter(code=code).update(
                    exchange_rate=rate
                )
            return True
        return False


def user_has_permission(user, company, module, action):
    """
    Check custom ERP RBAC permission:
    User -> UserRole -> RolePermission -> Permission(module/action)
    """
    if not user or not user.is_authenticated:
        return False

    if not company:
        return False

    roles = UserRole.objects.filter(
        user=user,
        company=company
    ).values_list('role_id', flat=True)

    if not roles:
        return False

    return RolePermission.objects.filter(
        role_id__in=roles,
        permission__company=company,
        permission__module=module,
        permission__action=action,
    ).exists()
