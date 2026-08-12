# xmrig (safe idle miner)

Context, since a miner in a public repo deserves it: this runs on the author's **own
hardware**, opt-in, and rate-limited two ways — a hard thermal ceiling and a 6-of-16
thread cap — so it only ever burns spare cycles and yields the moment anything else on
the box needs them. No botnet, nobody else's electricity. The draw is the legitimate
side of proof-of-work — the cryptography, and open research directions like
post-quantum (quantum-resistant) resilience — plus the small satisfaction of a miner
that behaves itself on a shared machine.

A RandomX CPU miner is the least important workload on the box, so the engineering
here is entirely about making it *safe to forget*:
[`run-safe-xmrig.sh`](run-safe-xmrig.sh) wraps the miner in a thermal contract.

- **Refuses to start** above 82 °C, and a watchdog loop kills the miner if the CPU
  crosses it while running.
- After any exit — crash, OOM, watchdog kill — it **holds in a cooldown loop** until
  the CPU is back under 70 °C, then exits nonzero so
  [systemd restarts the cycle](xmrig.service) (`Restart=always`, `Nice=10`).
- Handles the RandomX prerequisites (hugepages, MSR module) itself.

The `wait -n` unwind is the neat part: the script waits on *either* the miner or the
watchdog exiting, then tears both down — one code path for every failure mode.

Pool config (`config.json`, holds the wallet) stays out of the repo. Thread count is
capped at 6 of 16 so mining never contends with the [pinned game cores](../../docs/architecture.md#compute-isolation)
or the media stack.
