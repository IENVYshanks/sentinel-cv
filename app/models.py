from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class Detection:
    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float

    @property
    def centroid(self) -> tuple[int, int]:
        return ((self.x1 + self.x2) // 2, (self.y1 + self.y2) // 2)


@dataclass(slots=True)
class Track:
    id: int
    detection: Detection
    first_seen: datetime
    last_seen: datetime
    missed_frames: int = 0
    zone_entered_at: dict[str, datetime] = field(default_factory=dict)
    previous_centroid: tuple[int, int] | None = None

    @property
    def centroid(self) -> tuple[int, int]:
        return self.detection.centroid


@dataclass(slots=True)
class AlertEvent:
    camera_id: str
    rule_id: str
    rule_name: str
    rule_type: str
    message: str
    occurred_at: datetime
    track_id: int | None = None
    confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

