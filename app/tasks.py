import time
from datetime import datetime, timedelta
import httpx

from app.celery_app import celery_app
from app.db.session import SessionLocal
from app.models.monitor import Monitor
from app.models.check_result import CheckResult
from app.models.incident import Incident

@celery_app.task(bind=True, max_retries=2, default_retry_delay=5)
def check_url(self, monitor_id: int):
    db = SessionLocal()
    try:
        monitor = db.query(Monitor).filter(Monitor.id == monitor_id).first()
        if not monitor:
            return

        start = time.monotonic()
        try:
            # Synchronous httpx client because Celery threads handle the concurrency
            with httpx.Client(timeout=10.0, follow_redirects=True) as client:
                response = client.get(monitor.url)
            
            elapsed_ms = int((time.monotonic() - start) * 1000)
            result = CheckResult(
                monitor_id=monitor.id,
                is_up=response.status_code < 400,
                status_code=response.status_code,
                response_time_ms=elapsed_ms,
            )
        except httpx.RequestError as e:
            # Network failures (timeouts, DNS errors) are valid results, not task crashes
            result = CheckResult(
                monitor_id=monitor.id,
                is_up=False,
                status_code=None,
                response_time_ms=None,
                error_message=str(e),
            )

        db.add(result)

        # --- Incident Detection ---
        # Look for a currently ongoing incident (resolved_at is NULL)
        open_incident = db.query(Incident).filter(
            Incident.monitor_id == monitor.id,
            Incident.resolved_at.is_(None),
        ).first()

        if not result.is_up and open_incident is None:
            # Transition: Up -> Down (Open new incident)
            db.add(Incident(monitor_id=monitor.id, started_at=datetime.utcnow()))
        elif result.is_up and open_incident is not None:
            # Transition: Down -> Up (Resolve existing incident)
            open_incident.resolved_at = datetime.utcnow()

        # Self-perpetuating schedule: calculate the next due date based on the interval
        monitor.next_check_at = datetime.utcnow() + timedelta(seconds=monitor.check_interval_seconds)
        db.commit()
    finally:
        db.close()


@celery_app.task
def dispatch_due_checks():
    db = SessionLocal()
    try:
        due = db.query(Monitor).filter(
            Monitor.is_active == True,
            Monitor.next_check_at <= datetime.utcnow(),
        ).all()
        
        for monitor in due:
            check_url.delay(monitor.id)
    finally:
        db.close()