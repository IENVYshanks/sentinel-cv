from __future__ import annotations

import threading
from typing import Any

from app.models import Detection


class PersonDetector:
    """Lazy-loaded YOLO detector shared safely by camera workers."""

    def __init__(self, model_name: str, confidence: float = 0.4):
        self.model_name = model_name
        self.confidence = confidence
        self._model: Any = None
        self._lock = threading.Lock()

    def _load(self) -> None:
        if self._model is None:
            from ultralytics import YOLO

            self._model = YOLO(self.model_name)

    def detect(self, frame: Any) -> list[Detection]:
        with self._lock:
            self._load()
            results = self._model.predict(
                source=frame,
                classes=[0],
                conf=self.confidence,
                verbose=False,
            )
        detections: list[Detection] = []
        if not results:
            return detections
        for box in results[0].boxes:
            coordinates = box.xyxy[0].tolist()
            confidence = float(box.conf[0])
            detections.append(
                Detection(
                    x1=int(coordinates[0]),
                    y1=int(coordinates[1]),
                    x2=int(coordinates[2]),
                    y2=int(coordinates[3]),
                    confidence=confidence,
                )
            )
        return detections

