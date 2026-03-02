from django.apps import AppConfig


class AccountingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.accounting'

    def ready(self):
        import apps.accounting.signals  # noqa