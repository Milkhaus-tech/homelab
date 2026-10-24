# xmrig

A CPU miner ([XMRig](https://xmrig.com)) I run on noahlab when it's otherwise idle. It
gets 6 of the 16 threads and stops when the CPU gets hot. It's switched off right now.

**Runs on:** noahlab ([the boxes](../../README.md#the-boxes)) · **Reachable:** nothing to reach, it only talks to the pool

## How it works

[`run-safe-xmrig.sh`](run-safe-xmrig.sh) wraps the miner with temperature checks:

- It won't start above 82 °C, and a watchdog loop kills the miner if the CPU crosses
  82 °C while it's running.
- After any exit (crash, out of memory, or the watchdog), it waits until the CPU is back
  under 70 °C, then exits with an error so
  [systemd](xmrig.service) starts the whole thing again (`Restart=always`, `Nice=10`).
- It sets up the huge pages and the `msr` module that RandomX mining wants.
- The script waits on whichever of the miner or the watchdog exits first (`wait -n`),
  then stops both, so every kind of failure goes down the same path.

## Worth knowing

- Six threads keep it away from the game server's cores and leave room for the media
  stack ([how](../../docs/architecture.md#keeping-games-smooth)).
- The pool config (`config.json`) has the wallet in it, so it isn't in this repo.

## Files

| File | What it is |
|---|---|
| [`run-safe-xmrig.sh`](run-safe-xmrig.sh) | The temperature wrapper |
| [`xmrig.service`](xmrig.service) | The systemd unit (disabled at the moment) |
