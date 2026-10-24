# Filebrowser

A web file manager for the 14 TB media drive, for grabbing a file from anywhere.

**Runs on:** noahlab ([the boxes](../../README.md#the-boxes)) · **Reachable at:** `files.milkhaus.net`

It's the stock [Filebrowser](https://filebrowser.org) image. This folder is the live
deployment, run straight from my checkout of this repo. The user database lives in a
Docker volume on noahlab and never gets committed (the `filebrowser.db` mount is a
leftover; current images keep the database in their own volume).

| File | What it is |
|---|---|
| [`docker-compose.yml`](docker-compose.yml) | The container, with `/mnt/media` mounted |
| [`config.json`](config.json) | Settings file (mounted, but newer Filebrowser versions ignore it) |
