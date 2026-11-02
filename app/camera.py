from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any

import cv2
import numpy as np

from app.alerts import AlertService
from app.detector import PersonDetector
from app.rules import RuleEngine
from app.tracker import CentroidTracker


LOGGER = logging.getLogger(__name__)


def normalize_source(source: Any) -> Any:
    if isinstance(source, str) and source.strip().isdigit():
        return int(source.strip())
    return source


class CameraWorker:
    def __init__(
        self,
        config: dict[str, Any],
        detector: PersonDetector,
        rule_engine: RuleEngine,
        alert_service: AlertService,
    ):
        self.id = str(config["id"])
        self.name = str(config["name"])
        self.source = normalize_source(config["source"])
        self.process_every_n_frames = max(1, int(config.get("process_every_n_frames", 1)))
        self.reconnect_seconds = max(1.0, float(config.get("reconnect_seconds", 5)))
        self.detector = detector
        self.rule_engine = rule_engine
        self.alert_service = alert_service
        self.tracker = CentroidTracker()
        self.running = False
        self.connected = False
        self.last_error: str | None = None
        self.frames_processed = 0
        self._latest_jpeg: bytes | None = None
        self._frame_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self.running = True
        self._thread = threading.Thread(target=self._run, name=f"camera-{self.id}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        self.running = False

    def latest_jpeg(self) -> bytes | None:
        with self._frame_lock:
            return self._latest_jpeg

    def status(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "running": self.running,
            "connected": self.connected,
            "last_error": self.last_error,
            "frames_processed": self.frames_processed,
        }

    def _run(self) -> None:
        while not self._stop.is_set():
            capture = cv2.VideoCapture(self.source)
            if not capture.isOpened():
                self.connected = False
                self.last_error = "Unable to open camera source"
                capture.release()
                self._stop.wait(self.reconnect_seconds)
                continue
            self.connected = True
            self.last_error = None
            frame_number = 0
            try:
                while not self._stop.is_set():
                    success, frame = capture.read()
                    if not success:
                        self.last_error = "Camera stream ended or frame read failed"
                        break
                    frame_number += 1
                    if frame_number % self.process_every_n_frames != 0:
                        continue
                    self._process_frame(frame)
            except Exception as exc:  # keep other cameras alive if one worker fails
                LOGGER.exception("Camera %s failed", self.id)
                self.last_error = str(exc)
            finally:
                capture.release()
                self.connected = False
            if not self._stop.is_set():
                self._stop.wait(self.reconnect_seconds)
        self.running = False

    def _process_frame(self, frame: Any) -> None:
        now = datetime.now(timezone.utc)
        detections = self.detector.detect(frame)
        tracks = self.tracker.update(detections, now)
        events = self.rule_engine.evaluate(self.id, tracks, now)
        annotated = frame.copy()

        for rule in self.rule_engine.rules_for_camera(self.id):
            if rule["type"] == "line_crossing":
                points = np.array(rule["line"], dtype=np.int32)
                cv2.line(annotated, tuple(points[0]), tuple(points[1]), (255, 120, 40), 2)
                x, y = points[0]
                cv2.putText(
                    annotated,
                    str(rule["name"]),
                    (int(x), max(20, int(y) - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (255, 120, 40),
                    2,
                )
                continue
            points = np.array(rule["zone"], dtype=np.int32)
            cv2.polylines(annotated, [points], True, (0, 165, 255), 2)
            x, y = points[0]
            cv2.putText(
                annotated,
                str(rule["name"]),
                (int(x), max(20, int(y) - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 165, 255),
                2,
            )
        for track in tracks:
            detection = track.detection
            cv2.rectangle(
                annotated,
                (detection.x1, detection.y1),
                (detection.x2, detection.y2),
                (50, 205, 50),
                2,
            )
            cv2.putText(
                annotated,
                f"person #{track.id} {detection.confidence:.2f}",
                (detection.x1, max(20, detection.y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (50, 205, 50),
                2,
            )
        for event in events:
            self.alert_service.record(event, annotated)

        success, encoded = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if success:
            with self._frame_lock:
                self._latest_jpeg = encoded.tobytes()
        self.frames_processed += 1


class CameraManager:
    def __init__(self, workers: list[CameraWorker]):
        self.workers = {worker.id: worker for worker in workers}

    def start(self) -> None:
        for worker in self.workers.values():
            worker.start()

    def stop(self) -> None:
        for worker in self.workers.values():
            worker.stop()

    def statuses(self) -> list[dict[str, Any]]:
        return [worker.status() for worker in self.workers.values()]

    def get(self, camera_id: str) -> CameraWorker | None:
        return self.workers.get(camera_id)


def mjpeg_stream(worker: CameraWorker):
    while worker.running:
        frame = worker.latest_jpeg()
        if frame:
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
        time.sleep(0.1)

