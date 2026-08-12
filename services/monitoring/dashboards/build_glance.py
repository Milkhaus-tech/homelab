import json

DS = {"type": "prometheus", "uid": "afk8hs38s5n28a"}
pid = [0]
def nid():
    pid[0] += 1; return pid[0]

UPDOWN = [{"type": "value", "options": {
    "1": {"text": "UP", "color": "green"},
    "0": {"text": "DOWN", "color": "red"}}}]
ONOFF = [{"type": "value", "options": {
    "1": {"text": "ONLINE", "color": "green"},
    "0": {"text": "OFFLINE", "color": "red"}}}]

def bigstat(title, expr, mappings, x, y, w=6, h=5):
    return {"id": nid(), "type": "stat", "title": title,
        "gridPos": {"x": x, "y": y, "w": w, "h": h}, "datasource": DS,
        "targets": [{"datasource": DS, "expr": expr, "refId": "A"}],
        "fieldConfig": {"defaults": {"mappings": mappings,
            "thresholds": {"mode": "absolute", "steps": [{"color": "red", "value": None}]}},
            "overrides": []},
        "options": {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "background",
                    "textMode": "value", "graphMode": "none"}}

def countstat(title, expr, x, y, thresholds, w=6, h=5, fixed=None):
    fc = {"decimals": 0, "thresholds": {"mode": "absolute", "steps": thresholds}}
    if fixed: fc["color"] = {"mode": "fixed", "fixedColor": fixed}
    return {"id": nid(), "type": "stat", "title": title,
        "gridPos": {"x": x, "y": y, "w": w, "h": h}, "datasource": DS,
        "targets": [{"datasource": DS, "expr": expr, "refId": "A"}],
        "fieldConfig": {"defaults": fc, "overrides": []},
        "options": {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "value",
                    "textMode": "value", "graphMode": "none"}}

def usage(title, expr, unit, x, y, thresholds, w=4, h=5, fixed=None):
    fc = {"unit": unit, "decimals": 0, "thresholds": {"mode": "absolute", "steps": thresholds}}
    if fixed: fc["color"] = {"mode": "fixed", "fixedColor": fixed}
    return {"id": nid(), "type": "stat", "title": title,
        "gridPos": {"x": x, "y": y, "w": w, "h": h}, "datasource": DS,
        "targets": [{"datasource": DS, "expr": expr, "refId": "A"}],
        "fieldConfig": {"defaults": fc, "overrides": []},
        "options": {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "value",
                    "textMode": "value", "graphMode": "area"}}

pct = [{"color": "green", "value": None}, {"color": "yellow", "value": 70}, {"color": "red", "value": 90}]
tempth = [{"color": "green", "value": None}, {"color": "yellow", "value": 70}, {"color": "red", "value": 85}]
problems = [{"color": "green", "value": None}, {"color": "red", "value": 1}]
plain = [{"color": "text", "value": None}]

TETO = "#C63C51"

BANNER_HTML = """<style>
.main-view {
  background:
    radial-gradient(1100px 520px at 88% -8%, rgba(198,60,81,.18), transparent 60%),
    radial-gradient(800px 480px at -6% 108%, rgba(175,48,64,.12), transparent 55%);
}
</style>
<div style="display:flex;align-items:center;justify-content:space-between;height:100%;padding:0 14px;overflow:hidden;">
  <div>
    <div style="font-size:34px;font-weight:800;letter-spacing:6px;color:#ede3e4;line-height:1.1;">NOAHLAB</div>
    <div style="font-size:13px;font-weight:600;letter-spacing:3px;color:#C63C51;margin-top:4px;">重音テト &middot; HOMELAB CONSOLE</div>
  </div>
  <img src="/public/img/teto/teto.png" alt="Kasane Teto"
       style="height:132px;margin-right:6px;filter:drop-shadow(0 0 14px rgba(198,60,81,.5));"/>
</div>"""

def banner(y=0, h=4):
    return {"id": nid(), "type": "text", "title": "", "transparent": True,
            "gridPos": {"x": 0, "y": y, "w": 24, "h": h},
            "options": {"mode": "html", "content": BANNER_HTML}}

NL = 'instance="192.168.1.10:9100"'
ND = 'instance="192.168.1.13:9100"'

# tile label -> promql selector inside container_last_seen{...}
# game servers matched by wings label + image so tiles survive delete/recreate (new UUID)
CONTAINERS = [
    ("frigate", 'name="frigate"'), ("home assistant", 'name="homeassistant"'),
    ("mosquitto", 'name="mosquitto"'), ("matter bridge", 'name="matter-bridge"'),
    ("donetick", 'name="donetick"'),
    ("jellyfin", 'name="jellyfin"'), ("jellyseerr", 'name="jellyseerr"'),
    ("gluetun VPN", 'name="gluetun"'), ("qbittorrent", 'name="qbittorrent"'),
    ("sonarr", 'name="sonarr"'), ("radarr", 'name="radarr"'),
    ("prowlarr", 'name="prowlarr"'), ("bazarr", 'name="bazarr"'),
    ("autobrr", 'name="autobrr"'),
    ("pterodactyl", 'name="pterodactyl-panel-1"'),
    ("CS2 server", 'container_label_Service="Pterodactyl",image=~".*cs2.*"'),
    ("Factorio server", 'container_label_Service="Pterodactyl",image=~".*yolks.*"'),
    ("discord bot", 'name="milkhaus-discord-bot"'),
    ("fantasy backend", 'name="fantasy-football-backend"'),
    ("fantasy frontend", 'name="fantasy-football-frontend"'),
]

