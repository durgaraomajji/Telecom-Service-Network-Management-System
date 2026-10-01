from datetime import datetime
from pydantic import BaseModel, Field
from app.schemas.common import ORM


class SubscriptionCreate(BaseModel):
    customer_id: int | None = Field(default=None, description="Staff must set this; customers leave it empty")
    plan_id: int
    sim_id: int
    auto_renew: bool = False


class PlanChange(BaseModel):
    plan_id: int


class SubscriptionNote(BaseModel):
    note: str | None = Field(default=None, max_length=255)


class SubscriptionResponse(ORM):
    id: int
    customer_id: int
    plan_id: int
    sim_id: int
    status: str
    start_date: datetime
    end_date: datetime
    auto_renew: bool
    created_at: datetime


class SubscriptionHistoryResponse(ORM):
    id: int
    subscription_id: int
    action: str
    old_plan_id: int | None
    new_plan_id: int | None
    note: str | None
    performed_by: int | None
    created_at: datetime
