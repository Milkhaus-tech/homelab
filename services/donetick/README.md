# Donetick

Self-hosted chore chart for the household. SQLite-backed, LAN/Tailscale only, with
signup disabled — adding a user means temporarily flipping the flag.

The interesting part is the notification path: Donetick's own push needs HTTPS + web
push, which this deployment skips. Instead its circle webhook posts to a
`local_only` Home Assistant webhook, and
[an automation](../home-assistant/automations.yaml) routes by event type —
`task.reminder` goes to the **assignee's** phone (pre-due / due / overdue titles),
`task.completed` notifies the *other* partner, with a deep link back to the chore
list. The webhook carries no signature, hence `local_only` and the LAN threat model.

The JWT secret is overridden from [`.env`](.env.example) (verified against issued
tokens — the yaml placeholder is intentionally not a secret); rotating it logs
everyone out. The data dir stays owned by the login user so the nightly backup can
read it.
