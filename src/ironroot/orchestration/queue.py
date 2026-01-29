# Author: Bradley R. Kinnard
"""celery task queue for background orchestration."""

from celery import Celery

from ironroot.settings import get_settings

settings = get_settings()

celery_app = Celery(
    "ironroot",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,
    worker_prefetch_multiplier=1,
)


@celery_app.task(bind=True, name="ironroot.run.execute")  # type: ignore[untyped-decorator]
def execute_run(self: object, run_id: str) -> dict[str, str]:
    """background task to execute a run through all phases."""
    # todo: implement full orchestration in phase 3
    return {"run_id": run_id, "status": "completed"}
