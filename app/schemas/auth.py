from typing import Literal
from pydantic import BaseModel, EmailStr, Field

RoleName = Literal["customer", "super_admin", "operations_manager", "support_agent",
                  "network_engineer", "field_technician"]

class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=150, examples=["Jane Doe"])
    email: EmailStr = Field(examples=["jane@example.com"])
    password: str = Field(min_length=8, max_length=128, examples=["Password123"])
    role: RoleName = Field(
        default="customer", examples=["customer"],
        description="customer (public) | super_admin | operations_manager | support_agent | network_engineer | field_technician. "
                    "Staff roles need a super_admin token, except the very first account on an empty system.")

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class UserResponse(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    role: str
    is_active: bool
    model_config = {"from_attributes": True}
