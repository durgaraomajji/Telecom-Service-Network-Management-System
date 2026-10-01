from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field
from app.schemas.common import ORM


class TechnicianCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150, examples=["Ravi Kumar"])
    phone: str = Field(min_length=7, max_length=30, examples=["9123456780"])
    region: str = Field(min_length=2, max_length=100, examples=["Bengaluru"])
    user_id: int | None = Field(default=None, description="Link to a field_technician login")
    skills: list[str] = []


class TechnicianAvailability(BaseModel):
    is_available: bool


class SkillCreate(BaseModel):
    skill: str = Field(min_length=2, max_length=60, examples=["fiber_splicing"])


class TechnicianResponse(ORM):
    id: int
    user_id: int | None
    name: str
    phone: str
    region: str
    is_available: bool
    skills: list[str] = []


class WorkAssignCreate(BaseModel):
    task: str = Field(min_length=3, max_length=255, examples=["Replace failed power unit"])
    outage_id: int | None = None
    ticket_id: int | None = None
    equipment_id: int | None = None


class WorkStatusUpdate(BaseModel):
    status: Literal["in_progress", "completed", "cancelled"]


class WorkAssignmentResponse(ORM):
    id: int
    technician_id: int
    task: str
    outage_id: int | None
    ticket_id: int | None
    equipment_id: int | None
    status: str
    assigned_by: int
    assigned_at: datetime
    completed_at: datetime | None
