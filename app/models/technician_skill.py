from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.timeutil import utcnow
from app.db.base import Base

class TechnicianSkill(Base):
    __tablename__ = "technician_skills"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    technician_id: Mapped[int] = mapped_column(ForeignKey("technicians.id"), index=True, nullable=False)
    skill: Mapped[str] = mapped_column(String(60), nullable=False)
