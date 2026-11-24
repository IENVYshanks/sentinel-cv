from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import cv2

from app.database import AlertDatabase
from app.models import AlertEvent


class AlertService:
    def __init__(self, database: AlertDatabase, evidence_dir: Path, retention_days: int):
        self.database = database
        self.evidence_dir = evidence_dir
        self.retention_days = max(0, retention_days)
        evidence_dir.mkdir(parents=True, exist_ok=True)

    def record(self, event: AlertEvent, frame: Any) -> int:
        timestamp = event.occurred_at.strftime("%Y%m%dT%H%M%S_%f")
        safe_rule_id = "".join(char for char in event.rule_id if char.isalnum() or char in "-_")
        safe_camera_id = self._safe_component(event.camera_id, "camera")
        safe_rule_id = self._safe_component(safe_rule_id, "rule")
        filename = f"{safe_camera_id}_{safe_rule_id}_{timestamp}.jpg"
        target = self.evidence_dir / filename
        evidence_file = filename if cv2.imwrite(str(target), frame) else None
        try:
            return self.database.add_alert(event, evidence_file)
        except Exception:
            if evidence_file:
                target.unlink(missing_ok=True)
            raise

    @staticmethod
    def _safe_component(value: str, fallback: str) -> str:
        safe = "".join(char for char in str(value) if char.isalnum() or char in "-_")
        return safe or fallback

    def purge_expired(self) -> int:
        if self.retention_days <= 0:
            return 0
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.retention_days)
        removed = 0
        for path in self.evidence_dir.glob("*.jpg"):
            modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
            if modified < cutoff:
                path.unlink(missing_ok=True)
                self.database.clear_evidence_file(path.name)
                removed += 1
        return removed

