# Frigate

Records the house cameras and watches them for people and cats.
[Frigate](https://frigate.video) is an open-source NVR (network video recorder) with
object detection.

**Runs on:** jesus, with recordings saved to noahlab's big drive over NFS ([the boxes](../../README.md#the-boxes)) · **Reachable from:** Tailscale and the LAN only · **Talks to:** [Home Assistant](../home-assistant/)

## How it works

- **Nine cameras.** Each one sends two RTSP streams, and go2rtc (built into Frigate)
  restreams them so every camera only ever has one client.
  - The **main stream** gets recorded as-is, in 10-second segments, no transcoding.
  - The **sub stream** (1280×720 at 5 fps) is what detection looks at, so it never has to
    decode the full-resolution feed. Decoding uses the GPU (`preset-nvidia`).
- **Detection** runs a YOLOv9-s model at 320×320 on the CPU through OpenVINO, and only
  tracks `person` and `cat`. The older YOLOX-nano model kept calling backpacks and cats
  people.
- **Recording** is continuous for 7 days, plus 7 days of snapshots, on noahlab's
  `/mnt/media`. I keep continuous instead of motion-only, since a short gap in the
  middle of an event is worse than a shorter history.
- **Home Assistant** gets events and room occupancy over MQTT, which is what drives the
  downstairs lights. Pan/tilt buttons for the cameras are Home Assistant
  [scripts](../home-assistant/scripts.yaml).
- **Prometheus** scrapes `/api/metrics` for camera fps and detection time.

## Worth knowing

- Camera logins in [`config.yaml`](config.yaml) show as `{FRIGATE_*}` placeholders. Frigate
  fills those in from the container's environment ([`.env.example`](.env.example)).
  The live file has them inline, and the sync script swaps them out when it copies it
  here.
- Frigate is pinned away from the CPU threads the Zomboid server uses
  ([how](../../docs/architecture.md#keeping-games-smooth)).

## Files

| File | What it is |
|---|---|
| [`docker-compose.yml`](docker-compose.yml) | Frigate 0.17.2, with the GPU and the NFS recordings folder |
| [`config.yaml`](config.yaml) | Cameras, detection, zones, recording |
| [`.env.example`](.env.example) | The camera and MQTT logins |
