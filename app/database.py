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
        self._closed = False
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

            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS identities (
                    identity_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    face_image BLOB NOT NULL,
                    embedding BLOB NOT NULL,
                    embedding_dimensions INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS identity_samples (
                    sample_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    identity_id TEXT NOT NULL,
                    face_image BLOB NOT NULL,
                    embedding BLOB NOT NULL,
                    embedding_dimensions INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(identity_id) REFERENCES identities(identity_id)
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

    def upsert_identity(
        self,
        identity_id: str,
        display_name: str,
        face_image: bytes,
        embedding: bytes,
        embedding_dimensions: int,
    ) -> None:
        if not identity_id.strip() or not display_name.strip():
            raise ValueError("Identity id and display name must not be empty")
        if not face_image or not embedding or embedding_dimensions < 1:
            raise ValueError("Identity image and embedding must not be empty")
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO identities (
                    identity_id, display_name, face_image, embedding,
                    embedding_dimensions
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(identity_id) DO UPDATE SET
                    display_name = excluded.display_name,
                    face_image = excluded.face_image,
                    embedding = excluded.embedding,
                    embedding_dimensions = excluded.embedding_dimensions,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    identity_id.strip(),
                    display_name.strip(),
                    sqlite3.Binary(face_image),
                    sqlite3.Binary(embedding),
                    embedding_dimensions,
                ),
            )

    def list_identity_embeddings(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT identity_id, display_name, embedding, embedding_dimensions
                FROM identities
                UNION ALL
                SELECT samples.identity_id, identities.display_name,
                       samples.embedding, samples.embedding_dimensions
                FROM identity_samples AS samples
                JOIN identities ON identities.identity_id = samples.identity_id
                ORDER BY identity_id
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def add_identity_sample(
        self,
        identity_id: str,
        face_image: bytes,
        embedding: bytes,
        embedding_dimensions: int,
    ) -> int:
        if not face_image or not embedding or embedding_dimensions < 1:
            raise ValueError("Identity sample image and embedding must not be empty")
        with self._lock, self._connection:
            exists = self._connection.execute(
                "SELECT 1 FROM identities WHERE identity_id = ?", (identity_id,)
            ).fetchone()
            if not exists:
                raise KeyError(identity_id)
            cursor = self._connection.execute(
                """
                INSERT INTO identity_samples (
                    identity_id, face_image, embedding, embedding_dimensions
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    identity_id,
                    sqlite3.Binary(face_image),
                    sqlite3.Binary(embedding),
                    embedding_dimensions,
                ),
            )
            self._connection.execute(
                """
                UPDATE identities SET updated_at = CURRENT_TIMESTAMP
                WHERE identity_id = ?
                """,
                (identity_id,),
            )
            return int(cursor.lastrowid)

    def list_identity_samples(self, identity_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT sample_id, identity_id, created_at
                FROM identity_samples
                WHERE identity_id = ?
                ORDER BY sample_id
                """,
                (identity_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_identity_sample(
        self, identity_id: str, sample_id: int
    ) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT * FROM identity_samples
                WHERE identity_id = ? AND sample_id = ?
                """,
                (identity_id, sample_id),
            ).fetchone()
        return dict(row) if row else None

    def delete_identity_sample(self, identity_id: str, sample_id: int) -> bool:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                DELETE FROM identity_samples
                WHERE identity_id = ? AND sample_id = ?
                """,
                (identity_id, sample_id),
            )
            if cursor.rowcount:
                self._connection.execute(
                    """
                    UPDATE identities SET updated_at = CURRENT_TIMESTAMP
                    WHERE identity_id = ?
                    """,
                    (identity_id,),
                )
        return cursor.rowcount > 0

    def get_identity(self, identity_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM identities WHERE identity_id = ?", (identity_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_identities(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT identity_id, display_name, created_at, updated_at
                     , 1 + (
                         SELECT COUNT(*) FROM identity_samples
                         WHERE identity_samples.identity_id = identities.identity_id
                       ) AS sample_count
                FROM identities
                ORDER BY display_name COLLATE NOCASE, identity_id
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def rename_identity(self, identity_id: str, display_name: str) -> bool:
        clean_name = display_name.strip()
        if not clean_name:
            raise ValueError("Display name must not be empty")
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                UPDATE identities
                SET display_name = ?, updated_at = CURRENT_TIMESTAMP
                WHERE identity_id = ?
                """,
                (clean_name, identity_id),
            )
        return cursor.rowcount > 0

    def delete_identity(self, identity_id: str) -> bool:
        with self._lock, self._connection:
            self._connection.execute(
                "DELETE FROM identity_samples WHERE identity_id = ?", (identity_id,)
            )
            cursor = self._connection.execute(
                "DELETE FROM identities WHERE identity_id = ?", (identity_id,)
            )
        return cursor.rowcount > 0

    def list_alerts(self, limit: int = 100) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 500))
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM alerts ORDER BY occurred_at DESC LIMIT ?", (safe_limit,)
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            try:
                item["metadata"] = json.loads(item.pop("metadata_json"))
            except (json.JSONDecodeError, TypeError):
                item["metadata"] = {}
            result.append(item)
        return result

    def clear_evidence_file(self, filename: str) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "UPDATE alerts SET evidence_file = NULL WHERE evidence_file = ?", (filename,)
            )

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._connection.close()
                self._closed = True

