from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    quota: int = Field(gt=0)
    multiplier: float = Field(gt=0.0)


class UserUpdate(BaseModel):
    quota: int | None = Field(default=None, gt=0)
    multiplier: float | None = Field(default=None, gt=0.0)


class UserResponse(BaseModel):
    id: int
    quota: int
    multiplier: float
    used_credits: int
    reserved_credits: int

    model_config = {"from_attributes": True}
