# ntfy integration: how the network talks to the phone

[ntfy](https://ntfy.sh) is an open-source push-notification service. Seravo-0 and its scheduled jobs publish to a private topic, and the operator's phone (and any approver's phone) subscribes to it. It is the network's voice in the field. No inbound port is opened on the network: everything is outbound HTTPS from the hub to the notification server.

Topic names, server settings and tokens are `[REDACTED]`. A topic name on the public server works like a password, so treat it as one.

## Design goals

| Goal | How it is met |
|---|---|
| One look for every message | A single shared formatter builds every push: emoji, tags, priority, bold headline, bullets, meters, and a footer with site, host and time. |
| One delivery path | Every job calls the same send function, so retries, size limits and the spool behave the same everywhere. |
| Never lose a report | Failed sends are retried three times (immediately, then after 2 s and 6 s), then written to a small on-disk spool. The spool is flushed on the next send. The daily report warns if messages are waiting in it. |
| UTF-8 safe | Messages go through ntfy's JSON publish API, not HTTP headers, so titles and bodies can carry emoji and any language. |
| Fits a phone | Bodies are capped at about 3.8 KB and cut at a line break with a "truncated" marker. |
| Quiet by design | Alerts fire on state change only, not on every check. A node that stays down gets one reminder a day, not one an hour. |
| Priority means something | Priority is chosen by the kind of event, so urgent only ever means urgent. |

## Message anatomy

```
Title:    <site> · <HEADLINE>
Priority: 1-5 (chosen by event kind)
Tags:     emoji shortcodes that the app renders as icons
Body:     markdown
            ## <emoji> <HEADLINE>
            one-line summary or bulleted facts
            key/value details
            *<site> · <host> · <timestamp>*
```

## Event kinds and priorities

| Kind | Fires when | Priority |
|---|---|---|
| Client connect / disconnect | A device joins or leaves the network. | Default |
| Mesh node online / offline | A node appears on or drops from the encrypted overlay. | Default / High |
| Internet uplink drop | An uplink goes offline. Says whether traffic failed over or all uplinks are down. | **Urgent** |
| Internet uplink restore | An uplink returns. | Default |
| Unknown device | Something nobody has seen before shows up, including devices seen only on the switch mirror port. | High |
| Traffic anomaly / bottleneck | The gateway telemetry watcher sees a spike or a choke point. | Default / High |
| Fleet healing | The healer woke or recovered nodes, and says which are still down. | Default, High if any did not recover |
| IoT reconnect watch | A watched IoT device is absent too long, failed its address request, or rejoined (with the measured delay). | High |
| Weak-signal reconnects | The signal optimiser reconnected a weak Wi-Fi client. | Low |
| Online but not polled | A client is on the network but has not yet been brought under management. | Default |
| Log capacity | A log or the vault is filling. | High |
| Report failure | A scheduled report crashed. The failure itself is pushed. | High |
| Scheduled reports | Morning briefing, daily status, hardware overview, stack report, nightly audit, fleet census, link-speed poll. | Default (High or urgent when attention is needed) |
| Test | A delivery check. | Low |

Examples of each are in [report-examples.md](report-examples.md).

## What reaches the field

Three layers, from most to least frequent:

1. **Events** (state changes): a device joined, an uplink dropped, a node woke. Within about two minutes of the change.
2. **Reports** (scheduled): a morning briefing, a daily status, a hardware and a stack overview, a fleet census, a nightly audit with a short AI analysis, and a link-speed poll every few hours. See [polling.md](polling.md) for the timetable.
3. **Approvals**: when Seravo-0 wants to do something consequential, the request goes to the approver's phone, and nothing runs until a person says yes.

## Reading the priority on a phone

| Priority | Phone behaviour (typical) | Use |
|---|---|---|
| 5 urgent | Sound, vibrates, can override Do Not Disturb | Internet down, all uplinks lost |
| 4 high | Sound and pop-up | Node offline, unknown device, healing failed |
| 3 default | Sound | Normal events and reports |
| 2 low | No sound | Test messages, weak-signal reconnects |

## Keeping it safe

- **The topic is a secret.** Use a long random name. For anything beyond a hobby network, self-host the server and require a token.
- **Do not put secrets in messages.** Reports show roles, names and counts. Network addresses and hardware identities are shown only where the operator needs them, and are redacted in every example in this repository.
- **A pushed message is not a command.** Seravo-0 never reads its own notifications back as instructions.
- **Quarantine, not copy.** Anything that looks like a credential is stopped before it reaches any repository or message.

## Build your own

The [starter kit](../starter-kit/README.md) contains a standard-library-only version of this publisher, with retries, spool, size cap, styles and a dry-run default.
