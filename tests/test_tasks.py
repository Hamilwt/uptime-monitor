import pytest
from unittest.mock import patch
import httpx
from datetime import datetime, timedelta

from app.models.monitor import Monitor
from app.models.check_result import CheckResult
from app.models.incident import Incident
from app.tasks import check_url, dispatch_due_checks
from app.db.session import SessionLocal

@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        # Clean up tables before each test to ensure isolation
        db.query(CheckResult).delete()
        db.query(Incident).delete()
        db.query(Monitor).delete()
        db.commit()
        yield db
    finally:
        db.close()

def test_check_url_success_creates_result_and_updates_next_check(db_session):
    monitor = Monitor(name="Test", url="https://test.com", check_interval_seconds=60)
    db_session.add(monitor)
    db_session.commit()
    
    original_next_check = monitor.next_check_at

    with patch("httpx.Client.get") as mock_get:
        mock_get.return_value.status_code = 200
        check_url.delay(monitor.id)

    db_session.refresh(monitor)
    results = db_session.query(CheckResult).filter_by(monitor_id=monitor.id).all()
    
    assert len(results) == 1
    assert results[0].is_up is True
    assert results[0].status_code == 200
    assert monitor.next_check_at > original_next_check

def test_check_url_failure_opens_incident(db_session):
    monitor = Monitor(name="Fail Test", url="https://fail.com")
    db_session.add(monitor)
    db_session.commit()

    with patch("httpx.Client.get", side_effect=httpx.RequestError("DNS Failed")):
        check_url.delay(monitor.id)

    results = db_session.query(CheckResult).filter_by(monitor_id=monitor.id).all()
    assert len(results) == 1
    assert results[0].is_up is False
    assert results[0].error_message == "DNS Failed"

    incidents = db_session.query(Incident).filter_by(monitor_id=monitor.id).all()
    assert len(incidents) == 1
    assert incidents[0].resolved_at is None

def test_consecutive_failures_do_not_duplicate_incidents(db_session):
    monitor = Monitor(name="Fail Test", url="https://fail.com")
    db_session.add(monitor)
    db_session.commit()

    # Two consecutive failures
    with patch("httpx.Client.get", side_effect=httpx.RequestError("DNS Failed")):
        check_url.delay(monitor.id)
        check_url.delay(monitor.id)

    incidents = db_session.query(Incident).filter_by(monitor_id=monitor.id).all()
    # It should still be exactly ONE open incident row, not two
    assert len(incidents) == 1
    assert incidents[0].resolved_at is None

def test_incident_resolves_on_recovery(db_session):
    monitor = Monitor(name="Recovery Test", url="https://recover.com")
    db_session.add(monitor)
    db_session.commit()

    # 1. Goes Down
    with patch("httpx.Client.get", side_effect=httpx.RequestError("Down")):
        check_url.delay(monitor.id)
    
    # 2. Comes back Up
    with patch("httpx.Client.get") as mock_get:
        mock_get.return_value.status_code = 200
        check_url.delay(monitor.id)

    incidents = db_session.query(Incident).filter_by(monitor_id=monitor.id).all()
    assert len(incidents) == 1
    # The existing incident should now have a resolved_at timestamp
    assert incidents[0].resolved_at is not None

def test_dispatcher_ignores_inactive_and_future_monitors(db_session):
    # Active, but due in the future
    future_monitor = Monitor(name="Future", url="http://a.com", next_check_at=datetime.utcnow() + timedelta(minutes=10))
    # Due now, but paused
    paused_monitor = Monitor(name="Paused", url="http://b.com", next_check_at=datetime.utcnow() - timedelta(minutes=10), is_active=False)
    # Active and due now
    due_monitor = Monitor(name="Due", url="http://c.com", next_check_at=datetime.utcnow() - timedelta(minutes=10))
    
    db_session.add_all([future_monitor, paused_monitor, due_monitor])
    db_session.commit()

    # Dispatcher should only trigger the 'Due' monitor
    with patch("app.tasks.check_url.delay") as mock_delay:
        dispatch_due_checks()
        
        # It should have been called exactly once, for the due_monitor
        assert mock_delay.call_count == 1
        mock_delay.assert_called_with(due_monitor.id)