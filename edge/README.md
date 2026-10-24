# Edge

The VPS side of the lab. HTTPS ends here and rides WireGuard home, so my home network
doesn't expose anything directly.

**Runs on:** the VPS ([the boxes](../README.md#the-boxes)) · **Reachable at:** every public site except the two on the Cloudflare tunnel ([see architecture](../docs/architecture.md#websites)), plus the game ports

- [`Caddyfile`](Caddyfile) is every HTTPS site. Each one proxies over WireGuard to the
  box that runs it (`10.0.0.2` noahlab, `.3` jesus, `.4` pablo), or serves a static site
  straight off the VPS. Caddy handles the certificates itself.
- [`milkhaus.net/`](milkhaus.net/) holds pages of the main site that live in this repo
  (just `teto/` so far). Deploying one means copying it to `/var/www/milkhaus` on the VPS.
- Game traffic skips Caddy. `iptables` forwards each game port over the same tunnel,
  saved with `netfilter-persistent`:

  ```sh
  # one pair per port (Minecraft Java is TCP, the rest are UDP)
  iptables -t nat -A PREROUTING  -i <wan-nic> -p udp --dport 34197 -j DNAT --to-destination 10.0.0.2
  iptables -t nat -A POSTROUTING -o wg0       -p udp --dport 34197 -j MASQUERADE
  ```

Which site goes where, the firewall gotchas for new game ports, and why game
subdomains have to be DNS-only are all in
[docs/architecture.md](../docs/architecture.md#how-traffic-gets-in).
