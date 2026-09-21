from datetime import datetime
from sqlalchemy import ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    monitor_id: Mapped[int] = mapped_column(ForeignKey("monitors.id"))
    
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # A null resolved_at is our source of truth that an incident is currently ongoing
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    monitor = relationship("Monitor", back_populates="incidents")