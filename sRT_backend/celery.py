import os

from celery import Celery
from celery.schedules import crontab

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sRT_backend.settings')

app = Celery('sRT_backend')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

app.conf.beat_schedule = {
    'clean_database_and_analysis': {
        'task': 'analysis.tasks.clean_database_and_analysis',
        #'schedule': 900.0,
        'schedule': crontab(minute=0, hour=3),  # Example: Run at 3am every day
    },
}