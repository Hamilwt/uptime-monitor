from fastapi import FastAPI, Request, Form, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from datetime import datetime

from app.db.session import SessionLocal
from app.models.monitor import Monitor
from app.tasks import check_url

app = FastAPI(title="Uptime Monitor")
templates = Jinja2Templates(directory="app/templates")

# Dependency to get DB session per request
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    """Renders the full initial page skeleton."""
    monitors = db.query(Monitor).order_by(Monitor.created_at.desc()).all()
    return templates.TemplateResponse(
        request=request, 
        name="index.html", 
        context={"monitors": monitors}
    )

@app.get("/monitors/fragment", response_class=HTMLResponse)
def monitor_list_fragment(request: Request, db: Session = Depends(get_db)):
    """HTMX polling endpoint. Returns only the table rows, no HTML head/body."""
    monitors = db.query(Monitor).order_by(Monitor.created_at.desc()).all()
    return templates.TemplateResponse(
        request=request, 
        name="_monitor_list.html", 
        context={"monitors": monitors}
    )

@app.post("/monitors")
def add_monitor(
    request: Request,
    name: str = Form(...),
    url: str = Form(...),
    interval: int = Form(...),
    db: Session = Depends(get_db)
):
    """Creates a new monitor and returns the updated HTMX fragment."""
    monitor = Monitor(name=name, url=url, check_interval_seconds=interval)
    db.add(monitor)
    db.commit()
    
    monitors = db.query(Monitor).order_by(Monitor.created_at.desc()).all()
    return templates.TemplateResponse(
        request=request, 
        name="_monitor_list.html", 
        context={"monitors": monitors}
    )

@app.post("/monitors/{monitor_id}/check-now")
def force_check(monitor_id: int, request: Request, db: Session = Depends(get_db)):
    """
    Demonstrates the Celery offload. 
    We fire the task to the queue and instantly return the UI fragment.
    We do NOT wait for the HTTP request to finish.
    """
    check_url.delay(monitor_id)
    
    monitors = db.query(Monitor).order_by(Monitor.created_at.desc()).all()
    return templates.TemplateResponse(
        request=request, 
        name="_monitor_list.html", 
        context={"monitors": monitors}
    )