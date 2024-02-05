from djano.db.models.signals import pre_delete, post_delete
from analysis.models import Student
from django.dispatch import receiver
from sRT_backend.settings import env
import os


# defining a receiver function and what signal it connects to and the sender model
@receiver(pre_delete, sender=Analysis)
def delete_associated_directory(sender, instance, **kwargs):
    analysisOutDir = os.path.join(env('OUTPUT_DIR'), instance.sha_hash + ".zip")
    os.path.remove(analysisOutDir)