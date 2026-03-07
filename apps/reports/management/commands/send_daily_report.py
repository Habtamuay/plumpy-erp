from django.core.management.base import BaseCommand
from apps.reports.email_service import EmailAutomationService

class Command(BaseCommand):
    help = 'Sends a daily summary email to the administrator'

    def handle(self, *args, **kwargs):
        admin_email = "admin@yourcompany.com"
        EmailAutomationService.send_daily_summary(admin_email)
        self.stdout.write(self.style.SUCCESS(f'Successfully sent report to {admin_email}'))