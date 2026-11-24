from __future__ import annotations

import base64
import binascii
import logging
from contextlib import asynccontextmanager
from pathlib import Path
import uuid

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
import cv2
import numpy as np

from app.alerts import AlertService
from app.camera import CameraManager, CameraWorker, mjpeg_stream
from app.config import (
    Settings,
    load_cameras,
    load_identities,
    load_rule_config,
    load_settings,
)
from app.database import AlertDatabase
from app.detector import FaceDetector, PersonDetector
from app.identity import IdentityRecognizer
from app.schemas import (
    IdentityRenameRequest,
    IdentitySampleRequest,
    IdentityUpsertRequest,
)
from app.video_test import VideoTestManager, video_test_stream


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
STATIC_DIR = Path(__file__).parent / "static"


def create_app(start_cameras: bool = True, settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    camera_configs = load_cameras(settings)
    identities = load_identities(settings)
    rule_config = load_rule_config(settings)

    from app.rules import RuleEngine

    detector = PersonDetector(settings.detector_model)
    face_detector = FaceDetector(
        settings.face_detector_model, settings.face_detector_confidence
    )
    database = AlertDatabase(settings.database_path)
    identity_recognizer = IdentityRecognizer(
        settings.identity_model,
        identities,
        settings.identity_threshold,
        database=database,
    )
    rules = RuleEngine(rule_config.get("rules", []), str(rule_config.get("timezone", "UTC")))
    alerts = AlertService(
        database,
        settings.evidence_dir,
        int(rule_config.get("evidence_retention_days", 7)),
    )
    workers = [
        CameraWorker(
            config, detector, face_detector, identity_recognizer, rules, alerts
        )
        for config in camera_configs
        if config.get("enabled", True)
    ]
    cameras = CameraManager(workers)
    video_tests = VideoTestManager(detector, face_detector, identity_recognizer)
    video_test_dir = settings.database_path.parent / "video-tests"

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        alerts.purge_expired()
        if start_cameras:
            cameras.start()
        yield
        video_tests.stop()
        cameras.stop()
        database.close()

    app = FastAPI(title="Sentinel CV", version="0.1.0", lifespan=lifespan)
    app.state.database = database
    app.state.cameras = cameras
    app.state.settings = settings
    app.state.mode = "demo" if settings.detector_model == "demo" else "live"
    app.state.face_detector = face_detector
    app.state.identity_recognizer = identity_recognizer
    app.state.video_tests = video_tests

    def process_identity_image(image_base64: str):
        raw_value = image_base64
        if "," in raw_value and raw_value.startswith("data:"):
            raw_value = raw_value.split(",", 1)[1]
        try:
            image_bytes = base64.b64decode(raw_value, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(status_code=400, detail="Image is not valid base64") from exc
        if not image_bytes or len(image_bytes) > 10_000_000:
            raise HTTPException(
                status_code=400, detail="Image must be between 1 byte and 10 MB"
            )
        image = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise HTTPException(status_code=400, detail="Image could not be decoded")
        faces = app.state.face_detector.detect(image)
        if len(faces) != 1:
            raise HTTPException(
                status_code=400,
                detail=f"Enrollment requires exactly one detected face; found {len(faces)}",
            )
        try:
            return app.state.identity_recognizer.extract_embedding(image, faces[0])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.middleware("http")
    async def prevent_stale_static_assets(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    @app.get("/api/health")
    def health() -> dict[str, object]:
        statuses = cameras.statuses()
        connected = sum(1 for status in statuses if status["connected"])
        return {
            "status": "ok" if not start_cameras or connected == len(statuses) else "degraded",
            "mode": app.state.mode,
            "cameras": len(statuses),
            "connected": connected,
        }

    @app.get("/api/system")
    def system_information() -> dict[str, object]:
        statuses = cameras.statuses()
        return {
            "mode": app.state.mode,
            "host": settings.host,
            "port": settings.port,
            "detector_model": settings.detector_model,
            "face_detector_model": settings.face_detector_model,
            "identity_model": settings.identity_model,
            "identity_threshold": settings.identity_threshold,
            "database_path": str(settings.database_path),
            "evidence_dir": str(settings.evidence_dir),
            "evidence_retention_days": int(
                rule_config.get("evidence_retention_days", 7)
            ),
            "configured_cameras": len(camera_configs),
            "enabled_cameras": len(statuses),
        }

    @app.get("/api/cameras")
    def list_camera_statuses() -> list[dict[str, object]]:
        return cameras.statuses()

    @app.get("/api/alerts")
    def list_alerts(limit: int = Query(default=100, ge=1, le=500)) -> list[dict[str, object]]:
        return database.list_alerts(limit)

    @app.get("/api/identities")
    def list_identities() -> list[dict[str, object]]:
        return database.list_identities()

    @app.get("/api/identities/{identity_id}/image")
    def identity_image(identity_id: str) -> Response:
        identity = database.get_identity(identity_id)
        if not identity:
            raise HTTPException(status_code=404, detail="Identity not found")
        return Response(
            content=identity["face_image"],
            media_type="image/jpeg",
            headers={"Cache-Control": "no-store"},
        )

    @app.post("/api/identities", status_code=201)
    def upsert_identity(payload: IdentityUpsertRequest) -> dict[str, object]:
        embedding, face_image = process_identity_image(payload.image_base64)
        database.upsert_identity(
            payload.identity_id,
            payload.display_name,
            face_image,
            embedding.astype("float32").tobytes(),
            int(embedding.size),
        )
        app.state.identity_recognizer.reload_gallery()
        return {
            "identity_id": payload.identity_id,
            "display_name": payload.display_name.strip(),
        }

    @app.get("/api/identities/{identity_id}/samples")
    def list_identity_samples(identity_id: str) -> list[dict[str, object]]:
        identity = database.get_identity(identity_id)
        if not identity:
            raise HTTPException(status_code=404, detail="Identity not found")
        samples: list[dict[str, object]] = [
            {
                "sample_id": "primary",
                "primary": True,
                "created_at": identity["created_at"],
            }
        ]
        samples.extend(
            {
                "sample_id": sample["sample_id"],
                "primary": False,
                "created_at": sample["created_at"],
            }
            for sample in database.list_identity_samples(identity_id)
        )
        return samples

    @app.post("/api/identities/{identity_id}/samples", status_code=201)
    def add_identity_sample(
        identity_id: str, payload: IdentitySampleRequest
    ) -> dict[str, object]:
        if not database.get_identity(identity_id):
            raise HTTPException(status_code=404, detail="Identity not found")
        embedding, face_image = process_identity_image(payload.image_base64)
        sample_id = database.add_identity_sample(
            identity_id,
            face_image,
            embedding.astype("float32").tobytes(),
            int(embedding.size),
        )
        app.state.identity_recognizer.reload_gallery()
        return {"sample_id": sample_id, "identity_id": identity_id}

    @app.get("/api/identities/{identity_id}/samples/{sample_id}/image")
    def identity_sample_image(identity_id: str, sample_id: int) -> Response:
        sample = database.get_identity_sample(identity_id, sample_id)
        if not sample:
            raise HTTPException(status_code=404, detail="Identity sample not found")
        return Response(
            content=sample["face_image"],
            media_type="image/jpeg",
            headers={"Cache-Control": "no-store"},
        )

    @app.delete(
        "/api/identities/{identity_id}/samples/{sample_id}", status_code=204
    )
    def delete_identity_sample(identity_id: str, sample_id: int) -> Response:
        if not database.delete_identity_sample(identity_id, sample_id):
            raise HTTPException(status_code=404, detail="Identity sample not found")
        app.state.identity_recognizer.reload_gallery()
        return Response(status_code=204)

    @app.patch("/api/identities/{identity_id}")
    def rename_identity(
        identity_id: str, payload: IdentityRenameRequest
    ) -> dict[str, object]:
        if not database.rename_identity(identity_id, payload.display_name):
            raise HTTPException(status_code=404, detail="Identity not found")
        app.state.identity_recognizer.reload_gallery()
        return {
            "identity_id": identity_id,
            "display_name": payload.display_name.strip(),
        }

    @app.delete("/api/identities/{identity_id}", status_code=204)
    def delete_identity(identity_id: str) -> Response:
        if not database.delete_identity(identity_id):
            raise HTTPException(status_code=404, detail="Identity not found")
        app.state.identity_recognizer.reload_gallery()
        return Response(status_code=204)

    @app.post("/api/video-tests", status_code=201)
    async def create_video_test(
        request: Request, filename: str = Query(min_length=1, max_length=255)
    ) -> dict[str, object]:
        safe_filename = Path(filename).name
        suffix = Path(safe_filename).suffix.lower()
        if suffix not in {".mp4", ".mov", ".avi", ".mkv", ".webm"}:
            raise HTTPException(
                status_code=400,
                detail="Video must be MP4, MOV, AVI, MKV, or WebM",
            )
        maximum_size = 250 * 1024 * 1024
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                declared_size = int(content_length)
            except ValueError as exc:
                raise HTTPException(
                    status_code=400, detail="Invalid Content-Length header"
                ) from exc
            if declared_size > maximum_size:
                raise HTTPException(
                    status_code=413, detail="Video must be 250 MB or smaller"
                )
        video_test_dir.mkdir(parents=True, exist_ok=True)
        target = video_test_dir / f"{uuid.uuid4().hex}{suffix}"
        size = 0
        try:
            with target.open("wb") as handle:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > maximum_size:
                        raise HTTPException(
                            status_code=413, detail="Video must be 250 MB or smaller"
                        )
                    handle.write(chunk)
            if size == 0:
                raise HTTPException(status_code=400, detail="Uploaded video is empty")
            worker = video_tests.create(safe_filename, target)
            return worker.status()
        except HTTPException:
            target.unlink(missing_ok=True)
            raise
        except RuntimeError as exc:
            target.unlink(missing_ok=True)
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception:
            target.unlink(missing_ok=True)
            raise

    @app.get("/api/video-tests/{job_id}")
    def video_test_status(job_id: str) -> dict[str, object]:
        worker = video_tests.get(job_id)
        if not worker:
            raise HTTPException(status_code=404, detail="Video test not found")
        return worker.status()

    @app.get("/api/video-tests/{job_id}/stream")
    def video_test_preview(job_id: str) -> StreamingResponse:
        worker = video_tests.get(job_id)
        if not worker:
            raise HTTPException(status_code=404, detail="Video test not found")
        return StreamingResponse(
            video_test_stream(worker),
            media_type="multipart/x-mixed-replace; boundary=frame",
        )

    @app.delete("/api/video-tests/{job_id}", status_code=204)
    def cancel_video_test(job_id: str) -> Response:
        if not video_tests.cancel(job_id):
            raise HTTPException(status_code=404, detail="Video test not found")
        return Response(status_code=204)

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

    @app.get("/cameras", include_in_schema=False)
    def cameras_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "cameras.html")

    @app.get("/identities", include_in_schema=False)
    def identities_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "identities.html")

    @app.get("/alerts", include_in_schema=False)
    def alerts_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "alerts.html")

    @app.get("/settings", include_in_schema=False)
    def settings_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "settings.html")

    @app.get("/about", include_in_schema=False)
    def about_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "about.html")

    @app.get("/video-test", include_in_schema=False)
    def video_test_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "video-test.html")

    return app


if __name__ == "__main__":
    active_settings = load_settings()
    uvicorn.run(
        create_app(settings=active_settings),
        host=active_settings.host,
        port=active_settings.port,
        reload=False,
    )

