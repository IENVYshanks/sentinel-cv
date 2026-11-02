# Sentinel CV

Sentinel CV is a local, multi-camera computer-vision service that detects people and creates alerts when configurable safety rules are triggered. It supports webcams, USB cameras, RTSP streams, and video files.

The default design deliberately avoids facial recognition and identity inference. It tracks anonymous objects only for the lifetime of a camera session.

## Features

- YOLO person detection
- Anonymous centroid tracking
- Polygon restricted-area rules with schedules
- Loitering and occupancy rules
- Per-rule cooldowns to reduce duplicate alerts
- SQLite alert history and evidence snapshots
- FastAPI API, live MJPEG previews, and browser dashboard
- Configurable evidence retention

## Setup

Python 3.10 or newer is recommended.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item config\cameras.example.yaml config\cameras.yaml
Copy-Item config\rules.example.yaml config\rules.yaml
```

Edit `config/cameras.yaml`. A numeric source such as `0` selects a local camera. An RTSP URL, HTTP stream URL, or video path can be used instead.

Edit `config/rules.yaml`. Zone points use source-frame pixel coordinates in `[x, y]` form.

## Run

```powershell
python -m app.main
```

Open <http://127.0.0.1:8000>.

The first run may download the configured YOLO model. Set `SENTINEL_DETECTOR_MODEL` to a local model path for an offline deployment.

## Configuration

Environment variables can override common settings:

- `SENTINEL_CAMERAS_CONFIG`
- `SENTINEL_RULES_CONFIG`
- `SENTINEL_DATABASE_PATH`
- `SENTINEL_EVIDENCE_DIR`
- `SENTINEL_DETECTOR_MODEL`
- `SENTINEL_HOST`
- `SENTINEL_PORT`

Schedules are evaluated in the timezone configured in `rules.yaml`. An overnight schedule such as `22:00` to `06:00` is supported. If a schedule is omitted, the rule is always active.

## API

- `GET /api/health`
- `GET /api/cameras`
- `GET /api/alerts?limit=100`
- `GET /api/cameras/{camera_id}/stream`
- `GET /api/evidence/{filename}`

## Privacy and deployment

Use visible notices, access controls, short retention periods, and applicable local policies. Do not use this project to infer identity or protected traits. RTSP credentials should be supplied through protected deployment configuration, not committed to Git. Put the API behind authentication and TLS before exposing it outside a trusted network.

