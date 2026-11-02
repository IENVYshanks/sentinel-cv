from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from app.models import AlertEvent


class AlertDatabase:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._create_schema()

    def _create_schema(self) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_id TEXT NOT NULL,
                    rule_id TEXT NOT NULL,
                    rule_name TEXT NOT NULL,
                    rule_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    track_id INTEGER,
                    confidence REAL,
                    evidence_file TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )

    def add_alert(self, event: AlertEvent, evidence_file: str | None) -> int:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                INSERT INTO alerts (
                    camera_id, rule_id, rule_name, rule_type, message,
                    occurred_at, track_id, confidence, evidence_file, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.camera_id,
                    event.rule_id,
                    event.rule_name,
                    event.rule_type,
                    event.message,
                    event.occurred_at.isoformat(),
                    event.track_id,
                    event.confidence,
                    evidence_file,
                    json.dumps(event.metadata),
                ),
            )
            return int(cursor.lastrowid)

    def list_alerts(self, limit: int = 100) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 500))
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM alerts ORDER BY occurred_at DESC LIMIT ?", (safe_limit,)
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["metadata"] = json.loads(item.pop("metadata_json"))
            result.append(item)
        return result

    def close(self) -> None:
        with self._lock:
            self._connection.close()

