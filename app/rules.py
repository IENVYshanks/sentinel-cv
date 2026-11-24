from __future__ import annotations

from collections import defaultdict
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from app.models import AlertEvent, Track


DAY_NAMES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
SUPPORTED_RULES = {"restricted_area", "loitering", "occupancy", "line_crossing"}


def point_in_polygon(point: tuple[int, int], polygon: list[list[int]]) -> bool:
    """Return True when point is inside polygon, using ray casting."""
    if len(polygon) < 3:
        return False
    x, y = point
    inside = False
    previous = len(polygon) - 1
    for current in range(len(polygon)):
        xi, yi = polygon[current]
        xj, yj = polygon[previous]
        if (yi > y) != (yj > y):
            crossing_x = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < crossing_x:
                inside = not inside
        previous = current
    return inside


def _parse_clock(value: str) -> time:
    try:
        parts = value.split(":")
        if len(parts) != 2 or any(len(part) != 2 for part in parts):
            raise ValueError
        hour, minute = (int(part) for part in parts)
        return time(hour=hour, minute=minute)
    except ValueError as exc:
        raise ValueError(f"Invalid clock value {value!r}; expected HH:MM") from exc


def schedule_is_active(schedule: dict[str, Any] | None, now: datetime) -> bool:
    if not schedule:
        return True
    days = [str(day).lower()[:3] for day in schedule.get("days", DAY_NAMES)]
    current_clock = now.timetz().replace(tzinfo=None)
    start = _parse_clock(str(schedule.get("start", "00:00")))
    end = _parse_clock(str(schedule.get("end", "23:59")))

    if start <= end:
        return DAY_NAMES[now.weekday()] in days and start <= current_clock <= end

    # For an overnight window, early-morning time belongs to the previous day.
    if current_clock >= start:
        return DAY_NAMES[now.weekday()] in days
    previous_day = DAY_NAMES[(now.weekday() - 1) % 7]
    return current_clock <= end and previous_day in days


