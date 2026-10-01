from datetime import datetime
from pydantic import BaseModel, Field
from app.schemas.common import ORM


class DeviceCreate(BaseModel):
    imei: str = Field(pattern=r"^\d{15}$", examples=["356938035643809"], description="15 digits")
    brand: str = Field(min_length=2, max_length=80, examples=["Samsung"])
    model: str = Field(min_length=1, max_length=80, examples=["Galaxy S23"])
    device_type: str = Field(default="smartphone", max_length=30)


class DeviceAssign(BaseModel):
    sim_id: int


class DeviceBlock(BaseModel):
    is_blocked: bool = True


class DeviceResponse(ORM):
    id: int
    imei: str
    brand: str
    model: str
    device_type: str
    is_blocked: bool
    created_at: datetime


class DeviceAssignmentResponse(ORM):
    id: int
    device_id: int
    sim_id: int
    customer_id: int | None
    assigned_at: datetime
    released_at: datetime | None
