from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field
from app.schemas.common import ORM


class UsageCreate(BaseModel):
    subscription_id: int
    usage_type: Literal["data", "voice", "sms"]
    quantity: int = Field(gt=0, description="data: MB, voice: minutes, sms: messages", examples=[150])


class UsageResponse(ORM):
    id: int
    subscription_id: int
    usage_type: str
    quantity: int
    recorded_at: datetime


class UsageLine(BaseModel):
    used: int
    limit: int
    remaining: int
    exceeded: bool


class UsageSummary(BaseModel):
    subscription_id: int
    plan_id: int
    period_start: datetime
    period_end: datetime
    data_mb: UsageLine
    voice_minutes: UsageLine
    sms: UsageLine
