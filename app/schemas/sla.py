from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field
from app.schemas.common import ORM


class SlaRuleCreate(BaseModel):
    priority: Literal["low", "medium", "high", "critical"]
    response_minutes: int = Field(gt=0, examples=[60])
    resolution_minutes: int = Field(gt=0, examples=[480])


class SlaRuleUpdate(BaseModel):
    response_minutes: int = Field(gt=0)
    resolution_minutes: int = Field(gt=0)


class SlaRuleResponse(BaseModel):
    priority: str
    response_minutes: int
    resolution_minutes: int
    is_default: bool = False


class SlaTrackingResponse(ORM):
    ticket_id: int
    ticket_number: str | None = None
    priority: str | None = None
    ticket_status: str | None = None
    response_due: datetime
    resolution_due: datetime
    responded_at: datetime | None
    resolved_at: datetime | None
    response_breached: bool
    resolution_breached: bool
