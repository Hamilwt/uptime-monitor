from fastapi import FastAPI, Request, Form, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session, selectinload, joinedload
from datetime import datetime

from app.db.session import SessionLocal
from app.models.monitor import Monitor
from app.models.incident import Incident
from app.tasks import check_url

app = FastAPI(title="Uptime Monitor")
templates = Jinja2Templates(directory="app/templates")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_dashboard_context(db: Session) -> dict:
    """
    Helper to fetch all required dashboard data efficiently.
    selectinload() solves N+1 for monitor child collections (results/incidents).
    joinedload() executes a single SQL JOIN to eager-load the parent monitor on recent incidents.
    """
    monitors = db.query(Monitor).options(
        selectinload(Monitor.results),
        selectinload(Monitor.incidents)
    ).order_by(Monitor.created_at.desc()).all()
    
    # Eagerly load the parent monitor via JOIN to eliminate N+1 queries during rendering
    recent_incidents = (
        db.query(Incident)
        .filter(Incident.resolved_at.is_not(None))
        .options(joinedload(Incident.monitor))
        .order_by(Incident.resolved_at.desc())
        .limit(10)
        .all()
    )
    
    return {"monitors": monitors, "recent_incidents": recent_incidents}


@app.get("/health")
def health_check():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    context = get_dashboard_context(db)
    context["request"] = request
    return templates.TemplateResponse(request=request, name="index.html", context=context)

@app.get("/monitors/fragment", response_class=HTMLResponse)
def monitor_list_fragment(request: Request, db: Session = Depends(get_db)):
    context = get_dashboard_context(db)
    context["request"] = request
    return templates.TemplateResponse(request=request, name="_monitor_list.html", context=context)

@app.post("/monitors")
def add_monitor(
    request: Request,
    name: str = Form(...),
    url: str = Form(...),
    interval: int = Form(...),
    db: Session = Depends(get_db)
):
    monitor = Monitor(name=name, url=url, check_interval_seconds=interval)
    db.add(monitor)
    db.commit()
    
    context = get_dashboard_context(db)
    context["request"] = request
    return templates.TemplateResponse(request=request, name="_monitor_list.html", context=context)

@app.post("/monitors/{monitor_id}/check-now")
def force_check(monitor_id: int, request: Request, db: Session = Depends(get_db)):
    check_url.delay(monitor_id)
    context = get_dashboard_context(db)
    context["request"] = request
    return templates.TemplateResponse(request=request, name="_monitor_list.html", context=context)

@app.post("/monitors/{monitor_id}/pause")
def toggle_pause(monitor_id: int, request: Request, db: Session = Depends(get_db)):
    monitor = db.query(Monitor).filter(Monitor.id == monitor_id).first()
    if monitor:
        monitor.is_active = not monitor.is_active
        db.commit()
        
    context = get_dashboard_context(db)
    context["request"] = request
    return templates.TemplateResponse(request=request, name="_monitor_list.html", context=context)

@app.delete("/monitors/{monitor_id}")
def delete_monitor(monitor_id: int, request: Request, db: Session = Depends(get_db)):
    monitor = db.query(Monitor).filter(Monitor.id == monitor_id).first()
    if monitor:
        db.delete(monitor)
        db.commit()
        
    context = get_dashboard_context(db)
    context["request"] = request
    return templates.TemplateResponse(request=request, name="_monitor_list.html", context=context)