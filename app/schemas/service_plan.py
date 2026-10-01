from pydantic import BaseModel, Field

class PlanCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    plan_type: str
    price: float = Field(ge=0)
    validity_days: int = Field(gt=0)
    data_limit_mb: int = Field(default=0, ge=0)
    voice_minutes: int = Field(default=0, ge=0)
    sms_limit: int = Field(default=0, ge=0)

class PlanResponse(PlanCreate):
    id: int
    is_active: bool
    model_config = {"from_attributes": True}


class PlanUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    plan_type: str | None = None
    price: float | None = Field(default=None, ge=0)
    validity_days: int | None = Field(default=None, gt=0)
    data_limit_mb: int | None = Field(default=None, ge=0)
    voice_minutes: int | None = Field(default=None, ge=0)
    sms_limit: int | None = Field(default=None, ge=0)
    is_active: bool | None = None
