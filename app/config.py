from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Settings:
    cameras_config: Path
    rules_config: Path
    database_path: Path
    evidence_dir: Path
    detector_model: str
    host: str
    port: int


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        cameras_config=Path(os.getenv("SENTINEL_CAMERAS_CONFIG", "config/cameras.yaml")),
        rules_config=Path(os.getenv("SENTINEL_RULES_CONFIG", "config/rules.yaml")),
        database_path=Path(os.getenv("SENTINEL_DATABASE_PATH", "data/alerts.db")),
        evidence_dir=Path(os.getenv("SENTINEL_EVIDENCE_DIR", "evidence")),
        detector_model=os.getenv("SENTINEL_DETECTOR_MODEL", "yolo11n.pt"),
        host=os.getenv("SENTINEL_HOST", "127.0.0.1"),
        port=int(os.getenv("SENTINEL_PORT", "8000")),
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
    for camera in cameras:
        if not isinstance(camera, dict) or not required.issubset(camera):
            raise ValueError(f"Invalid camera entry; required fields: {sorted(required)}")
    return cameras


def load_rule_config(settings: Settings) -> dict[str, Any]:
    data = _load_yaml(settings.rules_config, Path("config/rules.example.yaml"))
    if not isinstance(data.get("rules", []), list):
        raise ValueError("'rules' must be a list")
    return data

