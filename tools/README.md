# Publishing pipeline

This repo is public; the live tree it mirrors is full of credentials. These two
scripts are the boundary between them.

## [`sync-from-live.sh`](sync-from-live.sh)

Re-exports every published file from its live location (`/opt/*`, `~/docker/*`,
`~/bin`, systemd units) and applies redaction **as patterns, never literal values** —
inline credentials become `${VAR}` / `{FRIGATE_*}` templates documented by
`.env.example` files, webhook ids and stream credentials become placeholders.
Substitutions that would themselves reveal a private string (renaming a person, say)
are read from `tools/.private-tokens`, an untracked `old=new` map — the mechanism is
public, the names aren't.

Why an export script instead of hard links or a shared checkout: a hard-linked file
can't be redacted without editing the shared inode (corrupting the live config) or
breaking the link (silently drifting). A copy with mandatory transforms + a verifier
is the version of "linked to live" that can't leak.

## [`verify-no-leaks.sh`](verify-no-leaks.sh)

Runs automatically at the end of every sync; a hit fails the sync. Two independent
nets:

1. **Pattern sweep** (also runs in CI): JWT shapes, private-key blocks, inline
   RTSP stream credentials, webhook ids, and any value-bearing
   password/secret/token/key assignment that isn't an approved placeholder.
2. **Value sweep** (lab box only): harvests the *actual* secret values from the live
   stores — env files, secret yaml/toml, password hashes, wallet, plus
   identity/topology strings (mesh addresses, the VPS address, private names) — and
   asserts none appear in any file git would publish, including URL-encoded forms.
   Hits print the source label and offending file, **never the value**.

CI re-runs the pattern net plus [gitleaks](https://github.com/gitleaks/gitleaks) on
every push, so a bad manual commit gets caught even if it skipped the sync path.

## Adding a file to the publish set

Add a mapping line in `sync-from-live.sh` (plus transform rules if it carries
secrets) and re-run. New secret *shapes* that no rule covers are the failure mode the
verifier exists for: the sync dies loudly and the fix is a new rule, not a manual
edit to the exported copy.
