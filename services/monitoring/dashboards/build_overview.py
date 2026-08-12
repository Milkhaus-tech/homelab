import json

DS = {"type": "prometheus", "uid": "afk8hs38s5n28a"}
pid = 0
def nid():
    global pid; pid += 1; return pid

def target(expr, legend=""):
    return {"datasource": DS, "expr": expr, "legendFormat": legend, "refId": chr(65 + nid() % 26)}

def stat(title, expr, unit, x, y, w=4, h=4, thresholds=None, decimals=1):
    steps = thresholds or [{"color": "green", "value": None}]
    return {
        "id": nid(), "type": "stat", "title": title,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "datasource": DS, "targets": [target(expr)],
        "fieldConfig": {"defaults": {
            "unit": unit, "decimals": decimals,
            "thresholds": {"mode": "absolute", "steps": steps}}, "overrides": []},
        "options": {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "value",
                    "graphMode": "area", "textMode": "auto"},
    }

TETO = "#C63C51"
DESKTOP_BLUE = "#3F8FD2"  # pair validated with TETO for CVD/contrast (dataviz checks)

def color_override(name, color):
    return {"matcher": {"id": "byName", "options": name},
            "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": color}}]}

def ts(title, targets, unit, x, y, w=12, h=8, extra_defaults=None, overrides=None,
       desc=None, fixed=None, legend_table=True):
    defaults = {"unit": unit, "custom": {"drawStyle": "line", "lineWidth": 2,
                "fillOpacity": 10, "pointSize": 4, "showPoints": "never"}}
    if fixed: defaults["color"] = {"mode": "fixed", "fixedColor": fixed}
    if extra_defaults: defaults.update(extra_defaults)
    legend = ({"displayMode": "table", "placement": "bottom",
               "calcs": ["min", "mean", "max", "lastNotNull"]}
              if legend_table else {"displayMode": "list", "placement": "bottom"})
    p = {
        "id": nid(), "type": "timeseries", "title": title,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "datasource": DS, "targets": targets,
        "fieldConfig": {"defaults": defaults, "overrides": overrides or []},
        "options": {"legend": legend, "tooltip": {"mode": "multi", "sort": "desc"}},
    }
    if desc: p["description"] = desc
    return p

pct = [{"color": "green", "value": None}, {"color": "yellow", "value": 70}, {"color": "red", "value": 90}]
tempth = [{"color": "green", "value": None}, {"color": "yellow", "value": 70}, {"color": "red", "value": 85}]
downth = [{"color": "green", "value": None}, {"color": "red", "value": 1}]

