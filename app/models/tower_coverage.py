from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.timeutil import utcnow
from app.db.base import Base

class TowerCoverage(Base):
    __tablename__ = "tower_coverages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tower_id: Mapped[int] = mapped_column(ForeignKey("towers.id"), index=True, nullable=False)
    area_name: Mapped[str] = mapped_column(String(120), nullable=False)
    radius_km: Mapped[float] = mapped_column(Float, nullable=False)
    technology: Mapped[str] = mapped_column(String(10), nullable=False)
