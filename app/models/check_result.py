from datetime import datetime
from sqlalchemy import ForeignKey, Boolean, Integer, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

class CheckResult(Base):
    __tablename__ = "check_results"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    monitor_id: Mapped[int] = mapped_column(ForeignKey("monitors.id"))
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    is_up: Mapped[bool] = mapped_column(Boolean)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)

    monitor = relationship("Monitor", back_populates="results")