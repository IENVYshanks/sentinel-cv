from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class AlertResponse(BaseModel):
    id: int
    camera_id: str
    rule_id: str
    rule_name: str
    rule_type: str
    message: str
    occurred_at: datetime
    track_id: int | None
    confidence: float | None
    evidence_file: str | None
    metadata: dict[str, Any]


class CameraResponse(BaseModel):
    id: str
    name: str
    running: bool
    connected: bool
    last_error: str | None
    frames_processed: int


class IdentityUpsertRequest(BaseModel):
    identity_id: str = Field(
        min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$"
    )
    display_name: str = Field(min_length=1, max_length=100)
    image_base64: str = Field(min_length=1, max_length=14_000_000)

    @field_validator("display_name")
    @classmethod
    def clean_display_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Display name must not be empty")
        return cleaned


class IdentityRenameRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)

    @field_validator("display_name")
    @classmethod
    def clean_display_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Display name must not be empty")
        return cleaned


class IdentitySampleRequest(BaseModel):
    image_base64: str = Field(min_length=1, max_length=14_000_000)

