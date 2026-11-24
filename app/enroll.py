from __future__ import annotations

import argparse
from pathlib import Path

import cv2

from app.config import load_settings
from app.database import AlertDatabase
from app.detector import FaceDetector
from app.identity import IdentityRecognizer


def enroll(identity_id: str, display_name: str, image_path: Path) -> None:
    settings = load_settings()
    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(f"Enrollment image could not be read: {image_path}")

    face_detector = FaceDetector(
        settings.face_detector_model, settings.face_detector_confidence
    )
    faces = face_detector.detect(image)
    if len(faces) != 1:
        raise ValueError(
            f"Enrollment requires exactly one detected face; found {len(faces)}"
        )

    recognizer = IdentityRecognizer(settings.identity_model, [])
    embedding, face_image = recognizer.extract_embedding(image, faces[0])
    database = AlertDatabase(settings.database_path)
    try:
        database.upsert_identity(
            identity_id,
            display_name,
            face_image,
            embedding.astype("float32").tobytes(),
            int(embedding.size),
        )
    finally:
        database.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enroll one consented face into the local Sentinel CV database."
    )
    parser.add_argument("--id", required=True, dest="identity_id")
    parser.add_argument("--name", required=True, dest="display_name")
    parser.add_argument("--image", required=True, type=Path, dest="image_path")
    arguments = parser.parse_args()
    enroll(arguments.identity_id, arguments.display_name, arguments.image_path)
    print(
        f"Enrolled {arguments.display_name!r} as {arguments.identity_id!r} "
        f"from {arguments.image_path}"
    )


if __name__ == "__main__":
    main()
