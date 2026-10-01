from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field
from app.schemas.common import ORM


class NotificationCreate(BaseModel):
    user_id: int
    title: str = Field(min_length=2, max_length=150)
    message: str = Field(min_length=1)
    type: str = Field(default="info", max_length=30)


class BroadcastCreate(BaseModel):
    role: Literal["customer", "super_admin", "operations_manager", "support_agent",
                  "network_engineer", "field_technician"] = "customer"
    title: str = Field(min_length=2, max_length=150)
    message: str = Field(min_length=1)


class NotificationResponse(ORM):
    id: int
    user_id: int
    title: str
    message: str
    type: str
    is_read: bool
    created_at: datetime
