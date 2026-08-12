# Frigate NVR

Nine-camera NVR with GPU object detection: TensorRT build, YOLOX detection, 7-day
continuous recording to the media pool, and full MQTT integration into Home Assistant.

## Stream architecture

Every camera publishes two RTSP streams, and go2rtc (bundled with Frigate) restreams
both so the cameras only ever serve one client each:

- **Main stream** → recording (10 s segments, stream-copied, no transcode)
- **Sub stream** (1280×720 @ 5 fps) → detection

Detection never decodes the full-resolution feed; ffmpeg uses `preset-nvidia` hwaccel.
WebRTC live view is available through go2rtc on 8555.

## Detection

| | |
|---|---|
| Model | YOLOX-nano ONNX, 416×416, ONNX detector on the GPU (TensorRT image) |
| Objects | `person`, `cat` |
| Tuning | Per-camera filters — e.g. one camera runs much looser cat thresholds (min_score 0.2 vs 0.5) because that's where the cat actually goes |

## Recording & retention

Continuous 7-day recording plus 7-day snapshot retention for every camera, stored on
the 14 TB pool (`/mnt/media/frigate`). Motion-only retention is deliberately off —
continuous + short retention beats motion gaps when reviewing an event.

## Integrations

- **MQTT** → Mosquitto (authenticated) → Home Assistant: events, occupancy, controls.
- **PTZ**: pan/tilt exposed as `frigate.ptz` services; Home Assistant
  [scripts](../home-assistant/scripts.yaml) implement pulse-move buttons (move,
  500 ms, stop) with an `input_select` choosing the active camera.
- **Doorbell**: wake-triggered clip capture + phone notification lives in
  [Home Assistant automations](../home-assistant/automations.yaml), using HA's camera
  services rather than Frigate events (the battery doorbell sleeps).
- **Prometheus**: scraped at `/api/metrics` — camera FPS and detector inference time
  are on the [Grafana overview dashboard](../monitoring/dashboards/).

## Secrets pattern

[`config.yaml`](config.yaml) uses Frigate's native environment substitution: any
`{FRIGATE_*}` placeholder is replaced from the container environment, so camera
credentials live in [`.env`](.env.example) and the config file stays committable.
