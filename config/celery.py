"""Celery application for AI Interview Prep.

``celery`` and ``redis`` were already dependencies and ``CELERY_*`` settings already
existed, but no app instance was ever created -- so nothing could actually be
enqueued. This wires it up.

Settings are read from Django with the ``CELERY_`` namespace, matching the keys
already defined in ``config/settings/base.py``.

To run a worker:

    celery -A config worker -l info
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("ai_interview_prep")

# Read CELERY_-prefixed settings (CELERY_BROKER_URL, CELERY_TASK_SERIALIZER, ...).
app.config_from_object("django.conf:settings", namespace="CELERY")

# Discover tasks.py in every installed app.
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self) -> str:
    """Trivial task for confirming a worker is connected and consuming."""
    return f"ok from {self.request.id}"
