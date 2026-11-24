import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.database import AlertDatabase
from app.models import AlertEvent


class DatabaseTests(unittest.TestCase):
    def test_add_list_and_clear_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            database = AlertDatabase(Path(directory) / "alerts.db")
            event = AlertEvent(
                camera_id="cam",
                rule_id="rule",
                rule_name="Rule",
                rule_type="restricted_area",
                message="Detected",
                occurred_at=datetime(2026, 11, 2, tzinfo=timezone.utc),
                track_id=4,
                confidence=0.9,
                metadata={"source": "test"},
            )
            alert_id = database.add_alert(event, "evidence.jpg")
            alerts = database.list_alerts()
            self.assertEqual(alerts[0]["id"], alert_id)
            self.assertEqual(alerts[0]["metadata"], {"source": "test"})

            database.clear_evidence_file("evidence.jpg")
            self.assertIsNone(database.list_alerts()[0]["evidence_file"])
            database.close()
            database.close()

    def test_limit_is_bounded_to_at_least_one(self):
        with tempfile.TemporaryDirectory() as directory:
            database = AlertDatabase(Path(directory) / "alerts.db")
            event = AlertEvent(
                "cam", "rule", "Rule", "occupancy", "Detected", datetime.now(timezone.utc)
            )
            database.add_alert(event, None)
            self.assertEqual(len(database.list_alerts(0)), 1)
            database.close()

    def test_upserts_and_reads_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            database = AlertDatabase(Path(directory) / "alerts.db")
            database.upsert_identity(
                "owner", "Owner", b"jpeg-data", b"embedding-data", 4
            )
            database.upsert_identity(
                "owner", "Updated Owner", b"new-jpeg", b"new-embedding", 8
            )

            identity = database.get_identity("owner")
            embeddings = database.list_identity_embeddings()

            self.assertIsNotNone(identity)
            self.assertEqual(identity["display_name"], "Updated Owner")
            self.assertEqual(identity["face_image"], b"new-jpeg")
            self.assertEqual(len(embeddings), 1)
            self.assertEqual(embeddings[0]["embedding"], b"new-embedding")
            self.assertEqual(embeddings[0]["embedding_dimensions"], 8)

            identities = database.list_identities()
            self.assertEqual(identities[0]["identity_id"], "owner")
            self.assertNotIn("embedding", identities[0])
            self.assertTrue(database.rename_identity("owner", "Renamed Owner"))
            self.assertEqual(
                database.get_identity("owner")["display_name"], "Renamed Owner"
            )
            self.assertFalse(database.rename_identity("missing", "Missing"))
            self.assertTrue(database.delete_identity("owner"))
            self.assertIsNone(database.get_identity("owner"))
            self.assertFalse(database.delete_identity("owner"))
            database.close()


if __name__ == "__main__":
    unittest.main()