container_targets = [{
    "datasource": DS,
    "expr": f'clamp_max(count(container_last_seen{{{sel}}} > (time() - 120)), 1) or vector(0)',
    "legendFormat": label, "refId": f"C{i:02d}",
} for i, (label, sel) in enumerate(CONTAINERS)]

panels = [
    banner(y=0, h=4),

    bigstat("Noahlab (server)", f'up{{{NL}}}', ONOFF, 0, 4),
    bigstat("Noah Desktop", f'up{{{ND}}}', ONOFF, 6, 4),
    countstat("Problems (targets down)", "count(up == 0) or vector(0)", "12", 4, problems),
    countstat("Containers running", 'count(container_last_seen{name!=""})', "18", 4, plain, fixed=TETO),

    usage("Noahlab CPU", f'100 - (avg(rate(node_cpu_seconds_total{{mode="idle",{NL}}}[5m])) * 100)', "percent", 0, 9, pct, h=4),
    usage("Noahlab RAM", f'(1 - node_memory_MemAvailable_bytes{{{NL}}} / node_memory_MemTotal_bytes{{{NL}}}) * 100', "percent", 4, 9, pct, h=4),
    usage("Noahlab disk", f'100 - (node_filesystem_avail_bytes{{{NL},mountpoint="/"}} / node_filesystem_size_bytes{{{NL},mountpoint="/"}} * 100)', "percent", 8, 9, pct, h=4),
    usage("Noahlab temp", f'max(node_hwmon_temp_celsius{{{NL}}})', "celsius", 12, 9, tempth, h=4),
    usage("Desktop CPU", f'100 - (avg(rate(node_cpu_seconds_total{{mode="idle",{ND}}}[5m])) * 100)', "percent", 16, 9, pct, h=4),
    usage("Desktop RAM", f'(1 - node_memory_MemAvailable_bytes{{{ND}}} / node_memory_MemTotal_bytes{{{ND}}}) * 100', "percent", 20, 9, pct, h=4),

    # Home Assistant row
    usage("House temp", 'homeassistant_climate_current_temperature_celsius', "celsius",
          0, 13, [{"color": "green", "value": None}, {"color": "yellow", "value": 27}, {"color": "red", "value": 30}], h=4),
    usage("House humidity", 'homeassistant_sensor_humidity_percent', "percent",
          4, 13, [{"color": "green", "value": None}, {"color": "yellow", "value": 60}, {"color": "red", "value": 70}], h=4),
    usage("Lights on", 'count(homeassistant_light_brightness_percent > 0) or vector(0)', "none",
          8, 13, plain, h=4, fixed=TETO),
    usage("Low batteries (<30%)", 'count(homeassistant_sensor_battery_percent < 30) or vector(0)', "none",
          12, 13, [{"color": "green", "value": None}, {"color": "yellow", "value": 1}, {"color": "red", "value": 3}], h=4),
    usage("HA entities unavailable", 'count(homeassistant_entity_available == 0) or vector(0)', "none",
          16, 13, plain, h=4, fixed=TETO),
    usage("Automations fired (24h)", 'sum(increase(homeassistant_automation_triggered_count_total[24h])) or vector(0)', "none",
          20, 13, plain, h=4, fixed=TETO),

    {"id": nid(), "type": "stat", "title": "Important containers",
     "gridPos": {"x": 0, "y": 17, "w": 24, "h": 8}, "datasource": DS,
     "targets": container_targets,
     "fieldConfig": {"defaults": {"mappings": UPDOWN,
         "thresholds": {"mode": "absolute", "steps": [{"color": "red", "value": None}]}},
         "overrides": []},
     "options": {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "background",
                 "textMode": "value_and_name", "graphMode": "none"}},
]

# gridPos x must be int
for p in panels:
    p["gridPos"]["x"] = int(p["gridPos"]["x"])

dash = {"uid": "homelab-glance", "title": "At a Glance", "tags": ["homelab"],
        "timezone": "browser", "schemaVersion": 39, "refresh": "30s",
        "time": {"from": "now-1h", "to": "now"}, "panels": panels, "editable": True,
        "links": [
            {"title": "Homelab Overview", "type": "link", "icon": "dashboard",
             "url": "/d/homelab-overview/homelab-overview", "keepTime": False},
            {"title": "Details", "type": "dashboards", "tags": ["detail"],
             "asDropdown": True, "keepTime": False, "includeVars": False},
        ]}
print(json.dumps({"dashboard": dash, "overwrite": True, "folderUid": ""}))
