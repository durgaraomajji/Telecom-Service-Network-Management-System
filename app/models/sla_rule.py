from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.timeutil import utcnow
from app.db.base import Base

class SlaRule(Base):
    __tablename__ = "sla_rules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    priority: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    response_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    resolution_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
