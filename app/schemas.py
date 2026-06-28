import datetime

from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    """Payload for creating a new user with a quota and per-token multiplier."""

    quota: int = Field(gt=0)
    multiplier: float = Field(gt=0.0)


class UserUpdate(BaseModel):
    """Partial update payload; omitted fields are left unchanged."""

    quota: int | None = Field(default=None, gt=0)
    multiplier: float | None = Field(default=None, gt=0.0)


class UserResponse(BaseModel):
    """API response representing a user's current quota configuration."""

    id: int
    quota: int
    multiplier: float
    used_credits: int
    reserved_credits: int

    model_config = {"from_attributes": True}


class GenerateRequest(BaseModel):
    """Request body for a text generation call."""

    prompt: str = Field(min_length=1, max_length=32_000)


class UsageDetail(BaseModel):
    """Token counts and credit amounts for a single completed generation."""

    prompt_tokens: int
    completion_tokens: int
    estimated_credits: int
    actual_credits: int


class GenerateResponse(BaseModel):
    """Response returned after a successful text generation."""

    text: str
    usage: UsageDetail


class UsageResponse(BaseModel):
    """Summary of a user's credit quota state at a point in time."""

    quota: int
    multiplier: float
    used: int
    reserved: int
    remaining: int

    model_config = {"from_attributes": True}


class UsageLogEntry(BaseModel):
    """A single row from the usage log, returned by the history endpoint."""

    id: int
    prompt_tokens: int
    completion_tokens: int
    estimated_credits: int | None
    actual_credits: int | None
    status: str
    created_at: datetime.datetime

    model_config = {"from_attributes": True}
