from datetime import datetime
from sqlalchemy import String, Integer, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

class Monitor(Base):
    __tablename__ = "monitors"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    url: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String)
    check_interval_seconds: Mapped[int] = mapped_column(Integer, default=60)
    
    # Used by the dispatcher to know when this monitor is due
    next_check_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    results = relationship("CheckResult", back_populates="monitor", cascade="all, delete-orphan")
    incidents = relationship("Incident", back_populates="monitor", cascade="all, delete-orphan")