panels = [
    # Row A — headline tiles
    stat("Targets down", "count(up == 0) or vector(0)", "none", 0, 0, thresholds=downth, decimals=0),
    stat("Noahlab CPU", '100 - (avg(rate(node_cpu_seconds_total{mode="idle",instance="192.168.1.10:9100"}[5m])) * 100)', "percent", 4, 0, thresholds=pct),
    stat("Noahlab RAM", '(1 - node_memory_MemAvailable_bytes{instance="192.168.1.10:9100"} / node_memory_MemTotal_bytes{instance="192.168.1.10:9100"}) * 100', "percent", 8, 0, thresholds=pct),
    stat("Root FS used", '100 - (node_filesystem_avail_bytes{instance="192.168.1.10:9100",mountpoint="/"} / node_filesystem_size_bytes{instance="192.168.1.10:9100",mountpoint="/"} * 100)', "percent", 12, 0, thresholds=pct),
    stat("Noahlab temp", 'max(node_hwmon_temp_celsius{instance="192.168.1.10:9100"})', "celsius", 16, 0, thresholds=tempth),
    stat("Containers", 'count(container_last_seen{name!=""})', "none", 20, 0, decimals=0),
    # Row B — service status grid
    {
        "id": nid(), "type": "stat", "title": "Scrape target status",
        "gridPos": {"x": 0, "y": 4, "w": 24, "h": 5},
        "datasource": DS, "targets": [target("up", "{{job}} · {{instance}}")],
        "fieldConfig": {"defaults": {
            "mappings": [{"type": "value", "options": {
                "1": {"text": "UP", "color": "green"},
                "0": {"text": "DOWN", "color": "red"}}}],
            "thresholds": {"mode": "absolute", "steps": [{"color": "red", "value": None}]}},
            "overrides": []},
        "options": {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "background",
                    "textMode": "value_and_name", "graphMode": "none"},
    },
    # Row C — host trends (Noahlab crimson / Desktop blue, pair validated for CVD+contrast)
    ts("CPU per host", [target('100 - (avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)', "{{instance}}")],
       "percent", 0, 9, extra_defaults={"min": 0, "max": 100},
       overrides=[color_override("192.168.1.10:9100", TETO), color_override("192.168.1.13:9100", DESKTOP_BLUE)]),
    ts("Memory used per host", [target('(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100', "{{instance}}")],
       "percent", 12, 9, extra_defaults={"min": 0, "max": 100},
       overrides=[color_override("192.168.1.10:9100", TETO), color_override("192.168.1.13:9100", DESKTOP_BLUE)]),
    # Row D — network + disk
    ts("Network throughput (Noahlab)", [
        target('sum(rate(node_network_receive_bytes_total{instance="192.168.1.10:9100",device!~"lo|veth.*|br-.*|docker.*"}[5m])) * 8', "receive"),
        target('sum(rate(node_network_transmit_bytes_total{instance="192.168.1.10:9100",device!~"lo|veth.*|br-.*|docker.*"}[5m])) * 8', "transmit"),
       ], "bps", 0, 17,
       desc="Transmit drawn below the axis; physical NICs only (bridges/veth excluded).",
       overrides=[{"matcher": {"id": "byName", "options": "transmit"},
                   "properties": [{"id": "custom.transform", "value": "negative-Y"}]}]),
    ts("Filesystem used %", [target('100 - (node_filesystem_avail_bytes{fstype=~"ext4|xfs|btrfs"} / node_filesystem_size_bytes{fstype=~"ext4|xfs|btrfs"} * 100)', "{{instance}} {{mountpoint}}")],
       "percent", 12, 17, extra_defaults={"min": 0, "max": 100}),
    # Row E — containers (many series: default palette, list legend to keep height sane)
    ts("Top 10 containers by CPU", [target('topk(10, sum by(name) (rate(container_cpu_usage_seconds_total{name!=""}[5m])) * 100)', "{{name}}")],
       "percent", 0, 25, extra_defaults={"min": 0}, legend_table=False),
    ts("Top 10 containers by memory", [target('topk(10, sum by(name) (container_memory_working_set_bytes{name!=""}))', "{{name}}")],
       "bytes", 12, 25, legend_table=False),
    # Row F — services
    ts("Jellyfin HTTP requests/s", [target('sum(rate(http_requests_received_total{job="jellyfin"}[5m]))', "req/s")],
       "reqps", 0, 33, w=8, fixed=TETO, extra_defaults={"min": 0},
       desc="Jellyfin exposes only generic .NET runtime metrics natively — request rate is the best health proxy."),
    ts("Frigate camera FPS", [target('frigate_camera_fps', "{{camera_name}}{{camera}}")],
       "none", 8, 33, w=8, legend_table=False),
    ts("Frigate detector inference", [target('frigate_detector_inference_speed_seconds * 1000', "{{name}}")],
       "ms", 16, 33, w=8, fixed=TETO, extra_defaults={"min": 0}),
]

dash = {
    "uid": "homelab-overview", "title": "Homelab Overview", "tags": ["homelab"],
    "timezone": "browser", "schemaVersion": 39, "refresh": "30s",
    "time": {"from": "now-6h", "to": "now"},
    "panels": panels, "editable": True,
    "links": [
        {"title": "At a Glance", "type": "link", "icon": "dashboard",
         "url": "/d/homelab-glance/at-a-glance", "keepTime": False},
        {"title": "Details", "type": "dashboards", "tags": ["detail"],
         "asDropdown": True, "keepTime": False, "includeVars": False},
    ],
}
print(json.dumps({"dashboard": dash, "overwrite": True, "folderUid": ""}))
