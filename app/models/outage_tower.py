from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.timeutil import utcnow
from app.db.base import Base

class OutageTower(Base):
    __tablename__ = "outage_towers"
    outage_id: Mapped[int] = mapped_column(ForeignKey("outages.id"), primary_key=True)
    tower_id: Mapped[int] = mapped_column(ForeignKey("towers.id"), primary_key=True)
