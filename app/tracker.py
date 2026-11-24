from __future__ import annotations

from datetime import datetime
from math import hypot

from app.models import Detection, Track


class CentroidTracker:
    def __init__(self, max_distance: float = 90.0, max_missed_frames: int = 12):
        if max_distance <= 0:
            raise ValueError("max_distance must be positive")
        if max_missed_frames < 0:
            raise ValueError("max_missed_frames must not be negative")
        self.max_distance = max_distance
        self.max_missed_frames = max_missed_frames
        self._tracks: dict[int, Track] = {}
        self._next_id = 1

    def update(self, detections: list[Detection], now: datetime) -> list[Track]:
        unmatched_track_ids = set(self._tracks)
        unmatched_detection_ids = set(range(len(detections)))
        candidates: list[tuple[float, int, int]] = []

        for track_id, track in self._tracks.items():
            tx, ty = track.centroid
            for detection_id, detection in enumerate(detections):
                dx, dy = detection.centroid
                distance = hypot(tx - dx, ty - dy)
                if distance <= self.max_distance:
                    candidates.append((distance, track_id, detection_id))

        for _, track_id, detection_id in sorted(candidates):
            if track_id not in unmatched_track_ids or detection_id not in unmatched_detection_ids:
                continue
            track = self._tracks[track_id]
            track.previous_centroid = track.centroid
            track.detection = detections[detection_id]
            track.last_seen = now
            track.missed_frames = 0
            unmatched_track_ids.remove(track_id)
            unmatched_detection_ids.remove(detection_id)

        for track_id in unmatched_track_ids:
            self._tracks[track_id].missed_frames += 1

        for detection_id in unmatched_detection_ids:
            detection = detections[detection_id]
            track = Track(
                id=self._next_id,
                detection=detection,
                first_seen=now,
                last_seen=now,
            )
            self._tracks[track.id] = track
            self._next_id += 1

        expired = [
            track_id
            for track_id, track in self._tracks.items()
            if track.missed_frames > self.max_missed_frames
        ]
        for track_id in expired:
            del self._tracks[track_id]

        return sorted(
            (track for track in self._tracks.values() if track.missed_frames == 0),
            key=lambda track: track.id,
        )

