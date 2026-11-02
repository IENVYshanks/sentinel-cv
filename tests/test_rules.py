import unittest
from datetime import datetime, timezone

from app.models import Detection, Track
from app.rules import RuleEngine, point_in_polygon, schedule_is_active


class GeometryTests(unittest.TestCase):
    def test_point_in_polygon(self):
        square = [[0, 0], [100, 0], [100, 100], [0, 100]]
        self.assertTrue(point_in_polygon((50, 50), square))
        self.assertFalse(point_in_polygon((150, 50), square))


class ScheduleTests(unittest.TestCase):
    def test_overnight_schedule(self):
        schedule = {"days": ["mon"], "start": "22:00", "end": "06:00"}
        monday_late = datetime(2026, 11, 2, 23, 0, tzinfo=timezone.utc)
        tuesday_early = datetime(2026, 11, 3, 5, 0, tzinfo=timezone.utc)
        tuesday_late = datetime(2026, 11, 3, 23, 0, tzinfo=timezone.utc)
        self.assertTrue(schedule_is_active(schedule, monday_late))
        self.assertTrue(schedule_is_active(schedule, tuesday_early))
        self.assertFalse(schedule_is_active(schedule, tuesday_late))


class RuleEngineTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
        self.rule = {
            "id": "restricted",
            "camera_id": "cam-1",
            "type": "restricted_area",
            "name": "Restricted zone",
            "zone": [[0, 0], [100, 0], [100, 100], [0, 100]],
            "cooldown_seconds": 30,
        }

    def test_restricted_area_alert_and_cooldown(self):
        engine = RuleEngine([self.rule], "UTC")
        detection = Detection(20, 20, 60, 80, 0.9)
        track = Track(1, detection, self.now, self.now)
        first = engine.evaluate("cam-1", [track], self.now)
        second = engine.evaluate("cam-1", [track], self.now)
        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])

    def test_occupancy_alert(self):
        rule = dict(self.rule, id="occupancy", type="occupancy", max_people=1)
        engine = RuleEngine([rule], "UTC")
        tracks = [
            Track(i, Detection(10 * i, 10, 10 * i + 10, 30, 0.9), self.now, self.now)
            for i in (1, 2)
        ]
        alerts = engine.evaluate("cam-1", tracks, self.now)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].metadata["occupancy"], 2)

    def test_line_crossing_alert(self):
        rule = {
            "id": "line",
            "camera_id": "cam-1",
            "type": "line_crossing",
            "name": "Direction line",
            "line": [[0, 50], [100, 50]],
            "direction": "a_to_b",
        }
        engine = RuleEngine([rule], "UTC")
        track = Track(
            1,
            Detection(40, 50, 60, 70, 0.9),
            self.now,
            self.now,
            previous_centroid=(50, 40),
        )
        alerts = engine.evaluate("cam-1", [track], self.now)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].metadata["direction"], "a_to_b")


if __name__ == "__main__":
    unittest.main()

