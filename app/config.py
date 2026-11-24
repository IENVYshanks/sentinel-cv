from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True, slots=True)
class Settings:
    cameras_config: Path
    rules_config: Path
    database_path: Path
    evidence_dir: Path
    detector_model: str
    host: str
    port: int
    face_detector_model: str = "models/yolov11n-face.pt"
    face_detector_confidence: float = 0.4
    identity_config: Path = Path("config/identities.yaml")
    identity_model: str = "models/face_recognition_sface_2021dec.onnx"
    identity_threshold: float = 0.45


def load_settings() -> Settings:
    load_dotenv()
    try:
        port = int(os.getenv("SENTINEL_PORT", "8000"))
    except ValueError as exc:
        raise ValueError("SENTINEL_PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise ValueError("SENTINEL_PORT must be between 1 and 65535")
    try:
        face_confidence = float(os.getenv("SENTINEL_FACE_DETECTOR_CONFIDENCE", "0.4"))
    except ValueError as exc:
        raise ValueError("SENTINEL_FACE_DETECTOR_CONFIDENCE must be a number") from exc
    if not 0 < face_confidence <= 1:
        raise ValueError(
            "SENTINEL_FACE_DETECTOR_CONFIDENCE must be greater than 0 and at most 1"
        )
    try:
        identity_threshold = float(os.getenv("SENTINEL_IDENTITY_THRESHOLD", "0.45"))
    except ValueError as exc:
        raise ValueError("SENTINEL_IDENTITY_THRESHOLD must be a number") from exc
    if not -1 <= identity_threshold <= 1:
        raise ValueError("SENTINEL_IDENTITY_THRESHOLD must be between -1 and 1")
    return Settings(
        cameras_config=Path(os.getenv("SENTINEL_CAMERAS_CONFIG", "config/cameras.yaml")),
        rules_config=Path(os.getenv("SENTINEL_RULES_CONFIG", "config/rules.yaml")),
        database_path=Path(os.getenv("SENTINEL_DATABASE_PATH", "data/alerts.db")),
        evidence_dir=Path(os.getenv("SENTINEL_EVIDENCE_DIR", "evidence")),
        detector_model=os.getenv("SENTINEL_DETECTOR_MODEL", "yolo11n.pt"),
        host=os.getenv("SENTINEL_HOST", "127.0.0.1"),
        port=port,
        face_detector_model=os.getenv(
            "SENTINEL_FACE_DETECTOR_MODEL", "models/yolov11n-face.pt"
        ),
        face_detector_confidence=face_confidence,
        identity_config=Path(
            os.getenv("SENTINEL_IDENTITY_CONFIG", "config/identities.yaml")
        ),
        identity_model=os.getenv(
            "SENTINEL_IDENTITY_MODEL",
            "models/face_recognition_sface_2021dec.onnx",
        ),
        identity_threshold=identity_threshold,
    )


def _load_yaml(path: Path, fallback: Path) -> dict[str, Any]:
    selected = path if path.exists() else fallback
    if not selected.exists():
        raise FileNotFoundError(f"Configuration file not found: {path} or {fallback}")
    with selected.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected a mapping in {selected}")
    return data


def load_cameras(settings: Settings) -> list[dict[str, Any]]:
    data = _load_yaml(settings.cameras_config, Path("config/cameras.example.yaml"))
    cameras = data.get("cameras", [])
    if not isinstance(cameras, list):
        raise ValueError("'cameras' must be a list")
    required = {"id", "name", "source"}
    seen: set[str] = set()
    for camera in cameras:
        if not isinstance(camera, dict) or not required.issubset(camera):
            raise ValueError(f"Invalid camera entry; required fields: {sorted(required)}")
        camera_id = str(camera["id"]).strip()
        if not camera_id:
            raise ValueError("Camera id must not be empty")
        if camera_id in seen:
            raise ValueError(f"Duplicate camera id: {camera_id}")
        seen.add(camera_id)
        if not str(camera["name"]).strip():
            raise ValueError(f"Camera {camera_id} name must not be empty")
        source = camera["source"]
        if isinstance(source, bool) or not isinstance(source, (int, str)):
            raise ValueError(f"Camera {camera_id} source must be an integer or string")
        if isinstance(source, str) and not source.strip():
            raise ValueError(f"Camera {camera_id} source must not be empty")
        try:
            process_interval = int(camera.get("process_every_n_frames", 1))
            face_process_interval = int(camera.get("face_process_every_n_frames", 1))
            reconnect_delay = float(camera.get("reconnect_seconds", 5))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Camera {camera_id} processing options must be numeric") from exc
        if process_interval < 1:
            raise ValueError(f"Camera {camera_id} process_every_n_frames must be at least 1")
        if face_process_interval < 1:
            raise ValueError(
                f"Camera {camera_id} face_process_every_n_frames must be at least 1"
            )
        if reconnect_delay <= 0:
            raise ValueError(f"Camera {camera_id} reconnect_seconds must be positive")
        if not isinstance(camera.get("face_detection", False), bool):
            raise ValueError(f"Camera {camera_id} face_detection must be true or false")
        if not isinstance(camera.get("identity_detection", False), bool):
            raise ValueError(f"Camera {camera_id} identity_detection must be true or false")
        if camera.get("identity_detection", False) and not camera.get(
            "face_detection", False
        ):
            raise ValueError(
                f"Camera {camera_id} identity_detection requires face_detection"
            )
    return cameras


def load_identities(settings: Settings) -> list[dict[str, Any]]:
    selected = (
        settings.identity_config
        if settings.identity_config.exists()
        else Path("config/identities.example.yaml")
    )
    if not selected.exists():
        raise FileNotFoundError(
            "Identity configuration file not found: "
            f"{settings.identity_config} or config/identities.example.yaml"
        )
    with selected.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict) or not isinstance(data.get("identities", []), list):
        raise ValueError("'identities' must be a list")
    identities: list[dict[str, Any]] = []
    seen: set[str] = set()
    for identity in data.get("identities", []):
        if not isinstance(identity, dict) or not {"id", "name", "images"}.issubset(
            identity
        ):
            raise ValueError("Each identity requires id, name, and images")
        identity_id = str(identity["id"]).strip()
        display_name = str(identity["name"]).strip()
        images = identity["images"]
        if not identity_id or not display_name:
            raise ValueError("Identity id and name must not be empty")
        if identity_id in seen:
            raise ValueError(f"Duplicate identity id: {identity_id}")
        if not isinstance(images, list) or not images or not all(
            isinstance(path, str) and path.strip() for path in images
        ):
            raise ValueError(f"Identity {identity_id} images must be a non-empty list")
        seen.add(identity_id)
        identities.append(
            {
                "id": identity_id,
                "name": display_name,
                "images": [
                    (selected.parent / path).resolve()
                    if not Path(path).is_absolute()
                    else Path(path)
                    for path in images
                ],
            }
        )
    return identities


def load_rule_config(settings: Settings) -> dict[str, Any]:
    data = _load_yaml(settings.rules_config, Path("config/rules.example.yaml"))
    if not isinstance(data.get("rules", []), list):
        raise ValueError("'rules' must be a list")
    timezone = str(data.get("timezone", "UTC"))
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"Unknown timezone: {timezone}") from exc
    try:
        retention = int(data.get("evidence_retention_days", 7))
    except (TypeError, ValueError) as exc:
        raise ValueError("evidence_retention_days must be an integer") from exc
    if retention < 0:
        raise ValueError("evidence_retention_days must not be negative")
    return data

