from sqlalchemy import Boolean, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class ServicePlan(Base):
    __tablename__ = "service_plans"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    plan_type: Mapped[str] = mapped_column(String(30), nullable=False)
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    validity_days: Mapped[int] = mapped_column(Integer, nullable=False)
    data_limit_mb: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    voice_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sms_limit: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
