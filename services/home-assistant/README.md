# Home Assistant

Runs the house: the thermostat follows whether anyone's home, the downstairs lights
follow the cameras, the doorbell sends a clip, and chores get reminders.

**Runs on:** noahlab ([the boxes](../../README.md#the-boxes)) · **Reachable from:** Tailscale and the LAN only · **Talks to:** [Frigate](../frigate/) on jesus, [Donetick](../donetick/)

## How it works

| Container | What it does |
|---|---|
| `homeassistant` | Home Assistant itself, on the host network |
| `mosquitto` | The MQTT broker Frigate and Home Assistant talk through. Logins required |
| `matter-server`, `matter-bridge` | Matter support, and matterbridge, which shares my Home Assistant devices with other Matter apps |
| `go2rtc-tuya` | Relays the cat feeders' cameras so Home Assistant gets a clean stream |

The automations in [`automations.yaml`](automations.yaml):

- **Heating and cooling.** Leaving or coming home flips the thermostat between away and
  home, plus a precool before the 6pm peak rate. Zone events sometimes get missed, so
  two pollers (`Check if Away` / `Check if Home`) catch up. They skip anything already in
  the right state so they don't undo a manual change, and they run on the same days.
  When one of them only ran on weekdays, the house stayed in away mode all weekend.
- **Downstairs lights** turn on when Frigate sees a person after dark and turn off after
  10 minutes with nobody there. They dim instead while Jellyfin is playing on the TV.
- **The iPad wall panel** wakes when someone's downstairs and goes to its screensaver
  when nobody is.
- **The doorbell** runs on a battery and sleeps, so its motion sensor wakes it, then it
  records a 20-second clip and sends a snapshot to both our phones.
- **Chores.** Donetick's webhook comes in here and becomes a phone notification
  ([details](../donetick/)).

[`scripts.yaml`](scripts.yaml) has the buttons: pan/tilt for the cameras, one portion
from each cat feeder, Fire TV remote helpers (launch or resume Jellyfin, type into a
search box), and a "Dance Party" scene for the lamps.

## Worth knowing

- The ecobee ignores mode changes while a hold is active, so every thermostat automation
  clears the hold first.
- Prometheus reads Home Assistant's `/api/prometheus` with its own long-lived token, so
  house temperature, humidity and battery levels show up in [Grafana](../monitoring/).
- Webhook ids are redacted in this copy, and the Matter bridge's token comes from
  [`.env`](.env.example).

## Files

| File | What it is |
|---|---|
| [`docker-compose.yml`](docker-compose.yml) | All five containers |
| [`configuration.yaml`](configuration.yaml) | Main config: Prometheus, camera feeds, light groups, sensors |
| [`automations.yaml`](automations.yaml) | The automations above |
| [`scripts.yaml`](scripts.yaml) | Buttons and helpers |
| [`mosquitto.conf`](mosquitto.conf) | MQTT broker config |
