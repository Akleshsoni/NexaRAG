from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "documind",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_acks_late=True,  # don't lose a job if the worker crashes mid-processing
    worker_prefetch_multiplier=1,  # avoid one worker hoarding all queued documents
    task_routes={"app.workers.tasks.process_document": {"queue": "ingestion"}},
)
