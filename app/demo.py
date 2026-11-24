from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import uvicorn

from app.config import Settings, load_settings
from app.main import create_app


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def demo_settings() -> Settings:
    base = load_settings()
    return replace(
        base,
        cameras_config=PROJECT_ROOT / "config" / "cameras.demo.yaml",
        rules_config=PROJECT_ROOT / "config" / "rules.demo.yaml",
        database_path=PROJECT_ROOT / "data" / "demo-alerts.db",
        evidence_dir=PROJECT_ROOT / "evidence" / "demo",
        detector_model="demo",
    )


def main() -> None:
    settings = demo_settings()
    uvicorn.run(
        create_app(settings=settings),
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
