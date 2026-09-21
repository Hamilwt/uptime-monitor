from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "uptime_worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

# This tells Celery to look for @celery_app.task decorators in app/tasks.py
celery_app.autodiscover_tasks(["app"])

# The Dispatcher Pattern: Instead of complex dynamic scheduling, 
# we run one fixed heartbeat that queries Postgres for what to check.
celery_app.conf.beat_schedule = {
    "dispatch-due-checks": {
        "task": "app.tasks.dispatch_due_checks",
        "schedule": 15.0,  # Fixed 15-second interval
    },
}
celery_app.conf.timezone = "UTC"