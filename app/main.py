from fastapi import FastAPI, Request, Form, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session, selectinload, joinedload
from datetime import datetime, timezone, timedelta

from app.db.session import SessionLocal
from app.models.monitor import Monitor
from app.models.incident import Incident
from app.tasks import check_url

app = FastAPI(title="Uptime Monitor")
templates = Jinja2Templates(directory="app/templates")

# --- Custom IST Timezone Filter ---
def format_ist(dt):
    if not dt:
        return ""
    # Convert naive UTC from Postgres into aware UTC, then into IST (+5:30)
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    return dt.replace(tzinfo=timezone.utc).astimezone(ist_tz).strftime('%I:%M:%S %p')

templates.env.filters["ist"] = format_ist

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_dashboard_context(db: Session) -> dict:
    monitors = db.query(Monitor).options(
        selectinload(Monitor.results),
        selectinload(Monitor.incidents)
    ).order_by(Monitor.created_at.desc()).all()
    
    recent_incidents = (
        db.query(Incident)
        .filter(Incident.resolved_at.is_not(None))
        .options(joinedload(Incident.monitor))
        .order_by(Incident.resolved_at.desc())
        .limit(10)
        .all()
    )
    return {"monitors": monitors, "recent_incidents": recent_incidents}

# --- Core Endpoints ---

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
    request: Request, name: str = Form(...), url: str = Form(...), interval: int = Form(...), db: Session = Depends(get_db)
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

# --- New Edit Modal Endpoints ---

@app.get("/monitors/{monitor_id}/edit", response_class=HTMLResponse)
def edit_monitor_modal(monitor_id: int, request: Request, db: Session = Depends(get_db)):
    monitor = db.query(Monitor).filter(Monitor.id == monitor_id).first()
    return templates.TemplateResponse(request=request, name="_edit_modal.html", context={"monitor": monitor})

@app.post("/monitors/{monitor_id}/edit", response_class=HTMLResponse)
def update_monitor(
    monitor_id: int, request: Request, name: str = Form(...), url: str = Form(...), interval: int = Form(...), db: Session = Depends(get_db)
):
    monitor = db.query(Monitor).filter(Monitor.id == monitor_id).first()
    if monitor:
        monitor.name = name
        monitor.url = url
        monitor.check_interval_seconds = interval
        db.commit()
    context = get_dashboard_context(db)
    context["request"] = request
    return templates.TemplateResponse(request=request, name="_monitor_list.html", context=context)

# --- New UI Health Endpoint ---

@app.get("/worker-status")
def worker_status():
    return HTMLResponse("""Workers Active""")