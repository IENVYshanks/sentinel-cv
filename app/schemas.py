from datetime import datetime
from typing import Any

from pydantic import BaseModel


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

