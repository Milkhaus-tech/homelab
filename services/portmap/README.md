# Port map

Two static pages I keep as a cheat sheet. One lists every public domain and every port
on every machine, the other has my Wake-on-LAN and BIOS setup notes for each box.

**Runs on:** noahlab ([the boxes](../../README.md#the-boxes)) · **Reachable at:** `noahlab:1337` on Tailscale or the LAN

It's plain nginx serving the [`html/`](html/) folder. The real Tailscale addresses get
swapped for `100.x.y.z` placeholders when the pages are copied into this repo.

| File | What it is |
|---|---|
| [`html/index.html`](html/index.html) | The port map |
| [`html/guide.html`](html/guide.html) | Wake-on-LAN and BIOS notes |
| [`docker-compose.yml`](docker-compose.yml) | nginx on port 1337 |
