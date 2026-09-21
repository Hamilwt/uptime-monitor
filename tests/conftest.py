import pytest
from app.celery_app import celery_app

@pytest.fixture(autouse=True)
def celery_eager():
    """
    Forces Celery to execute tasks synchronously during tests.
    This means calling .delay() runs the function immediately, 
    so we don't need a real Redis broker or Worker running to test our logic!
    """
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    yield