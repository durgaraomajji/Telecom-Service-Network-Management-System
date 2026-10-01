from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.timeutil import utcnow
from app.db.base import Base

class SimReplacement(Base):
    __tablename__ = "sim_replacements"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    old_sim_id: Mapped[int] = mapped_column(ForeignKey("sim_cards.id"), index=True, nullable=False)
    new_sim_id: Mapped[int] = mapped_column(ForeignKey("sim_cards.id"), index=True, nullable=False)
    reason: Mapped[str] = mapped_column(String(20), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    replaced_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
