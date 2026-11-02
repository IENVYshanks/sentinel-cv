import tempfile
import unittest
from pathlib import Path

from app.config import Settings, load_cameras, load_rule_config


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


if __name__ == "__main__":
    unittest.main()

