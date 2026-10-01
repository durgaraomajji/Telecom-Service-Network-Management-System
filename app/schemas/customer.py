from pydantic import BaseModel, EmailStr, Field

class CustomerCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    email: EmailStr
    password: str = Field(min_length=8)
    phone: str = Field(min_length=7, max_length=30)

class CustomerResponse(BaseModel):
    id: int
    user_id: int
    customer_number: str
    phone: str
    kyc_status: str
    model_config = {"from_attributes": True}


class CustomerProfileCreate(BaseModel):
    phone: str = Field(min_length=7, max_length=30, examples=["9876543210"])


class CustomerUpdate(BaseModel):
    phone: str | None = Field(default=None, min_length=7, max_length=30)
