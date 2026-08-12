# Home Assistant

Automation hub for the house: presence-driven HVAC, irrigation with a failsafe,
doorbell capture, chore notifications, and the webhook relay that lets everything else
on the box reach a phone. Runs with host networking beside a Matter bridge and an
authenticated Mosquitto broker.

## Stack

| Container | Role |
|---|---|
| `homeassistant` | HA core, host network, `/mnt/media/homeassistant` as media dir |
| `matter-bridge` | matterbridge — exposes HA devices to Matter controllers via a long-lived token ([`.env`](.env.example)) |
| `mosquitto` | MQTT broker, **anonymous access off**, password file outside the repo — Frigate and HA share the credential |

## Automations worth reading

[`automations.yaml`](automations.yaml) is small but carries a few patterns that took
iteration to get right:

- **Presence HVAC with recovery pollers.** Zone triggers set the thermostat home/away,
  but zone events can be missed — so paired `Check if Away` / `Check if Home`
  automations poll on a time pattern as a catch-up net. The conditions encode two
  hard-won rules: the poller must be idempotent (a "not already away" guard stops it
  re-sending and overriding manual changes), and **both pollers must run the same
  weekday set** — when the home-recovery poller ran Mon–Fri only, an away state set on
  Friday night persisted all weekend.
- **Pump failsafe.** The irrigation automations use an in-memory 2-minute delay, so an
  HA restart mid-run would leave the pump running indefinitely. `Pump failsafe off`
  backstops it two ways: an on-for-5-minutes state trigger (catches everything,
  including a manual turn-on someone forgot), and an HA-start trigger (catches the
  restart-mid-run case).
- **Doorbell capture.** The battery doorbell sleeps; its motion-detect entity turning
  on wakes it, then a short delay, a 20 s clip with 3 s lookback, a snapshot, and a
  photo notification to both phones — queued mode so bursts don't drop.
- **Webhook relays.** Two `local_only` webhooks turn box events into phone pushes:
  Donetick chore reminders route to the *assignee's* phone (completions notify the
  other partner), and [`vd-flag`](../../virtual-desktop/bin/vd-flag) fires a
  time-sensitive push when an automation agent is blocked on a login wall or captcha.
  Webhook ids are redacted here.

[`scripts.yaml`](scripts.yaml) holds the callable pieces: PTZ pulse-move helpers for
the [Frigate](../frigate/) cameras, a cat-feeder portion trigger, an ADB command that
launches Jellyfin on the living-room TV, and a scene that sets every lamp to its
"Dance Party" effect, because of course it does.

## Metrics

The `prometheus:` integration exposes `/api/prometheus`, scraped by the
[monitoring stack](../monitoring/) with a dedicated long-lived token — house
temperature, humidity, entity availability, and automation trigger counts end up on
the Grafana home dashboard.
