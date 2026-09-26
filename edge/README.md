# Edge

The VPS half of the lab: TLS terminates at the edge and rides a WireGuard tunnel
home, so the home network exposes nothing directly. Full path + firewall model in
[docs/architecture.md](../docs/architecture.md#the-edge-path).

- [`Caddyfile`](Caddyfile) — every HTTPS vhost, reverse-proxied to the box's tunnel
  address (`10.0.0.2`). Caddy manages certificates itself.
- [`milkhaus.net/`](milkhaus.net) — tracked pages of the static root site Caddy serves from
  `/var/www/milkhaus` on the VPS (so far only `teto/`); copy a page there to deploy it.
- **Game traffic bypasses Caddy entirely** — iptables DNAT rules (persisted with
  `netfilter-persistent`) forward the game ports over the same tunnel. Illustrative
  rule shape:

  ```sh
  # UDP game port → the box over wg0 (repeat per port; Minecraft is TCP)
  iptables -t nat -A PREROUTING  -i <wan-nic> -p udp --dport 34197 -j DNAT --to-destination 10.0.0.2
  iptables -t nat -A POSTROUTING -o wg0       -p udp --dport 34197 -j MASQUERADE
  ```

- Opening a new game port takes **three** layers: the provider's cloud firewall
  (filters upstream of the instance — drops never even reach `tcpdump`), `ufw`, and
  the DNAT rule. Verify from an unrelated network before blaming the game server.
- Game subdomains are DNS-only (grey cloud): a proxied record carries HTTP(S) only
  and silently eats game UDP.
