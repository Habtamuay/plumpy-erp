from django.db.models.signals import post_save
from django.dispatch import receiver

# Import models from this app
from .models import ProductionRun

@receiver(post_save, sender=ProductionRun)
def auto_post_production_completion(sender, instance, created, **kwargs):
    """
    Journal entry for production completion.
    This is a placeholder for more complex logic, like debiting Finished Goods
    and crediting Work-in-Progress inventory.
    """
    pass