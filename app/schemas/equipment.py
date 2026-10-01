from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field
from app.schemas.common import ORM


class EquipmentCreate(BaseModel):
    tower_id: int
    name: str = Field(min_length=2, max_length=120, examples=["Antenna A1"])
    equipment_type: Literal["antenna", "router", "base_station", "power_unit", "battery", "other"]
    serial_number: str = Field(min_length=3, max_length=80, examples=["SN-100200"])


class EquipmentStatusUpdate(BaseModel):
    status: Literal["operational", "faulty", "maintenance", "decommissioned"]


class EquipmentResponse(ORM):
    id: int
    tower_id: int
    name: str
    equipment_type: str
    serial_number: str
    status: str
    installed_at: datetime


class MetricCreate(BaseModel):
    cpu_load: float = Field(ge=0, le=100, description="percent")
    temperature_c: float = Field(ge=-50, le=200)
    signal_strength_dbm: float | None = Field(default=None, ge=-150, le=0)


class MetricResponse(ORM):
    id: int
    equipment_id: int
    cpu_load: float
    temperature_c: float
    signal_strength_dbm: float | None
    recorded_at: datetime
