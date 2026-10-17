# Information checklist

Gather these before you prompt an AI assistant. Keep the answers in a private note. **Never paste passwords, keys, tokens or your real ntfy topic into a chat.** Use explicitly non-operational placeholders such as `x-topic`, `x-token`, `x.x.x.x` and `xx:xx:xx:xx:xx:xx`; add real values only to ignored private configuration. Role labels such as `edge-scout-1` are public pseudonyms, not real host identities.

## 1. Your goal, in one sentence
Example: "Tell my phone when a machine on my home network goes offline, and send me one summary each morning."

## 2. Your machines (one line each)

| Field | Example | Needed for |
|---|---|---|
| Name you choose | `edge-scout-1` | Alerts and state |
| Role | "Edge scout", "Windows hub", "AI box" | Reports, so they read by function |
| Operating system | Pop!_OS, Debian, Windows 11, Android | Which probe and agent to use |
| Always on, sleeps, or travels? | "sleeps", "travels" | Whether it may be woken, and how loud its alerts are |
| MAC address | `xx:xx:xx:xx:xx:xx` (non-operational) | Identity-first lookup |
| Mesh or VPN hostname | `my-laptop` | Fallback when it is off the LAN |
| Probe port | 22 (SSH), 3389 (remote desktop) | The "is it alive" check |
| Allowed to be woken? | yes/no | `wake_required` |
| Remote access works? | yes/no/unknown | Whether heartbeats can be collected |

## 3. Your network
- Router or gateway make and whether you can read a client list from it.
- Whether there is a network controller (TP-Link Omada, UniFi or similar) with an API.
- Which segments exist (main, IoT, guest). Roles only. Keep ranges private.
- Uplinks: cable, satellite, cellular, and whether there is a failover.
- Your mesh or VPN overlay, if any (Tailscale, WireGuard, none).

## 4. The hub
- The always-on Linux machine that will poll. OS version. Python 3.9 or newer.
- Can it send outbound HTTPS? (needed for ntfy)
- Is systemd available? (`systemctl --user status`)

## 5. Alerts
- Which events matter: device joined or left, node down, internet down, daily summary.
- Quiet hours, if any.
- Who receives them (one phone, or several subscribers to the same topic).
- Public ntfy server, or self-hosted with a token.

## 6. Limits and safety
- Machines the AI must never touch.
- Whether any automatic action is allowed at all. Recommended answer: **no, dry-run only** until you have read the output.
- Anything you do not want in a message: addresses, hardware identities, names of people.

## 7. What you will test with
- One machine you can switch off safely.
- One machine that is asleep, to test wake-up.
- A second phone, to test a second subscriber.
