from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

import cv2
import numpy as np

from app.models import Detection, IdentityMatch

if TYPE_CHECKING:
    from app.database import AlertDatabase


class IdentityRecognizer:
    """Match face crops to a private, explicitly configured reference gallery."""

    def __init__(
        self,
        model_name: str,
        identities: list[dict[str, Any]],
        threshold: float = 0.45,
        database: AlertDatabase | None = None,
    ):
        self.model_name = model_name
        self.identities = identities
        self.threshold = threshold
        self.database = database
        self._recognizer: Any = None
        self._gallery: list[tuple[str, str, np.ndarray]] | None = None
        self._lock = threading.Lock()

    def _load_recognizer(self) -> None:
        if self._recognizer is None:
            self._recognizer = cv2.FaceRecognizerSF.create(self.model_name, "")

    @staticmethod
    def _prepare_face(image: Any) -> Any:
        return cv2.resize(image, (112, 112), interpolation=cv2.INTER_AREA)

    def _feature(self, image: Any) -> np.ndarray:
        feature = np.asarray(
            self._recognizer.feature(self._prepare_face(image)), dtype=np.float32
        ).reshape(-1)
        magnitude = float(np.linalg.norm(feature))
        if magnitude == 0:
            raise ValueError("Face recognition model returned an empty feature")
        return feature / magnitude

    def _load_gallery(self) -> None:
        if self._gallery is not None:
            return
        gallery: list[tuple[str, str, np.ndarray]] = []
        for identity in self.identities:
            identity_id = str(identity["id"])
            display_name = str(identity["name"])
            for image_path in identity["images"]:
                reference = cv2.imread(str(image_path))
                if reference is None:
                    raise FileNotFoundError(
                        f"Identity reference image could not be read: {image_path}"
                    )
                gallery.append(
                    (identity_id, display_name, self._feature(reference))
                )
        if self.database is not None:
            for identity in self.database.list_identity_embeddings():
                feature = np.frombuffer(identity["embedding"], dtype=np.float32).copy()
                expected = int(identity["embedding_dimensions"])
                if feature.size != expected:
                    raise ValueError(
                        f"Stored embedding for {identity['identity_id']} has invalid dimensions"
                    )
                magnitude = float(np.linalg.norm(feature))
                if magnitude == 0:
                    raise ValueError(
                        f"Stored embedding for {identity['identity_id']} is empty"
                    )
                gallery.append(
                    (
                        str(identity["identity_id"]),
                        str(identity["display_name"]),
                        feature / magnitude,
                    )
                )
        self._gallery = gallery

    def reload_gallery(self) -> None:
        """Discard cached embeddings so the next frame reloads current identities."""
        with self._lock:
            self._gallery = None

    def extract_embedding(
        self, frame: Any, face: Detection
    ) -> tuple[np.ndarray, bytes]:
        height, width = frame.shape[:2]
        x1 = max(0, min(width, face.x1))
        y1 = max(0, min(height, face.y1))
        x2 = max(0, min(width, face.x2))
        y2 = max(0, min(height, face.y2))
        if x2 <= x1 or y2 <= y1:
            raise ValueError("Face bounding box is outside the image")
        crop = frame[y1:y2, x1:x2]
        with self._lock:
            self._load_recognizer()
            feature = self._feature(crop)
        success, encoded = cv2.imencode(
            ".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 92]
        )
        if not success:
            raise ValueError("Unable to encode the enrolled face image")
        return feature, encoded.tobytes()

    def recognize(self, frame: Any, faces: list[Detection]) -> list[IdentityMatch]:
        if not faces:
            return []
        with self._lock:
            self._load_recognizer()
            self._load_gallery()
            height, width = frame.shape[:2]
            matches: list[IdentityMatch] = []
            for face in faces:
                x1 = max(0, min(width, face.x1))
                y1 = max(0, min(height, face.y1))
                x2 = max(0, min(width, face.x2))
                y2 = max(0, min(height, face.y2))
                if x2 <= x1 or y2 <= y1:
                    matches.append(IdentityMatch(face, None, "Unknown", 0.0))
                    continue
                probe = self._feature(frame[y1:y2, x1:x2])
                best: tuple[str, str, float] | None = None
                for identity_id, display_name, reference in self._gallery or []:
                    similarity = float(np.dot(probe, reference))
                    if best is None or similarity > best[2]:
                        best = (identity_id, display_name, similarity)
                if best is not None and best[2] >= self.threshold:
                    matches.append(
                        IdentityMatch(face, best[0], best[1], best[2])
                    )
                else:
                    matches.append(
                        IdentityMatch(
                            face,
                            None,
                            "Unknown",
                            best[2] if best is not None else 0.0,
                        )
                    )
            return matches
