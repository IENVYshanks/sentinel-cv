import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import numpy as np

from app.camera import CameraWorker
from app.identity import IdentityRecognizer
from app.models import Detection, IdentityMatch, Track


class FakeRecognizer:
    def feature(self, image):
        if float(image[..., 0].mean()) > 100:
            return np.array([[1.0, 0.0]], dtype=np.float32)
        return np.array([[0.0, 1.0]], dtype=np.float32)


class FakeDatabase:
    def list_identity_embeddings(self):
        embedding = np.array([1.0, 0.0], dtype=np.float32)
        return [
            {
                "identity_id": "database-person",
                "display_name": "Database Person",
                "embedding": embedding.tobytes(),
                "embedding_dimensions": embedding.size,
            }
        ]


class IdentityRecognizerTests(unittest.TestCase):
    def recognizer(self, threshold=0.45):
        recognizer = IdentityRecognizer("unused.onnx", [], threshold)
        recognizer._recognizer = FakeRecognizer()
        recognizer._gallery = [
            ("person-1", "Test Person", np.array([1.0, 0.0], dtype=np.float32))
        ]
        return recognizer

    def test_matches_enrolled_identity(self):
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        frame[10:50, 20:60, 0] = 255
        face = Detection(20, 10, 60, 50, 0.9)

        match = self.recognizer().recognize(frame, [face])[0]

        self.assertTrue(match.known)
        self.assertEqual(match.identity_id, "person-1")
        self.assertEqual(match.display_name, "Test Person")
        self.assertAlmostEqual(match.confidence, 1.0)

    def test_labels_below_threshold_as_unknown(self):
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        face = Detection(20, 10, 60, 50, 0.9)

        match = self.recognizer().recognize(frame, [face])[0]

        self.assertFalse(match.known)
        self.assertEqual(match.display_name, "Unknown")
        self.assertAlmostEqual(match.confidence, 0.0)

    def test_ignores_invalid_face_crop(self):
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        face = Detection(120, 10, 130, 50, 0.9)

        match = self.recognizer().recognize(frame, [face])[0]

        self.assertFalse(match.known)
        self.assertEqual(match.confidence, 0.0)

    def test_associates_known_face_with_containing_track(self):
        now = datetime.now(timezone.utc)
        track = Track(7, Detection(10, 10, 90, 100, 0.9), now, now)
        face = Detection(30, 20, 60, 55, 0.95)
        match = IdentityMatch(face, "person-1", "Test Person", 0.88)

        associations = CameraWorker._associate_identities([track], [match])

        self.assertIs(associations[track.id], match)
        self.assertEqual(track.identity_id, "person-1")
        self.assertEqual(track.identity_name, "Test Person")
        self.assertAlmostEqual(track.identity_confidence, 0.88)

    def test_unknown_face_maps_to_person_without_persisting_identity(self):
        now = datetime.now(timezone.utc)
        track = Track(3, Detection(10, 10, 90, 100, 0.9), now, now)
        face = Detection(30, 20, 60, 55, 0.95)
        match = IdentityMatch(face, None, "Unknown", 0.2)

        associations = CameraWorker._associate_identities([track], [match])

        self.assertIs(associations[track.id], match)
        self.assertIsNone(track.identity_id)
        self.assertIsNone(track.identity_name)

    def test_prefers_one_face_box_for_one_track(self):
        now = datetime.now(timezone.utc)
        track = Track(3, Detection(10, 10, 90, 100, 0.9), now, now)
        face = Detection(30, 20, 60, 55, 0.95)
        match = IdentityMatch(face, None, "Unknown", 0.2)

        with patch("app.camera.cv2.rectangle") as rectangle, patch(
            "app.camera.cv2.putText"
        ) as put_text:
            CameraWorker.draw_individual_boxes(
                np.zeros((120, 120, 3), dtype=np.uint8),
                [track],
                {track.id: match},
            )

        self.assertEqual(rectangle.call_count, 1)
        self.assertEqual(put_text.call_count, 1)
        self.assertEqual(rectangle.call_args.args[1], (face.x1, face.y1))
        self.assertEqual(rectangle.call_args.args[2], (face.x2, face.y2))
        self.assertIn("Unknown", put_text.call_args.args[1])

    def test_falls_back_to_one_person_box_without_face(self):
        now = datetime.now(timezone.utc)
        detection = Detection(10, 10, 90, 100, 0.9)
        track = Track(3, detection, now, now)

        with patch("app.camera.cv2.rectangle") as rectangle, patch(
            "app.camera.cv2.putText"
        ) as put_text:
            CameraWorker.draw_individual_boxes(
                np.zeros((120, 120, 3), dtype=np.uint8), [track], {}
            )

        self.assertEqual(rectangle.call_count, 1)
        self.assertEqual(rectangle.call_args.args[1], (detection.x1, detection.y1))
        self.assertEqual(rectangle.call_args.args[2], (detection.x2, detection.y2))
        self.assertIn("Person", put_text.call_args.args[1])

    def test_loads_identity_embedding_from_database(self):
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        frame[10:50, 20:60, 0] = 255
        face = Detection(20, 10, 60, 50, 0.9)
        recognizer = IdentityRecognizer(
            "unused.onnx", [], database=FakeDatabase()
        )
        recognizer._recognizer = FakeRecognizer()

        match = recognizer.recognize(frame, [face])[0]

        self.assertEqual(match.identity_id, "database-person")
        self.assertEqual(match.display_name, "Database Person")

    def test_reload_gallery_discards_cached_embeddings(self):
        recognizer = self.recognizer()
        self.assertIsNotNone(recognizer._gallery)

        recognizer.reload_gallery()

        self.assertIsNone(recognizer._gallery)


if __name__ == "__main__":
    unittest.main()
