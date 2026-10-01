from pydantic import BaseModel


class ORM(BaseModel):
    model_config = {"from_attributes": True}


class Message(BaseModel):
    detail: str
