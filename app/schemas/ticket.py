from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field
from app.schemas.common import ORM

Priority = Literal["low", "medium", "high", "critical"]
TicketStatus = Literal["open", "assigned", "in_progress", "waiting_for_customer", "resolved", "closed"]


class TicketCreate(BaseModel):
    customer_id: int | None = Field(default=None, description="Staff must set this; customers leave it empty")
    subject: str = Field(min_length=3, max_length=200, examples=["No network since morning"])
    description: str = Field(min_length=5, examples=["Signal drops every few minutes in my area."])
    category: Literal["network", "billing", "sim", "device", "plan", "other"] = "other"
    priority: Priority = "medium"


class TicketStatusUpdate(BaseModel):
    status: TicketStatus
    note: str | None = Field(default=None, max_length=255)


class CommentCreate(BaseModel):
    comment: str = Field(min_length=1)
    is_internal: bool = Field(default=False, description="Internal notes are hidden from the customer (staff only)")


class TicketResponse(ORM):
    id: int
    ticket_number: str
    customer_id: int
    subject: str
    description: str
    category: str
    priority: str
    status: str
    assigned_to: int | None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None


class CommentResponse(ORM):
    id: int
    ticket_id: int
    author_id: int
    comment: str
    is_internal: bool
    created_at: datetime


class TicketHistoryResponse(ORM):
    id: int
    ticket_id: int
    old_status: str | None
    new_status: str
    changed_by: int
    note: str | None
    changed_at: datetime


class AssignRequest(BaseModel):
    ticket_id: int
    assignee_id: int = Field(description="user id of a staff member")


class AssignmentResponse(ORM):
    id: int
    ticket_id: int
    assignee_id: int
    assigned_by: int
    assigned_at: datetime
