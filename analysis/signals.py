from django.db.models.signals import pre_delete, post_delete
from analysis.models import Analysis
from django.dispatch import receiver
from transect_web.settings import env
import os
import shutil
import time

# defining a receiver function and what signal it connects to and the sender model
@receiver(pre_delete, sender=Analysis)
def delete_associated_directory(sender, instance, **kwargs):
    analysisOutDir = os.path.join(env('OUTPUT_DIR'), instance.sha_hash)
    try:
        shutil.rmtree(analysisOutDir)
    except:
        pass

    if os.path.exists(analysisOutDir + ".zip"):
        os.remove(analysisOutDir + ".zip")
    if os.path.exists(analysisOutDir + "_no_gsea.zip"):
        os.remove(analysisOutDir + "_no_gsea.zip")