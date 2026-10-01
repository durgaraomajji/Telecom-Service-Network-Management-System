from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field
from app.schemas.common import ORM

TowerStatus = Literal["active", "degraded", "down", "maintenance"]


class TowerCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120, examples=["BLR-Central-01"])
    city: str = Field(min_length=2, max_length=100, examples=["Bengaluru"])
    latitude: float = Field(ge=-90, le=90, examples=[12.9716])
    longitude: float = Field(ge=-180, le=180, examples=[77.5946])
    capacity_users: int = Field(default=0, ge=0)


class TowerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    city: str | None = Field(default=None, min_length=2, max_length=100)
    status: TowerStatus | None = None
    capacity_users: int | None = Field(default=None, ge=0)


class TowerResponse(ORM):
    id: int
    name: str
    city: str
    latitude: float
    longitude: float
    status: str
    capacity_users: int
    created_at: datetime


class CoverageCreate(BaseModel):
    area_name: str = Field(min_length=2, max_length=120, examples=["MG Road"])
    radius_km: float = Field(gt=0, le=100)
    technology: Literal["2G", "3G", "4G", "5G"]


class CoverageResponse(ORM):
    id: int
    tower_id: int
    area_name: str
    radius_km: float
    technology: str
