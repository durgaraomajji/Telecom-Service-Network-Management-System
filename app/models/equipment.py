from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.timeutil import utcnow
from app.db.base import Base

class Equipment(Base):
    __tablename__ = "equipment"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tower_id: Mapped[int] = mapped_column(ForeignKey("towers.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    equipment_type: Mapped[str] = mapped_column(String(40), nullable=False)
    serial_number: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="operational", index=True, nullable=False)
    installed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
