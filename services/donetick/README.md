# Donetick

The household chore chart. [Donetick](https://donetick.com) is a small self-hosted app
with recurring chores and reminders.

**Runs on:** noahlab ([the boxes](../../README.md#the-boxes)) · **Reachable from:** Tailscale and the LAN only · **Talks to:** [Home Assistant](../home-assistant/)

## How it works

Donetick's own push notifications need HTTPS and web push, which I skipped. Instead,
Donetick calls a webhook for the household (it calls that a circle), the webhook goes to
Home Assistant, and [an automation](../home-assistant/automations.yaml) turns it into a
phone notification: reminders go to whoever the chore belongs to, and when I finish one
the other person in the house gets a "done" message with a link back to the list. My own
reminders come through my assistant bot instead.

## Worth knowing

- Signup is turned off. To add a user, flip it on, make the account, flip it back.
- The webhook isn't signed, so the Home Assistant side only accepts it from the LAN.
- The JWT secret comes from [`.env`](.env.example). Changing it logs everyone out.
- The data folder stays owned by my user so the nightly backup can read it.

## Files

| File | What it is |
|---|---|
| [`docker-compose.yml`](docker-compose.yml) | Donetick, pinned to v0.1.76 |
| [`.env.example`](.env.example) | The JWT secret |
