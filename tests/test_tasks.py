import pytest
from unittest.mock import patch
import httpx
from datetime import datetime, timedelta

from app.models.monitor import Monitor
from app.models.check_result import CheckResult
from app.models.incident import Incident
from app.tasks import check_url
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
    # 1. Setup: Create a monitor
    monitor = Monitor(name="Test", url="https://test.com", check_interval_seconds=60)
    db_session.add(monitor)
    db_session.commit()
    
    original_next_check = monitor.next_check_at

    # 2. Mock a successful HTTP response
    with patch("httpx.Client.get") as mock_get:
        mock_get.return_value.status_code = 200
        
        # 3. Execute: Because of our conftest.py, .delay() runs synchronously!
        check_url.delay(monitor.id)

    # 4. Assertions
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

    # Mock an HTTPX network failure
    with patch("httpx.Client.get", side_effect=httpx.RequestError("DNS Failed")):
        check_url.delay(monitor.id)

    # Verify a check result was saved showing DOWN
    results = db_session.query(CheckResult).filter_by(monitor_id=monitor.id).all()
    assert len(results) == 1
    assert results[0].is_up is False
    assert results[0].error_message == "DNS Failed"

    # Verify a NEW incident was opened (resolved_at is None)
    incidents = db_session.query(Incident).filter_by(monitor_id=monitor.id).all()
    assert len(incidents) == 1
    assert incidents[0].resolved_at is None