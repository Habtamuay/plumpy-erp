from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import UserActivity

# List the models you want to track
# To keep it simple, we'll assume you import your models here
# from apps.sales.models import SalesOrder, SalesInvoice
# from apps.inventory.models import StockItem

def log_activity(sender, instance, created, **kwargs):
    # This is a simplified version. Usually, you'd use middleware 
    # to get the current request.user.
    action = 'create' if created else 'update'
    # description logic here...
    pass

# You would connect your models here
# post_save.connect(log_activity, sender=SalesOrder)