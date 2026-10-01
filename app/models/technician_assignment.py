from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.timeutil import utcnow
from app.db.base import Base

class TechnicianAssignment(Base):
    __tablename__ = "technician_assignments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    technician_id: Mapped[int] = mapped_column(ForeignKey("technicians.id"), index=True, nullable=False)
    task: Mapped[str] = mapped_column(String(255), nullable=False)
    outage_id: Mapped[int | None] = mapped_column(ForeignKey("outages.id"), nullable=True)
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("support_tickets.id"), nullable=True)
    equipment_id: Mapped[int | None] = mapped_column(ForeignKey("equipment.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="assigned", nullable=False)
    assigned_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