class RuleEngine:
    def __init__(self, rules: list[dict[str, Any]], timezone: str = "UTC"):
        self.timezone = ZoneInfo(timezone)
        self.rules_by_camera: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._last_alert: dict[tuple[str, int | None], datetime] = {}
        self._validate_rules(rules)
        for rule in rules:
            if rule.get("enabled", True):
                self.rules_by_camera[str(rule["camera_id"])].append(rule)

    @staticmethod
    def _validate_rules(rules: list[dict[str, Any]]) -> None:
        seen: set[str] = set()
        for rule in rules:
            required = {"id", "camera_id", "type", "name"}
            if not isinstance(rule, dict) or not required.issubset(rule):
                raise ValueError(f"Invalid rule; required fields: {sorted(required)}")
            rule_id = str(rule["id"]).strip()
            if not rule_id or not str(rule["camera_id"]).strip() or not str(rule["name"]).strip():
                raise ValueError("Rule id, camera_id, and name must not be empty")
            if rule_id in seen:
                raise ValueError(f"Duplicate rule id: {rule_id}")
            seen.add(rule_id)
            if rule["type"] not in SUPPORTED_RULES:
                raise ValueError(f"Unsupported rule type: {rule['type']}")
            cooldown = float(rule.get("cooldown_seconds", 30))
            confidence = float(rule.get("minimum_confidence", 0.0))
            if cooldown < 0:
                raise ValueError(f"Rule {rule_id} cooldown_seconds must not be negative")
            if not 0 <= confidence <= 1:
                raise ValueError(f"Rule {rule_id} minimum_confidence must be between 0 and 1")
            schedule = rule.get("schedule")
            if schedule is not None:
                if not isinstance(schedule, dict):
                    raise ValueError(f"Rule {rule_id} schedule must be a mapping")
                raw_days = schedule.get("days", DAY_NAMES)
                if not isinstance(raw_days, (list, tuple)) or not raw_days:
                    raise ValueError(f"Rule {rule_id} schedule days must be a non-empty list")
                days = [str(day).lower()[:3] for day in raw_days]
                invalid_days = sorted(set(days) - set(DAY_NAMES))
                if invalid_days:
                    raise ValueError(f"Rule {rule_id} has invalid schedule days: {invalid_days}")
                _parse_clock(str(schedule.get("start", "00:00")))
                _parse_clock(str(schedule.get("end", "23:59")))
            if rule["type"] == "line_crossing":
                line = rule.get("line")
                if not RuleEngine._valid_points(line, 2):
                    raise ValueError(f"Rule {rule['id']} requires exactly 2 line points")
                if line[0] == line[1]:
                    raise ValueError(f"Rule {rule_id} line points must be different")
                direction = rule.get("direction", "any")
                if direction not in {"any", "a_to_b", "b_to_a"}:
                    raise ValueError(f"Rule {rule['id']} has an invalid direction")
            else:
                zone = rule.get("zone")
                if not RuleEngine._valid_points(zone, 3, at_least=True):
                    raise ValueError(f"Rule {rule['id']} requires a polygon with at least 3 points")
            if rule["type"] == "loitering" and float(rule.get("threshold_seconds", 30)) < 0:
                raise ValueError(f"Rule {rule_id} threshold_seconds must not be negative")
            if rule["type"] == "occupancy" and int(rule.get("max_people", 1)) < 0:
                raise ValueError(f"Rule {rule_id} max_people must not be negative")

    @staticmethod
    def _valid_points(value: Any, count: int, at_least: bool = False) -> bool:
        if not isinstance(value, list) or (len(value) < count if at_least else len(value) != count):
            return False
        return all(
            isinstance(point, list)
            and len(point) == 2
            and all(isinstance(coordinate, (int, float)) and not isinstance(coordinate, bool) for coordinate in point)
            for point in value
        )

    def rules_for_camera(self, camera_id: str) -> list[dict[str, Any]]:
        return self.rules_by_camera.get(camera_id, [])

    def evaluate(
        self, camera_id: str, tracks: list[Track], now: datetime
    ) -> list[AlertEvent]:
        local_now = now.astimezone(self.timezone)
        events: list[AlertEvent] = []
        for rule in self.rules_for_camera(camera_id):
            rule_id = str(rule["id"])
            rule_type = str(rule["type"])
            if not schedule_is_active(rule.get("schedule"), local_now):
                continue
            if rule_type == "line_crossing":
                for track in tracks:
                    if track.detection.confidence < float(rule.get("minimum_confidence", 0.0)):
                        continue
                    crossing_direction = self._crossing_direction(track, rule["line"])
                    wanted_direction = str(rule.get("direction", "any"))
                    if crossing_direction and wanted_direction in {"any", crossing_direction}:
                        events.extend(
                            self._track_event(
                                rule,
                                track,
                                local_now,
                                f"Person crossed line ({crossing_direction})",
                                {"direction": crossing_direction},
                            )
                        )
                continue

            tracks_inside = [
                track
                for track in tracks
                if point_in_polygon(track.centroid, rule["zone"])
                and track.detection.confidence >= float(rule.get("minimum_confidence", 0.0))
            ]
            inside_ids = {track.id for track in tracks_inside}
            for track in tracks:
                if track.id not in inside_ids:
                    track.zone_entered_at.pop(rule_id, None)

            if rule_type == "restricted_area":
                for track in tracks_inside:
                    events.extend(self._track_event(rule, track, local_now, "Person in restricted area"))
            elif rule_type == "loitering":
                threshold = float(rule.get("threshold_seconds", 30))
                for track in tracks_inside:
                    entered = track.zone_entered_at.setdefault(rule_id, local_now)
                    duration = (local_now - entered).total_seconds()
                    if duration >= threshold:
                        events.extend(
                            self._track_event(
                                rule,
                                track,
                                local_now,
                                f"Person loitering for {int(duration)} seconds",
                                {"duration_seconds": int(duration)},
                            )
                        )
            elif rule_type == "occupancy":
                maximum = int(rule.get("max_people", 1))
                if len(tracks_inside) > maximum and self._cooldown_ready(rule, None, local_now):
                    events.append(
                        self._event(
                            rule,
                            local_now,
                            f"Occupancy {len(tracks_inside)} exceeds limit {maximum}",
                            metadata={"occupancy": len(tracks_inside), "maximum": maximum},
                        )
                    )
        return events

    @staticmethod
    def _crossing_direction(track: Track, line: list[list[int]]) -> str | None:
        if track.previous_centroid is None:
            return None
        (x1, y1), (x2, y2) = line

        def side(point: tuple[int, int]) -> float:
            x, y = point
            return (x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)

        previous_side = side(track.previous_centroid)
        current_side = side(track.centroid)
        if previous_side == 0 or current_side == 0 or previous_side * current_side >= 0:
            return None

        # Crossing the infinite line is insufficient: the movement must intersect
        # the configured finite segment as well.
        px, py = track.previous_centroid
        cx, cy = track.centroid

        def movement_side(point: list[int]) -> float:
            x, y = point
            return (cx - px) * (y - py) - (cy - py) * (x - px)

        first_endpoint = movement_side(line[0])
        second_endpoint = movement_side(line[1])
        if first_endpoint * second_endpoint > 0:
            return None
        return "a_to_b" if previous_side < 0 < current_side else "b_to_a"

    def _track_event(
        self,
        rule: dict[str, Any],
        track: Track,
        now: datetime,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> list[AlertEvent]:
        if not self._cooldown_ready(rule, track.id, now):
            return []
        return [
            self._event(
                rule,
                now,
                message,
                track_id=track.id,
                confidence=track.detection.confidence,
                metadata=metadata,
            )
        ]

    def _cooldown_ready(
        self, rule: dict[str, Any], track_id: int | None, now: datetime
    ) -> bool:
        key = (str(rule["id"]), track_id)
        cooldown = float(rule.get("cooldown_seconds", 30))
        previous = self._last_alert.get(key)
        if previous and (now - previous).total_seconds() < cooldown:
            return False
        self._last_alert[key] = now
        return True

    @staticmethod
    def _event(
        rule: dict[str, Any],
        now: datetime,
        message: str,
        track_id: int | None = None,
        confidence: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AlertEvent:
        return AlertEvent(
            camera_id=str(rule["camera_id"]),
            rule_id=str(rule["id"]),
            rule_name=str(rule["name"]),
            rule_type=str(rule["type"]),
            message=message,
            occurred_at=now,
            track_id=track_id,
            confidence=confidence,
            metadata=metadata or {},
        )

