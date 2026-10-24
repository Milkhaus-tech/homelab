# Publishing pipeline

This repo is public, and the live configs it's copied from are full of passwords. These
two scripts sit in between.

**Runs on:** noahlab, by hand whenever I update the repo · CI runs the pattern check on every push

## How it works

- [`sync-from-live.sh`](sync-from-live.sh) copies every published file from the box it
  runs on (over ssh for jesus) and swaps the secrets out on the way. The rules are
  patterns, never real values: inline credentials become `${VAR}` or `{FRIGATE_*}`
  placeholders with a matching `.env.example`. Renames that would give away a private
  string by themselves, like a person's name, come from `tools/.private-tokens`, an
  untracked `old=new` list. The mechanism is public, the names aren't.
- [`verify-no-leaks.sh`](verify-no-leaks.sh) runs at the end of every sync, and any hit
  fails it. It checks two ways:
  1. **Patterns** (also runs in CI): JWTs, private keys, logins inside stream URLs,
     webhook ids, and any password/secret/token/key assignment that isn't a placeholder.
  2. **Real values** (only at home, where the real secrets are): it reads the actual
     secrets from every box's env files, configs and key files, plus the Tailscale
     addresses, the VPS address and the private names, and makes sure none of them show
     up in any file git would publish. A hit prints where the secret came from and which
     file it landed in, never the value.
- CI also runs [gitleaks](https://github.com/gitleaks/gitleaks) on every push, so a bad
  manual commit gets caught even if it skipped the sync.

## Worth knowing

- Why copies and not hard links: you can't redact a hard-linked file without editing the
  live config, and a link that breaks just drifts. A copy plus a checker fails closed: a
  new kind of secret stops the sync instead of slipping through.
- To publish a new file, add a line to `sync-from-live.sh` (plus redaction rules if it
  has secrets) and re-run it. Don't fix an exported copy by hand, because the next sync
  overwrites it.
