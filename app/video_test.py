from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2

from app.camera import CameraWorker
from app.detector import FaceDetector, PersonDetector
from app.identity import IdentityRecognizer
from app.tracker import CentroidTracker


TERMINAL_STATES = {"completed", "canceled", "failed"}


class VideoTestWorker:
    def __init__(
        self,
        job_id: str,
        filename: str,
        path: Path,
        detector: PersonDetector,
        face_detector: FaceDetector,
        identity_recognizer: IdentityRecognizer,
    ):
        self.id = job_id
        self.filename = filename
        self.path = path
        self.detector = detector
        self.face_detector = face_detector
        self.identity_recognizer = identity_recognizer
        self.state = "queued"
        self.error: str | None = None
        self.frames_processed = 0
        self.total_frames = 0
        self.recognized_identities: set[str] = set()
        self._tracker = CentroidTracker()
        self._latest_jpeg: bytes | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run, name=f"video-test-{self.id}", daemon=True
        )
        self._thread.start()

    def cancel(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=5)

    def status(self) -> dict[str, object]:
        with self._lock:
            progress = (
                round(self.frames_processed / self.total_frames * 100, 1)
                if self.total_frames > 0
                else 0.0
            )
            if self.state == "completed":
                progress = 100.0
            return {
                "id": self.id,
                "filename": self.filename,
                "state": self.state,
                "error": self.error,
                "frames_processed": self.frames_processed,
                "total_frames": self.total_frames,
                "progress": min(progress, 100.0),
                "recognized_identities": sorted(self.recognized_identities),
            }

    def latest_jpeg(self) -> bytes | None:
        with self._lock:
            return self._latest_jpeg

    def _run(self) -> None:
        capture = cv2.VideoCapture(str(self.path))
        if not capture.isOpened():
            with self._lock:
                self.state = "failed"
                self.error = "Uploaded video could not be opened"
            self.path.unlink(missing_ok=True)
            return
        with self._lock:
            self.state = "processing"
            self.total_frames = max(0, int(capture.get(cv2.CAP_PROP_FRAME_COUNT)))
        try:
            while not self._stop.is_set():
                success, frame = capture.read()
                if not success:
                    break
                detections = self.detector.detect(frame)
                faces = self.face_detector.detect(frame)
                face_matches = self.identity_recognizer.recognize(frame, faces)
                tracks = self._tracker.update(detections, datetime.now(timezone.utc))
                associations = CameraWorker._associate_identities(tracks, face_matches)
                annotated = frame.copy()
                CameraWorker.draw_individual_boxes(annotated, tracks, associations)
                recognized = {
                    track.identity_name for track in tracks if track.identity_name
                }
                ok, encoded = cv2.imencode(
                    ".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 82]
                )
                with self._lock:
                    self.frames_processed += 1
                    self.recognized_identities.update(recognized)
                    if ok:
                        self._latest_jpeg = encoded.tobytes()
            with self._lock:
                self.state = "canceled" if self._stop.is_set() else "completed"
        except Exception as exc:
            with self._lock:
                self.state = "failed"
                self.error = str(exc)
        finally:
            capture.release()
            self.path.unlink(missing_ok=True)


class VideoTestManager:
    def __init__(
        self,
        detector: PersonDetector,
        face_detector: FaceDetector,
        identity_recognizer: IdentityRecognizer,
    ):
        self.detector = detector
        self.face_detector = face_detector
        self.identity_recognizer = identity_recognizer
        self._active: VideoTestWorker | None = None
        self._lock = threading.Lock()

    def create(self, filename: str, path: Path) -> VideoTestWorker:
        with self._lock:
            if self._active and self._active.status()["state"] not in TERMINAL_STATES:
                raise RuntimeError("Another video test is already running")
            worker = VideoTestWorker(
                uuid.uuid4().hex,
                filename,
                path,
                self.detector,
                self.face_detector,
                self.identity_recognizer,
            )
            self._active = worker
            worker.start()
            return worker

    def get(self, job_id: str) -> VideoTestWorker | None:
        with self._lock:
            if self._active and self._active.id == job_id:
                return self._active
            return None

    def cancel(self, job_id: str) -> bool:
        worker = self.get(job_id)
        if not worker:
            return False
        worker.cancel()
        return True

    def stop(self) -> None:
        with self._lock:
            worker = self._active
        if worker:
            worker.cancel()


def video_test_stream(worker: VideoTestWorker):
    previous: bytes | None = None
    while True:
        frame = worker.latest_jpeg()
        if frame and frame != previous:
            previous = frame
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
        status = worker.status()["state"]
        if status in TERMINAL_STATES and frame == previous:
            break
        if worker._stop.wait(0.05):
            break
