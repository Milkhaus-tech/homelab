# Virtual desktop

A desktop on servers that have no monitor. I stream it to my phone, and scripts use the
browser on it. When a script gets stuck on a login, 2FA or a captcha, it messages me
and I clear it from my phone.

**Runs on:** noahlab (the main desktop) and jesus (the extra ones) ([the boxes](../README.md#the-boxes)) · **Reachable from:** Tailscale and the LAN only, never port-forwarded

## How it works

- **The main desktop.** noahlab logs itself in at boot and runs `startx`, so there's no
  display manager. XFCE runs on the GPU, [Sunshine](https://github.com/LizardByte/Sunshine)
  streams it, and I watch it with [Moonlight](https://moonlight-stream.org/) on my phone.
- **The browser.** [`bin/vd-browser`](bin/vd-browser) keeps one Chromium open and signed
  in. Scripts drive it through Chrome's debugging port (CDP) on `127.0.0.1:9222`. That
  port controls every account the browser is logged into, so it only listens on localhost.
- **Extra desktops.** [`bin/vd-desktop`](bin/vd-desktop) starts virtual screens on jesus,
  each with its own browser: an everyday one for my fantasy football bot, one that only
  exists around a live draft (a draft can't be redone), one for timed store drops, and a
  scratch one ([why not one per league](../docs/incidents.md#too-many-browsers-ran-noahlab-out-of-memory)).
- **Input for the extra desktops.** Virtual screens have no input of their own.
  [`bin/vd-input-bridge`](bin/vd-input-bridge) grabs the keyboard, mouse and touch
  devices each stream creates and replays them into the right screen.
  [`bin/vd-pair-sync`](bin/vd-pair-sync) copies my phone's pairing to every Sunshine, so I
  only type a PIN once.
- **Asking for help.** A stuck script runs `vd-flag "what it needs"`
  ([script](bin/vd-flag)) and stops. My assistant bot on jesus sends it to me on Telegram, or by text if that
  fails. A nonzero exit means nothing went out.

## Worth knowing

- Keep `xserver-xorg-input-libinput` installed. Without it the stream shows video but
  ignores every tap and key
  ([what happened](../docs/incidents.md#the-desktop-stream-had-video-but-no-input)).
- The `startx` hook is in `~/.profile`. Don't create a `~/.bash_profile`: bash reads that
  one instead, and the desktop won't start.
- Change resolution with `xrandr -s 1920x1080`. `xrandr --output DP-0 --mode` fails on
  this driver when going smaller.

## Files

| File | What it is |
|---|---|
| [`xorg.conf`](xorg.conf) | Tells the NVIDIA driver a monitor is plugged in when there isn't one |
| [`xinitrc`](xinitrc) | Starts XFCE, Sunshine and the browser |
| [`systemd/getty-autologin-override.conf`](systemd/getty-autologin-override.conf) | Autologin on tty1 |
| [`systemd/sunshine.service`](systemd/sunshine.service) | Sunshine for the main desktop |
| [`bin/vd-browser`](bin/vd-browser) | Starts the signed-in Chromium, or does nothing if it's already up |
| [`bin/vd-desktop`](bin/vd-desktop) | `start` / `stop` / `status` for the extra desktops |
| [`bin/vd-input-bridge`](bin/vd-input-bridge) | Sends each extra desktop's input to the right screen |
| [`bin/vd-pair-sync`](bin/vd-pair-sync) | Copies Moonlight pairings to every Sunshine |
| [`bin/vd-flag`](bin/vd-flag) | The "I need a human" message |
| [`bin/audible-desktops`](bin/audible-desktops), [`bin/audible-warroom`](bin/audible-warroom), `systemd/audible-*` | Glue for the fantasy football bot (its code name is Audible): keeps its everyday desktop up, and checks every minute whether a draft is coming so it can start the draft desktop |
