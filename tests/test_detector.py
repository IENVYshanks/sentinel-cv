import unittest
from types import SimpleNamespace

import numpy as np

from app.detector import FaceDetector


class FakeFaceModel:
    def __init__(self):
        self.options = None

    def predict(self, **options):
        self.options = options
        box = SimpleNamespace(
            xyxy=np.array([[10.8, 20.2, 50.9, 70.7]]),
            conf=np.array([0.87]),
        )
        return [SimpleNamespace(boxes=[box])]


class FaceDetectorTests(unittest.TestCase):
    def test_converts_yolo_face_result_to_detection(self):
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        model = FakeFaceModel()
        detector = FaceDetector("unused.pt", confidence=0.55)
        detector._model = model

        detections = detector.detect(frame)

        self.assertEqual(len(detections), 1)
        self.assertEqual((detections[0].x1, detections[0].y1), (10, 20))
        self.assertEqual((detections[0].x2, detections[0].y2), (50, 70))
        self.assertAlmostEqual(detections[0].confidence, 0.87, places=5)
        self.assertIs(model.options["source"], frame)
        self.assertEqual(model.options["conf"], 0.55)
        self.assertFalse(model.options["verbose"])


if __name__ == "__main__":
    unittest.main()
