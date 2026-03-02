from django.apps import AppConfig


class PurchasingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.purchasing'  # This must match the path in INSTALLED_APPS
    verbose_name = "Purchasing Management"