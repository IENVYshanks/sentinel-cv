import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from app.config import (
    Settings,
    load_cameras,
    load_identities,
    load_rule_config,
    load_settings,
)


class ConfigTests(unittest.TestCase):
    def settings(self, root: Path) -> Settings:
        return Settings(
            cameras_config=root / "cameras.yaml",
            rules_config=root / "rules.yaml",
            database_path=root / "alerts.db",
            evidence_dir=root / "evidence",
            detector_model="model.pt",
            host="127.0.0.1",
            port=8000,
        )

    def test_loads_valid_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "cameras.yaml").write_text(
                "cameras:\n  - id: cam\n    name: Camera\n    source: 0\n", encoding="utf-8"
            )
            (root / "rules.yaml").write_text("timezone: UTC\nrules: []\n", encoding="utf-8")
            settings = self.settings(root)
            self.assertEqual(load_cameras(settings)[0]["id"], "cam")
            self.assertEqual(load_rule_config(settings)["timezone"], "UTC")

    def test_rejects_invalid_camera(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "cameras.yaml").write_text("cameras:\n  - id: incomplete\n", encoding="utf-8")
            (root / "rules.yaml").write_text("rules: []\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_cameras(self.settings(root))

    def test_loads_face_detection_options(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "cameras.yaml").write_text(
                "cameras:\n"
                "  - id: cam\n"
                "    name: Camera\n"
                "    source: 0\n"
                "    face_detection: true\n"
                "    face_process_every_n_frames: 3\n",
                encoding="utf-8",
            )
            (root / "rules.yaml").write_text("rules: []\n", encoding="utf-8")
            camera = load_cameras(self.settings(root))[0]
            self.assertTrue(camera["face_detection"])
            self.assertEqual(camera["face_process_every_n_frames"], 3)

    def test_rejects_invalid_face_detection_options(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "cameras.yaml").write_text(
                "cameras:\n"
                "  - id: cam\n"
                "    name: Camera\n"
                "    source: 0\n"
                "    face_detection: yes-please\n",
                encoding="utf-8",
            )
            (root / "rules.yaml").write_text("rules: []\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "face_detection"):
                load_cameras(self.settings(root))

    def test_identity_detection_requires_face_detection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "cameras.yaml").write_text(
                "cameras:\n"
                "  - id: cam\n"
                "    name: Camera\n"
                "    source: 0\n"
                "    identity_detection: true\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "requires face_detection"):
                load_cameras(self.settings(root))

    def test_loads_identity_gallery_and_resolves_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = self.settings(root)
            identity_config = root / "identities.yaml"
            identity_config.write_text(
                "identities:\n"
                "  - id: person-1\n"
                "    name: Test Person\n"
                "    images: [portraits/person.jpg]\n",
                encoding="utf-8",
            )
            settings = Settings(
                cameras_config=settings.cameras_config,
                rules_config=settings.rules_config,
                database_path=settings.database_path,
                evidence_dir=settings.evidence_dir,
                detector_model=settings.detector_model,
                host=settings.host,
                port=settings.port,
                identity_config=identity_config,
            )

            identities = load_identities(settings)

            self.assertEqual(identities[0]["id"], "person-1")
            self.assertEqual(
                identities[0]["images"], [(root / "portraits/person.jpg").resolve()]
            )

    def test_rejects_duplicate_camera_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "cameras.yaml").write_text(
                "cameras:\n  - {id: cam, name: One, source: 0}\n"
                "  - {id: cam, name: Two, source: 1}\n",
                encoding="utf-8",
            )
            (root / "rules.yaml").write_text("rules: []\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate camera id"):
                load_cameras(self.settings(root))

    def test_rejects_unknown_timezone(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "cameras.yaml").write_text("cameras: []\n", encoding="utf-8")
            (root / "rules.yaml").write_text(
                "timezone: Not/A_Real_Zone\nrules: []\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "Unknown timezone"):
                load_rule_config(self.settings(root))

    def test_rejects_invalid_environment_port(self):
        with patch.dict("os.environ", {"SENTINEL_PORT": "70000"}, clear=False):
            with self.assertRaisesRegex(ValueError, "between 1 and 65535"):
                load_settings()

    def test_rejects_invalid_face_confidence(self):
        with patch.dict(
            "os.environ", {"SENTINEL_FACE_DETECTOR_CONFIDENCE": "1.5"}, clear=False
        ):
            with self.assertRaisesRegex(ValueError, "FACE_DETECTOR_CONFIDENCE"):
                load_settings()

    def test_rejects_invalid_identity_threshold(self):
        with patch.dict(
            "os.environ", {"SENTINEL_IDENTITY_THRESHOLD": "2"}, clear=False
        ):
            with self.assertRaisesRegex(ValueError, "IDENTITY_THRESHOLD"):
                load_settings()


if __name__ == "__main__":
    unittest.main()

