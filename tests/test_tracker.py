import unittest
from datetime import datetime, timedelta, timezone

from app.models import Detection
from app.tracker import CentroidTracker


class TrackerTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 2, tzinfo=timezone.utc)

    def test_preserves_identity_and_previous_centroid(self):
        tracker = CentroidTracker(max_distance=50)
        first = tracker.update([Detection(0, 0, 20, 20, 0.9)], self.now)[0]
        second = tracker.update(
            [Detection(10, 0, 30, 20, 0.9)], self.now + timedelta(seconds=1)
        )[0]
        self.assertEqual(first.id, second.id)
        self.assertEqual(second.previous_centroid, (10, 10))
        self.assertEqual(second.centroid, (20, 10))

    def test_expires_missed_track(self):
        tracker = CentroidTracker(max_missed_frames=0)
        first_id = tracker.update([Detection(0, 0, 20, 20, 0.9)], self.now)[0].id
        self.assertEqual(tracker.update([], self.now), [])
        replacement = tracker.update([Detection(0, 0, 20, 20, 0.9)], self.now)[0]
        self.assertNotEqual(replacement.id, first_id)

    def test_rejects_invalid_options(self):
        with self.assertRaises(ValueError):
            CentroidTracker(max_distance=0)
        with self.assertRaises(ValueError):
            CentroidTracker(max_missed_frames=-1)


if __name__ == "__main__":
    unittest.main()
