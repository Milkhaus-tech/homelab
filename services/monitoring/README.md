# Monitoring

Prometheus + Grafana with the box's dashboards **built from Python** — dashboard
changes are code-reviewable diffs, and a wiped Grafana can be reconstructed by
re-running two scripts.

## Scrape map

| Job | Targets | Notes |
|---|---|---|
| `node_stats` | this box + a desktop (node_exporter) | two more fleet machines commented out for the summer — they return in winter |
| `cadvisor` | per-container CPU/memory/network | on 8098; 8080 is taken by qBittorrent |
| `exportarr` ×3 | Sonarr / Radarr / Prowlarr | queue depth, library counts, indexer health |
| `jellyfin` | native `/metrics` | generic .NET runtime metrics only — request rate is the honest health proxy |
| `frigate` | `/api/metrics` | camera FPS, detector inference ms |
| `homeassistant` | `/api/prometheus` | authenticated with a dedicated long-lived token mounted read-only (`ha_token`, file mode 400, never in git) |

## Dashboards as code

[`dashboards/build_glance.py`](dashboards/build_glance.py) and
[`build_overview.py`](dashboards/build_overview.py) emit complete dashboard JSON to
stdout; deploying a change is:

```sh
python3 dashboards/build_glance.py | curl -sS -X POST -H 'Content-Type: application/json' \
  -u "$GRAFANA_USER:$GRAFANA_PASS" -d @- http://localhost:3000/api/dashboards/db
```

- **At a Glance** (`homelab-glance`): host tiles, usage row, a Home Assistant row
  (house temp/humidity/lights/batteries), and a 20-container UP/DOWN grid. Game-server
  tiles match on the Wings container *label + image* rather than name, so they survive
  a server being deleted and recreated under a new UUID.
- **Homelab Overview** (`homelab-overview`): trends — per-host CPU/RAM, network with
  transmit drawn below the axis, filesystem fill, top-10 containers, and service
  panels (Jellyfin req/s, Frigate FPS + inference). The two host colors are a
  CVD-validated pair.

Both dashboards cross-link, with imported per-app dashboards tucked behind a tagged
dropdown.

## Grafana hardening-adjacent notes

Grafana sits on the Tailscale/LAN ring only (see
[exposure model](../../docs/architecture.md#exposure-model)). `GF_PANELS_DISABLE_SANITIZE_HTML`
is on — a deliberate single-admin-box tradeoff to allow a styled HTML banner panel;
don't copy that setting onto anything multi-user. News/analytics/update pings are off.
The custom branding mounts overlay art files that aren't redistributed in this repo.
