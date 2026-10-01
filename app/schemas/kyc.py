from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field
from app.schemas.common import ORM


class KycCreate(BaseModel):
    document_type: Literal["aadhaar", "passport", "driving_license", "voter_id", "pan"]
    document_number: str = Field(min_length=4, max_length=60, examples=["ABCDE1234F"])


class KycVerify(BaseModel):
    status: Literal["verified", "rejected"]
    remarks: str | None = Field(default=None, max_length=255)


class KycResponse(ORM):
    id: int
    customer_id: int
    document_type: str
    document_number: str
    status: str
    remarks: str | None
    verified_by: int | None
    verified_at: datetime | None
    created_at: datetime
