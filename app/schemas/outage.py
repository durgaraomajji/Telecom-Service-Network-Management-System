from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field
from app.schemas.common import ORM


class OutageCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200, examples=["Power failure at BLR-Central-01"])
    description: str | None = None
    severity: Literal["low", "medium", "high", "critical"]
    tower_ids: list[int] = Field(min_length=1, examples=[[1]])


class OutageStatusUpdate(BaseModel):
    status: Literal["investigating", "resolved"]
    note: str | None = Field(default=None, max_length=255)


class OutageResponse(ORM):
    id: int
    title: str
    description: str | None
    severity: str
    status: str
    started_at: datetime
    resolved_at: datetime | None
    created_by: int
    tower_ids: list[int] = []
    affected_customers: int = 0
