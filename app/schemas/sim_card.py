from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field
from app.schemas.common import ORM

SimStatus = Literal["available", "active", "suspended", "lost", "blocked", "deactivated"]


class SimCreate(BaseModel):
    iccid: str = Field(pattern=r"^\d{19,20}$", examples=["8991101200003204510"], description="19-20 digits")
    msisdn: str = Field(pattern=r"^\+?\d{10,13}$", examples=["9876500001"], description="Phone number")


class SimStatusUpdate(BaseModel):
    status: SimStatus
    reason: str | None = Field(default=None, max_length=255)


class SimReplaceRequest(BaseModel):
    new_iccid: str = Field(pattern=r"^\d{19,20}$", examples=["8991101200003204999"])
    reason: Literal["lost", "damaged", "upgrade", "other"] = "damaged"
    notes: str | None = Field(default=None, max_length=255)


class SimResponse(ORM):
    id: int
    iccid: str
    msisdn: str | None
    status: str
    customer_id: int | None
    activated_at: datetime | None
    created_at: datetime


class SimReplacementResponse(ORM):
    id: int
    old_sim_id: int
    new_sim_id: int
    reason: str
    notes: str | None
    replaced_by: int
    created_at: datetime
