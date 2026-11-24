from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any

import cv2
import numpy as np

from app.alerts import AlertService
from app.detector import FaceDetector, PersonDetector
from app.identity import IdentityRecognizer
from app.models import Detection, IdentityMatch, Track
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
        face_detector: FaceDetector,
        identity_recognizer: IdentityRecognizer,
        rule_engine: RuleEngine,
        alert_service: AlertService,
    ):
        self.id = str(config["id"])
        self.name = str(config["name"])
        self.source = normalize_source(config["source"])
        self.process_every_n_frames = max(1, int(config.get("process_every_n_frames", 1)))
        self.reconnect_seconds = max(1.0, float(config.get("reconnect_seconds", 5)))
        self.detector = detector
        self.face_detector = face_detector
        self.identity_recognizer = identity_recognizer
        self.face_detection_enabled = bool(config.get("face_detection", False))
        self.identity_detection_enabled = bool(
            config.get("identity_detection", False)
        )
        self.face_process_every_n_frames = max(
            1, int(config.get("face_process_every_n_frames", 1))
        )
        self.rule_engine = rule_engine
        self.alert_service = alert_service
        self.tracker = CentroidTracker()
        self.running = False
        self.connected = False
        self.last_error: str | None = None
        self.frames_processed = 0
        self.faces_detected = 0
        self._face_detections: list[Detection] = []
        self._identity_matches: list[IdentityMatch] = []
        self.recognized_identities: list[str] = []
        self._latest_jpeg: bytes | None = None
        self._frame_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        with self._state_lock:
            if self.running:
                return
            self._stop.clear()
            self.running = True
            self._thread = threading.Thread(
                target=self._run, name=f"camera-{self.id}", daemon=True
            )
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=5)
        with self._state_lock:
            if not thread or not thread.is_alive():
                self.running = False
                self._thread = None

    def latest_jpeg(self) -> bytes | None:
        with self._frame_lock:
            return self._latest_jpeg

    def status(self) -> dict[str, Any]:
        with self._state_lock:
            return {
                "id": self.id,
                "name": self.name,
                "running": self.running,
                "connected": self.connected,
                "last_error": self.last_error,
                "frames_processed": self.frames_processed,
                "face_detection_enabled": self.face_detection_enabled,
                "faces_detected": self.faces_detected,
                "identity_detection_enabled": self.identity_detection_enabled,
                "recognized_identities": list(self.recognized_identities),
            }

    def _run(self) -> None:
        if isinstance(self.source, str) and self.source.lower().startswith("demo://"):
            self._run_demo()
            return
        while not self._stop.is_set():
            capture = cv2.VideoCapture(self.source)
            if not capture.isOpened():
                with self._state_lock:
                    self.connected = False
                    self.last_error = "Unable to open camera source"
                capture.release()
                self._stop.wait(self.reconnect_seconds)
                continue
            with self._state_lock:
                self.connected = True
                self.last_error = None
            frame_number = 0
            try:
                while not self._stop.is_set():
                    success, frame = capture.read()
                    if not success:
                        with self._state_lock:
                            self.last_error = "Camera stream ended or frame read failed"
                        break
                    frame_number += 1
                    if frame_number % self.process_every_n_frames != 0:
                        continue
                    self._process_frame(frame)
            except Exception as exc:  # keep other cameras alive if one worker fails
                LOGGER.exception("Camera %s failed", self.id)
                with self._state_lock:
                    self.last_error = str(exc)
            finally:
                capture.release()
                with self._state_lock:
                    self.connected = False
            if not self._stop.is_set():
                self._stop.wait(self.reconnect_seconds)
        with self._state_lock:
            self.running = False
            self.connected = False
            self._thread = None

    def _run_demo(self) -> None:
        """Generate a deterministic scene that exercises the production pipeline."""
        width, height = 640, 480
        frame_number = 0
        frame_interval = 1 / 12
        with self._state_lock:
            self.connected = True
            self.last_error = None
        try:
            while not self._stop.is_set():
                frame = np.full((height, width, 3), (18, 23, 31), dtype=np.uint8)
                for x in range(0, width, 40):
                    cv2.line(frame, (x, 0), (x, height), (28, 35, 45), 1)
                for y in range(0, height, 40):
                    cv2.line(frame, (0, y), (width, y), (28, 35, 45), 1)

                cycle = frame_number % 240
                moving_y = 35 + int(315 * cycle / 120) if cycle < 120 else 350 - int(315 * (cycle - 120) / 120)
                self._draw_demo_person(frame, 255, moving_y, "MOVING")
                self._draw_demo_person(frame, 410, 175, "LOITERING")
                if 60 <= cycle < 180:
                    self._draw_demo_person(frame, 480, 205, "VISITOR")

                cv2.putText(
                    frame,
                    "SENTINEL CV - SYNTHETIC DEMO",
                    (18, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.65,
                    (220, 230, 240),
                    2,
                )
                self._process_frame(frame)
                frame_number += 1
                if self._stop.wait(frame_interval):
                    break
        except Exception as exc:
            LOGGER.exception("Demo camera %s failed", self.id)
            with self._state_lock:
                self.last_error = str(exc)
        finally:
            with self._state_lock:
                self.running = False
                self.connected = False
                self._thread = None

    @staticmethod
    def _draw_demo_person(frame: Any, x: int, y: int, label: str) -> None:
        color = (40, 240, 40)
        cv2.rectangle(frame, (x, y + 20), (x + 42, y + 110), color, -1)
        cv2.circle(frame, (x + 21, y + 20), 20, color, -1)
        cv2.putText(
            frame,
            label,
            (x - 5, max(50, y - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (190, 255, 190),
            1,
        )

    def _process_frame(self, frame: Any) -> None:
        now = datetime.now(timezone.utc)
        detections = self.detector.detect(frame)
        current_identity_matches: list[IdentityMatch] = []
        if (
            self.face_detection_enabled
            and self.frames_processed % self.face_process_every_n_frames == 0
        ):
            self._face_detections = self.face_detector.detect(frame)
            if self.identity_detection_enabled:
                self._identity_matches = self.identity_recognizer.recognize(
                    frame, self._face_detections
                )
            else:
                self._identity_matches = []
            current_identity_matches = self._identity_matches
            with self._state_lock:
                self.faces_detected = len(self._face_detections)
                self.recognized_identities = sorted(
                    {match.display_name for match in self._identity_matches if match.known}
                )
        tracks = self.tracker.update(detections, now)
        identity_matches_by_track = self._associate_identities(
            tracks, current_identity_matches
        )
        events = self.rule_engine.evaluate(self.id, tracks, now)
        tracks_by_id = {track.id: track for track in tracks}
        for event in events:
            track = tracks_by_id.get(event.track_id)
            if track and track.identity_id:
                event.metadata.update(
                    {
                        "identity_id": track.identity_id,
                        "identity_name": track.identity_name,
                        "identity_confidence": track.identity_confidence,
                    }
                )
                event.message = f"{event.message} ({track.identity_name})"
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
        self.draw_individual_boxes(annotated, tracks, identity_matches_by_track)
        for event in events:
            self.alert_service.record(event, annotated)

        success, encoded = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if success:
            with self._frame_lock:
                self._latest_jpeg = encoded.tobytes()
        self.frames_processed += 1

    @staticmethod
    def _associate_identities(
        tracks: list[Track], matches: list[IdentityMatch]
    ) -> dict[int, IdentityMatch]:
        associations: dict[int, IdentityMatch] = {}
        for match in matches:
            face_x, face_y = match.face.centroid
            candidates = [
                track
                for track in tracks
                if track.detection.x1 <= face_x <= track.detection.x2
                and track.detection.y1 <= face_y <= track.detection.y2
            ]
            if not candidates:
                continue
            track = min(
                candidates,
                key=lambda item: (item.detection.x2 - item.detection.x1)
                * (item.detection.y2 - item.detection.y1),
            )
            previous = associations.get(track.id)
            if previous is None or match.confidence > previous.confidence:
                associations[track.id] = match
            if match.known:
                track.identity_id = match.identity_id
                track.identity_name = match.display_name
                track.identity_confidence = match.confidence
        return associations

    @staticmethod
    def draw_individual_boxes(
        frame: Any,
        tracks: list[Track],
        matches_by_track: dict[int, IdentityMatch],
    ) -> None:
        """Draw one box per individual, preferring a current face box."""
        for track in tracks:
            match = matches_by_track.get(track.id)
            detection = match.face if match is not None else track.detection
            if track.identity_name:
                name = track.identity_name
                identity_confidence = (
                    match.confidence if match is not None else track.identity_confidence
                )
            elif match is not None:
                name = "Unknown"
                identity_confidence = match.confidence
            else:
                name = "Person"
                identity_confidence = detection.confidence
            confidence_text = (
                f" {identity_confidence:.2f}"
                if identity_confidence is not None
                else ""
            )
            color = (50, 205, 50) if track.identity_name else (0, 180, 255)
            cv2.rectangle(
                frame,
                (detection.x1, detection.y1),
                (detection.x2, detection.y2),
                color,
                2,
            )
            cv2.putText(
                frame,
                f"{name} #{track.id}{confidence_text}",
                (detection.x1, max(20, detection.y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                color,
                2,
            )


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
    while worker.status()["running"]:
        frame = worker.latest_jpeg()
        if frame:
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
        if worker._stop.wait(0.1):
            break

