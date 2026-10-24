# Monitoring

Prometheus collects numbers from every box and Grafana shows them. The two main
dashboards are built from Python, so changing one shows up as a diff and a wiped Grafana
comes back by re-running two scripts.

**Runs on:** jesus (Prometheus + Grafana), with exporters on noahlab ([the boxes](../../README.md#the-boxes)) · **Reachable from:** Tailscale and the LAN only

## How it works

[`docker-compose.yml`](docker-compose.yml) on jesus runs Prometheus, Grafana, cAdvisor
(per-container stats) and a blackbox prober. [`exporters/`](exporters/) is the smaller
compose file on noahlab: node_exporter, cAdvisor, and exportarr for Sonarr, Radarr and
Prowlarr.

What [`prometheus.yml`](prometheus.yml) scrapes:

| Job | What | Notes |
|---|---|---|
| `node_stats` | node_exporter on noahlab, jesus, pablo and my desktop | CPU, memory, disk, network |
| `cadvisor` | noahlab and jesus | on port 8098, since qBittorrent has 8080 on noahlab |
| `exportarr` | Sonarr, Radarr, Prowlarr | queue size, library counts, indexer health |
| `jellyfin` | Jellyfin's `/metrics` | only generic .NET numbers, so request rate is the useful one |
| `frigate` | `/api/metrics` on jesus | camera fps, detection time |
| `homeassistant` | `/api/prometheus` | uses its own long-lived token from a file that's never in git |
| `sites` | 16 public URLs through the blackbox prober | is each site up |

## Dashboards

[`build_glance.py`](dashboards/build_glance.py) and
[`build_overview.py`](dashboards/build_overview.py) print complete dashboard JSON.
Deploying a change, on jesus:

```sh
python3 dashboards/build_glance.py | curl -sS -X POST -H 'Content-Type: application/json' \
  -u "$GRAFANA_USER:$GRAFANA_PASS" -d @- http://localhost:3000/api/dashboards/db
```

- **At a Glance** (`homelab-glance`): a tile per box, usage, a house row from Home
  Assistant (temperature, humidity, lights, batteries), and an up/down grid of the main
  containers. Game server tiles match on the Wings label and image instead of the
  container name, so they survive a server getting recreated.
- **Homelab Overview** (`homelab-overview`): trends. CPU and memory per box, network,
  disk fill, the top 10 containers, Jellyfin requests and Frigate fps.

## Worth knowing

- `GF_PANELS_DISABLE_SANITIZE_HTML` is on so a text panel can carry a styled banner.
  That's fine on a Grafana only I log into. Don't copy it onto anything with other users.
- The custom branding mounts art files that aren't in this repo.

## Files

| File | What it is |
|---|---|
| [`docker-compose.yml`](docker-compose.yml), [`.env.example`](.env.example) | Prometheus, Grafana, cAdvisor and blackbox on jesus |
| [`exporters/`](exporters/) | The exporters on noahlab |
| [`prometheus.yml`](prometheus.yml) | Scrape config |
| [`dashboards/`](dashboards/) | The two dashboard builders |
