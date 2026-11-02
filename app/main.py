from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.alerts import AlertService
from app.camera import CameraManager, CameraWorker, mjpeg_stream
from app.config import load_cameras, load_rule_config, load_settings
from app.database import AlertDatabase
from app.detector import PersonDetector


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
STATIC_DIR = Path(__file__).parent / "static"


def create_app(start_cameras: bool = True) -> FastAPI:
    settings = load_settings()
    camera_configs = load_cameras(settings)
    rule_config = load_rule_config(settings)

    from app.rules import RuleEngine

    database = AlertDatabase(settings.database_path)
    alerts = AlertService(
        database,
        settings.evidence_dir,
        int(rule_config.get("evidence_retention_days", 7)),
    )
    detector = PersonDetector(settings.detector_model)
    rules = RuleEngine(rule_config.get("rules", []), str(rule_config.get("timezone", "UTC")))
    workers = [
        CameraWorker(config, detector, rules, alerts)
        for config in camera_configs
        if config.get("enabled", True)
    ]
    cameras = CameraManager(workers)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        alerts.purge_expired()
        if start_cameras:
            cameras.start()
        yield
        cameras.stop()
        database.close()

    app = FastAPI(title="Sentinel CV", version="0.1.0", lifespan=lifespan)
    app.state.database = database
    app.state.cameras = cameras
    app.state.settings = settings

    @app.get("/api/health")
    def health() -> dict[str, object]:
        statuses = cameras.statuses()
        return {
            "status": "ok",
            "cameras": len(statuses),
            "connected": sum(1 for status in statuses if status["connected"]),
        }

    @app.get("/api/cameras")
    def list_camera_statuses() -> list[dict[str, object]]:
        return cameras.statuses()

    @app.get("/api/alerts")
    def list_alerts(limit: int = Query(default=100, ge=1, le=500)) -> list[dict[str, object]]:
        return database.list_alerts(limit)

    @app.get("/api/cameras/{camera_id}/stream")
    def camera_stream(camera_id: str) -> StreamingResponse:
        worker = cameras.get(camera_id)
        if not worker:
            raise HTTPException(status_code=404, detail="Camera not found")
        return StreamingResponse(
            mjpeg_stream(worker),
            media_type="multipart/x-mixed-replace; boundary=frame",
        )

    @app.get("/api/evidence/{filename}")
    def evidence(filename: str) -> FileResponse:
        safe_name = Path(filename).name
        target = settings.evidence_dir / safe_name
        if safe_name != filename or not target.is_file():
            raise HTTPException(status_code=404, detail="Evidence not found")
        return FileResponse(target, media_type="image/jpeg")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    return app


app = create_app()


if __name__ == "__main__":
    active_settings = load_settings()
    uvicorn.run("app.main:app", host=active_settings.host, port=active_settings.port, reload=False)

