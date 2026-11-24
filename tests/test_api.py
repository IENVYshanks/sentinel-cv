import base64
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import cv2
from fastapi.testclient import TestClient

from app.config import Settings
from app.detector import PersonDetector
from app.main import create_app
from app.models import AlertEvent, Detection


class FakeFaceDetector:
    def detect(self, image):
        height, width = image.shape[:2]
        return [Detection(0, 0, width, height, 0.99)]


class FakeIdentityRecognizer:
    def __init__(self):
        self.reloads = 0

    def extract_embedding(self, image, face):
        return np.array([1.0, 0.0], dtype=np.float32), b"cropped-face"

    def reload_gallery(self):
        self.reloads += 1


class FakeVideoJob:
    id = "video-job"

    def status(self):
        return {
            "id": self.id,
            "filename": "test.mp4",
            "state": "queued",
            "error": None,
            "frames_processed": 0,
            "total_frames": 0,
            "progress": 0.0,
            "recognized_identities": [],
        }


class ApiTests(unittest.TestCase):
    def test_health_alerts_static_page_and_not_found_routes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cameras = root / "cameras.yaml"
            rules = root / "rules.yaml"
            cameras.write_text(
                "cameras:\n"
                "  - id: cam\n"
                "    name: Camera\n"
                "    source: 0\n"
                "    face_detection: true\n",
                encoding="utf-8",
            )
            rules.write_text("timezone: UTC\nrules: []\n", encoding="utf-8")
            settings = Settings(
                cameras_config=cameras,
                rules_config=rules,
                database_path=root / "data" / "alerts.db",
                evidence_dir=root / "evidence",
                detector_model="unused.pt",
                host="127.0.0.1",
                port=8000,
            )
            app = create_app(start_cameras=False, settings=settings)

            with TestClient(app) as client:
                health = client.get("/api/health")
                self.assertEqual(health.status_code, 200)
                self.assertEqual(
                    health.json(),
                    {"status": "ok", "mode": "live", "cameras": 1, "connected": 0},
                )

                system = client.get("/api/system")
                self.assertEqual(system.status_code, 200)
                self.assertEqual(system.json()["mode"], "live")
                self.assertEqual(system.json()["configured_cameras"], 1)
                self.assertIn("identity_threshold", system.json())

                camera_status = client.get("/api/cameras")
                self.assertEqual(camera_status.status_code, 200)
                self.assertTrue(camera_status.json()[0]["face_detection_enabled"])
                self.assertEqual(camera_status.json()[0]["faces_detected"], 0)
                self.assertFalse(
                    camera_status.json()[0]["identity_detection_enabled"]
                )
                self.assertEqual(
                    camera_status.json()[0]["recognized_identities"], []
                )

                app.state.database.add_alert(
                    AlertEvent(
                        "cam",
                        "rule",
                        "Rule",
                        "restricted_area",
                        "Detected",
                        datetime.now(timezone.utc),
                    ),
                    None,
                )
                alerts = client.get("/api/alerts?limit=1")
                self.assertEqual(alerts.status_code, 200)
                self.assertEqual(alerts.json()[0]["rule_id"], "rule")
                for path, marker in {
                    "/": "Overview",
                    "/cameras": "Cameras",
                    "/video-test": "Video Test",
                    "/identities": "Identities",
                    "/alerts": "Alerts",
                    "/settings": "System",
                    "/about": "About Sentinel CV",
                }.items():
                    page = client.get(path)
                    self.assertEqual(page.status_code, 200)
                    self.assertIn(marker, page.text)
                    self.assertIn("styles.css?v=20261124-3", page.text)
                    self.assertIn("app.js?v=20261124-3", page.text)
                    self.assertIn('href="/about"', page.text)
                    self.assertIn('href="/video-test"', page.text)

                stylesheet = client.get("/static/styles.css?v=20261124-3")
                self.assertEqual(stylesheet.status_code, 200)
                self.assertIn(".app-shell", stylesheet.text)
                self.assertEqual(
                    stylesheet.headers["cache-control"],
                    "no-cache, no-store, must-revalidate",
                )
                self.assertEqual(stylesheet.headers["pragma"], "no-cache")
                self.assertEqual(client.get("/api/cameras/missing/stream").status_code, 404)
                self.assertEqual(client.get("/api/evidence/missing.jpg").status_code, 404)

                app.state.video_tests.create = lambda filename, path: FakeVideoJob()
                video = client.post(
                    "/api/video-tests?filename=test.mp4",
                    content=b"fake-video",
                    headers={"Content-Type": "application/octet-stream"},
                )
                self.assertEqual(video.status_code, 201)
                self.assertEqual(video.json()["id"], "video-job")
                invalid_video = client.post(
                    "/api/video-tests?filename=test.txt", content=b"not-video"
                )
                self.assertEqual(invalid_video.status_code, 400)

    def test_demo_detector_finds_generated_silhouettes(self):
        frame = np.zeros((200, 300, 3), dtype=np.uint8)
        frame[30:160, 40:90] = (40, 240, 40)
        frame[50:180, 180:230] = (40, 240, 40)
        detections = PersonDetector("demo").detect(frame)
        self.assertEqual(len(detections), 2)
        self.assertTrue(all(detection.confidence == 0.99 for detection in detections))

    def test_identity_management_api(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cameras = root / "cameras.yaml"
            rules = root / "rules.yaml"
            cameras.write_text("cameras: []\n", encoding="utf-8")
            rules.write_text("timezone: UTC\nrules: []\n", encoding="utf-8")
            settings = Settings(
                cameras_config=cameras,
                rules_config=rules,
                database_path=root / "data" / "alerts.db",
                evidence_dir=root / "evidence",
                detector_model="unused.pt",
                host="127.0.0.1",
                port=8000,
            )
            app = create_app(start_cameras=False, settings=settings)
            fake_recognizer = FakeIdentityRecognizer()
            app.state.face_detector = FakeFaceDetector()
            app.state.identity_recognizer = fake_recognizer
            source = np.full((20, 20, 3), 120, dtype=np.uint8)
            success, encoded = cv2.imencode(".jpg", source)
            self.assertTrue(success)
            image_base64 = base64.b64encode(encoded.tobytes()).decode("ascii")

            with TestClient(app) as client:
                created = client.post(
                    "/api/identities",
                    json={
                        "identity_id": "person-1",
                        "display_name": "Test Person",
                        "image_base64": image_base64,
                    },
                )
                self.assertEqual(created.status_code, 201)
                self.assertEqual(fake_recognizer.reloads, 1)

                identities = client.get("/api/identities")
                self.assertEqual(identities.status_code, 200)
                self.assertEqual(identities.json()[0]["identity_id"], "person-1")
                self.assertNotIn("embedding", identities.json()[0])

                image = client.get("/api/identities/person-1/image")
                self.assertEqual(image.status_code, 200)
                self.assertEqual(image.content, b"cropped-face")
                self.assertEqual(image.headers["content-type"], "image/jpeg")

                renamed = client.patch(
                    "/api/identities/person-1",
                    json={"display_name": "Renamed Person"},
                )
                self.assertEqual(renamed.status_code, 200)
                self.assertEqual(renamed.json()["display_name"], "Renamed Person")
                self.assertEqual(fake_recognizer.reloads, 2)

                deleted = client.delete("/api/identities/person-1")
                self.assertEqual(deleted.status_code, 204)
                self.assertEqual(fake_recognizer.reloads, 3)
                self.assertEqual(
                    client.get("/api/identities/person-1/image").status_code, 404
                )
                self.assertEqual(
                    client.delete("/api/identities/person-1").status_code, 404
                )


if __name__ == "__main__":
    unittest.main()
