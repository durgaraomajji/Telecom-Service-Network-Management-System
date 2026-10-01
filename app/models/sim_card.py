from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.timeutil import utcnow
from app.db.base import Base

class SimCard(Base):
    __tablename__ = "sim_cards"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    iccid: Mapped[str] = mapped_column(String(22), unique=True, index=True, nullable=False)
    msisdn: Mapped[str | None] = mapped_column(String(16), unique=True, index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="available", index=True, nullable=False)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), index=True, nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
