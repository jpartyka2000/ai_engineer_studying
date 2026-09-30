"""Project package.

Importing the Celery app here is what makes ``@shared_task`` resolve to the
configured app, so it must happen when Django starts rather than lazily.
"""

from config.celery import app as celery_app

__all__ = ("celery_app",)
