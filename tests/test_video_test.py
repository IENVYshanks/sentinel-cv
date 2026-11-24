import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from app.models import Detection, IdentityMatch
from app.video_test import VideoTestWorker, video_test_stream


class FakeCapture:
    def __init__(self, path):
        self.frames = [
            np.zeros((120, 160, 3), dtype=np.uint8),
            np.zeros((120, 160, 3), dtype=np.uint8),
        ]

    def isOpened(self):
        return True

    def get(self, property_id):
        return 2

    def read(self):
        if self.frames:
            return True, self.frames.pop(0)
        return False, None

    def release(self):
        return None


class FakePersonDetector:
    def detect(self, frame):
        return [Detection(20, 10, 120, 115, 0.9)]


class FakeFaceDetector:
    def detect(self, frame):
        return [Detection(45, 20, 80, 60, 0.95)]


class FakeIdentityRecognizer:
    def recognize(self, frame, faces):
        return [IdentityMatch(faces[0], "owner", "Owner", 0.91)]


class VideoTestTests(unittest.TestCase):
    def test_processes_video_and_removes_upload(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.mp4"
            path.write_bytes(b"placeholder")
            worker = VideoTestWorker(
                "job",
                "test.mp4",
                path,
                FakePersonDetector(),
                FakeFaceDetector(),
                FakeIdentityRecognizer(),
            )
            with patch("app.video_test.cv2.VideoCapture", FakeCapture):
                worker.start()
                worker._thread.join(timeout=3)

            status = worker.status()
            self.assertEqual(status["state"], "completed")
            self.assertEqual(status["frames_processed"], 2)
            self.assertEqual(status["progress"], 100.0)
            self.assertEqual(status["recognized_identities"], ["Owner"])
            self.assertIsNotNone(worker.latest_jpeg())
            self.assertFalse(path.exists())

            chunks = list(video_test_stream(worker))
            self.assertEqual(len(chunks), 1)
            self.assertIn(b"Content-Type: image/jpeg", chunks[0])


if __name__ == "__main__":
    unittest.main()
