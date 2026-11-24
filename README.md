# Sentinel CV

Sentinel CV is a local, multi-camera computer-vision service that detects people and creates alerts when configurable safety rules are triggered. It supports webcams, USB cameras, RTSP streams, and video files.

The default design tracks anonymous objects only for the lifetime of a camera session. Optional identity recognition is available for a private, consent-based enrollment gallery and is disabled by default.

## Features

- YOLO person detection
- Optional YOLO face detection without identity recognition
- Optional local recognition of explicitly enrolled identities
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

The browser interface is organized into separate responsive pages:

- **Overview:** health metrics, camera connections, and latest alerts.
- **Cameras:** live streams, processing status, face counts, and recognized identities.
- **Video Test:** upload a local video and watch person and identity processing without creating alerts.
- **Identities:** enrollment, reference previews, rename, replacement, and deletion.
- **Alerts:** searchable and filterable event history with evidence links.
- **System:** read-only runtime, model, storage, retention, and security information.
- **About:** project purpose, processing pipeline, capabilities, privacy principles, technology, and limitations.

The first run may download the configured YOLO model. Set `SENTINEL_DETECTOR_MODEL` to a local model path for an offline deployment.

Face detection uses a separate `yolov11n-face.pt` checkpoint. Download it from the GPL-3.0 [`akanametov/yolo-face`](https://github.com/akanametov/yolo-face) project into `models/yolov11n-face.pt`, then set `face_detection: true` on the cameras where it should run. Face detection alone only draws anonymous boxes and counts faces.

## Optional identity recognition

Identity recognition is disabled by default and should only be used with informed consent and appropriate access controls. It matches detected face crops against a private local gallery; it does not search the internet, enroll unknown people, or identify anyone absent from that gallery.

1. Download OpenCV's SFace ONNX model to `models/face_recognition_sface_2021dec.onnx`.
2. Place a clear reference portrait under `data/identities/<identity-id>/`.
3. Enroll the portrait into SQLite:

   ```powershell
   python -m app.enroll --id owner --name Owner --image data/identities/owner/source.jpg
   ```

4. Set both `face_detection: true` and `identity_detection: true` for the intended camera.

Enrollment requires exactly one detected face. The cropped reference face and its embedding are stored in the `identities` table of the configured SQLite database. Reference images, databases, identity configuration, and ONNX models are ignored by Git. A match below `SENTINEL_IDENTITY_THRESHOLD` is labeled `Unknown`. Increasing the threshold reduces false matches but increases missed matches. Test the threshold with representative footage before operational use.

The dashboard includes an identity gallery for local enrollment, preview, rename, photo replacement, and deletion. Enrollment accepts JPEG, PNG, or WebP images up to 10 MB. Deleting an identity removes its stored face and embedding but does not rewrite historical alerts.

The service validates camera IDs, sources, schedules, timezones, rule geometry, thresholds, and confidence values at startup. A configuration error stops startup with a descriptive message instead of running with a partial configuration.

## Self-contained demo

The demo exercises the complete dashboard, tracking, rule evaluation, alert history, and evidence pipeline without a camera, video file, network stream, or YOLO download.

From the project directory with the virtual environment active, run:

```powershell
python -m app.demo
```

Then open <http://127.0.0.1:8000>. The synthetic lobby contains moving silhouettes that trigger restricted-area, loitering, occupancy, and line-crossing alerts. Let it run for several seconds, then use **Refresh** or wait for the dashboard to update.

Demo state is isolated from normal operation:

- Database: `data/demo-alerts.db`
- Evidence: `evidence/demo/`
- Camera configuration: `config/cameras.demo.yaml`
- Rules: `config/rules.demo.yaml`

Stop the demo with `Ctrl+C`. These generated data and evidence paths are ignored by Git.

## Configuration

Environment variables can override common settings:

- `SENTINEL_CAMERAS_CONFIG`
- `SENTINEL_RULES_CONFIG`
- `SENTINEL_DATABASE_PATH`
- `SENTINEL_EVIDENCE_DIR`
- `SENTINEL_DETECTOR_MODEL`
- `SENTINEL_FACE_DETECTOR_MODEL`
- `SENTINEL_FACE_DETECTOR_CONFIDENCE`
- `SENTINEL_IDENTITY_CONFIG`
- `SENTINEL_IDENTITY_MODEL`
- `SENTINEL_IDENTITY_THRESHOLD`
- `SENTINEL_HOST`
- `SENTINEL_PORT`

Schedules are evaluated in the timezone configured in `rules.yaml`. An overnight schedule such as `22:00` to `06:00` is supported. If a schedule is omitted, the rule is always active.

Camera entries accept `face_detection` (default `false`), `identity_detection` (default `false`), and `face_process_every_n_frames` (default `1`). Identity recognition requires face detection. Increasing the face interval reduces CPU/GPU load at the cost of less frequent face-count and identity updates. Face and identity model performance depends on camera angle, lighting, occlusion, and face size.

Live and test-video previews draw one box per tracked individual. A current face detection receives priority, so the box surrounds the face and is labeled with an enrolled name or `Unknown`. When no face can be associated, the system falls back to the larger person box. It never draws both boxes for the same individual.

`evidence_retention_days` controls JPEG cleanup. Set it to a positive number to purge older evidence during startup. Set it to `0` to retain evidence indefinitely. When a file is purged, its alert remains in history and its evidence link is cleared.

## API

- `GET /api/health`
- `GET /api/system`
- `GET /api/cameras`
- `GET /api/alerts?limit=100`
- `GET /api/identities`
- `GET /api/identities/{identity_id}/image`
- `POST /api/identities`
- `PATCH /api/identities/{identity_id}`
- `DELETE /api/identities/{identity_id}`
- `POST /api/video-tests?filename=<video>`
- `GET /api/video-tests/{job_id}`
- `GET /api/video-tests/{job_id}/stream`
- `DELETE /api/video-tests/{job_id}`
- `GET /api/cameras/{camera_id}/stream`
- `GET /api/evidence/{filename}`

The health endpoint reports `degraded` while one or more enabled cameras are disconnected. Camera workers reconnect automatically using each camera's `reconnect_seconds` setting.

## Test

Tests use temporary databases and evidence directories; they do not open cameras or load the detector model.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Troubleshooting

- **Camera stays offline:** Confirm the numeric device index, file path, or stream URL and check `last_error` in `GET /api/cameras`.
- **No detections:** Confirm the model is available and that the source frame is being processed. The first detector call may download the configured model if it is not local.
- **No face boxes:** Confirm `face_detection: true`, verify the face-model path, and lower `SENTINEL_FACE_DETECTOR_CONFIDENCE` if appropriate.
- **Known person is `Unknown`:** Confirm the SFace model and reference paths, use tightly cropped reference portraits, and cautiously lower `SENTINEL_IDENTITY_THRESHOLD` after testing false matches.
- **Zones do not align:** Zone and line points use original source-frame pixels, not browser preview coordinates.
- **Timezone error at startup:** Use an IANA timezone such as `Asia/Kolkata` or `UTC`.
- **RTSP instability:** Increase `reconnect_seconds` and avoid embedding credentials in committed configuration.

## Privacy and deployment

Use visible notices, informed consent, access controls, short retention periods, and applicable biometric/privacy policies. Never use identity output to infer protected traits or as the sole basis for consequential decisions. False matches and missed matches are expected. RTSP credentials and biometric data must remain in protected deployment storage, not Git. The bundled service has no authentication or TLS; bind it to a trusted interface and place it behind an authenticated TLS reverse proxy before any wider exposure.

