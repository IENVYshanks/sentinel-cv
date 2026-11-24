import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from app.alerts import AlertService
from app.database import AlertDatabase
from app.models import AlertEvent


class AlertServiceTests(unittest.TestCase):
    def test_record_sanitizes_filename_and_purge_clears_database_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = AlertDatabase(root / "alerts.db")
            service = AlertService(database, root / "evidence", retention_days=1)
            event = AlertEvent(
                camera_id="../front camera",
                rule_id="../restricted zone",
                rule_name="Restricted zone",
                rule_type="restricted_area",
                message="Detected",
                occurred_at=datetime.now(timezone.utc),
            )
            service.record(event, np.zeros((20, 20, 3), dtype=np.uint8))
            alert = database.list_alerts()[0]
            evidence_path = service.evidence_dir / alert["evidence_file"]
            self.assertTrue(evidence_path.is_file())
            self.assertNotIn("..", alert["evidence_file"])
            self.assertNotIn(" ", alert["evidence_file"])

            os.utime(evidence_path, (0, 0))
            self.assertEqual(service.purge_expired(), 1)
            self.assertFalse(evidence_path.exists())
            self.assertIsNone(database.list_alerts()[0]["evidence_file"])
            database.close()


if __name__ == "__main__":
    unittest.main()
