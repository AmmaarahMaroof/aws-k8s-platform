"""Request and response shapes (Pydantic).

FastAPI uses these to validate incoming JSON and to build the /docs page.
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class SiteCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100, examples=["GitHub"])
    url: HttpUrl = Field(examples=["https://github.com"])


class SiteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    url: str
    created_at: datetime


class CheckOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    site_id: int
    checked_at: datetime
    is_up: bool
    status_code: int | None
    response_ms: int | None
    error: str | None


class SiteStatus(BaseModel):
    """A site plus its most recent check (None if never checked)."""

    id: int
    name: str
    url: str
    is_up: bool | None
    status_code: int | None
    response_ms: int | None
    last_checked: datetime | None


class RunResult(BaseModel):
    checked: int
    up: int
    down: int
