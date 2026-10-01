from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field
from app.schemas.common import ORM


class AddressCreate(BaseModel):
    customer_id: int | None = Field(default=None, description="Staff must set this; customers leave it empty")
    address_type: Literal["service", "billing"] = "service"
    line1: str = Field(min_length=3, max_length=255, examples=["12 MG Road"])
    line2: str | None = Field(default=None, max_length=255)
    city: str = Field(min_length=2, max_length=100, examples=["Bengaluru"])
    state: str = Field(min_length=2, max_length=100, examples=["Karnataka"])
    postal_code: str = Field(min_length=3, max_length=20, examples=["560001"])
    country: str = Field(default="India", max_length=60)
    is_primary: bool = False


class AddressUpdate(BaseModel):
    address_type: Literal["service", "billing"] | None = None
    line1: str | None = Field(default=None, min_length=3, max_length=255)
    line2: str | None = None
    city: str | None = Field(default=None, min_length=2, max_length=100)
    state: str | None = Field(default=None, min_length=2, max_length=100)
    postal_code: str | None = Field(default=None, min_length=3, max_length=20)
    country: str | None = None
    is_primary: bool | None = None


class AddressResponse(ORM):
    id: int
    customer_id: int
    address_type: str
    line1: str
    line2: str | None
    city: str
    state: str
    postal_code: str
    country: str
    is_primary: bool
    created_at: datetime
