from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field
from app.schemas.common import ORM

RequestType = Literal["new_connection", "plan_change", "sim_replacement", "disconnection", "address_change", "other"]


class ServiceRequestCreate(BaseModel):
    customer_id: int | None = Field(default=None, description="Staff must set this; customers leave it empty")
    request_type: RequestType
    description: str | None = None
    subscription_id: int | None = None
    target_plan_id: int | None = Field(default=None, description="Needed for plan_change")


class ServiceRequestStatusUpdate(BaseModel):
    status: Literal["under_review", "approved", "rejected", "completed"]
    note: str | None = Field(default=None, max_length=255)


class ServiceRequestResponse(ORM):
    id: int
    request_number: str
    customer_id: int
    request_type: str
    description: str | None
    subscription_id: int | None
    target_plan_id: int | None
    status: str
    created_at: datetime
    updated_at: datetime


class ServiceRequestHistoryResponse(ORM):
    id: int
    request_id: int
    old_status: str | None
    new_status: str
    changed_by: int
    note: str | None
    changed_at: datetime
