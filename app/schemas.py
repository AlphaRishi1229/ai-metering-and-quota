import datetime

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


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=32_000)


class UsageDetail(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    estimated_credits: int
    actual_credits: int


class GenerateResponse(BaseModel):
    text: str
    usage: UsageDetail


class UsageResponse(BaseModel):
    quota: int
    multiplier: float
    used: int
    reserved: int
    remaining: int

    model_config = {"from_attributes": True}


class UsageLogEntry(BaseModel):
    id: int
    prompt_tokens: int
    completion_tokens: int
    estimated_credits: int | None
    actual_credits: int | None
    status: str
    created_at: datetime.datetime

    model_config = {"from_attributes": True}
