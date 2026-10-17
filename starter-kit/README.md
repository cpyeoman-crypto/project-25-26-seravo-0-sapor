# Fleet starter kit

A small, tested, standard-library-only toolkit that reproduces the core loop of the Seravo-0 network on your own hardware:

- **Poll** every machine you care about and find it by hardware identity first.
- **Alert your phone** through [ntfy](https://ntfy.sh), on state changes only.
- **Report** once a day, in the same style as the real project.
- **Wake** machines that are allowed to be woken (dry-run by default).
- **Heartbeat** from each client so silence gets noticed.
- **Assess project maintenance** from tracked documentation hashes and reviewed local evidence, without running ingested commands or external connectors.

It does not include any AI model, network controller integration or the author's real configuration. It is the skeleton you tweak, with an AI assistant, into a build of your own. Start with [PROMPT_GUIDE.md](PROMPT_GUIDE.md) and [INFORMATION_CHECKLIST.md](INFORMATION_CHECKLIST.md).

**Not deployment proof:** installed units, a matching documentation hash and a configured connector entry do not establish live service health. Missing, invalid or stale required evidence yields `ATTENTION` and a nonzero project-check exit. Rave remains planned/disabled with no verified connector; see [project maintenance](../docs/monitoring-and-protection.md#connectors-and-rave).

Read [SCRIPT_GUIDE.txt](SCRIPT_GUIDE.txt) for every Python/shell script's blocks, inputs, outputs, prerequisites and side effects.

## What is in the box

```
README.md                    this file
PROMPT_GUIDE.md              prompts to paste into an AI assistant, in order
INFORMATION_CHECKLIST.md     the facts to gather before you prompt
SCRIPT_GUIDE.txt             complete script/block and connector reference
install.sh                   per-user install of files and systemd timers (nothing runs as root)
build_package.sh             builds fleet-kit.zip from this folder
requirements.txt             none: Python 3.9+ standard library only
src/
  ntfy_notify.py             styled publish, retries, disk spool, size cap, dry-run by default
  resolver.py                MAC first, mesh second, last-known address last
  fleet_poll.py              the poll loop; alerts on state change only; writes state/fleet_status.json
  heartbeat.py               client health file for the hub to collect
  wol_healer.py              Wake-on-LAN for wake_required nodes, dry-run unless --apply
  daily_status.py            the daily report
  project_monitor.py         read-only local repo/evidence assessment; writes project status
config/
  fleet.env.example          your ntfy topic and site name
  fleet_manifest.example.json  your inventory, by role
  maintenance.example.json   required checks, age limit and connector implementation policy
systemd/                     poll, heal, daily, heartbeat and optional hourly project units
tests/                       standard-library unittest checks
```

## Quick start (about 15 minutes)

1. **Install ntfy on your phone** (Android or iOS) and subscribe to a long random topic name. Generate one:
   ```
   python3 -c "import secrets; print('mynet-' + secrets.token_urlsafe(18))"
   ```
2. **Get the kit** onto the hub machine (the always-on Linux box that will do the polling):
   ```
   cd starter-kit && ./install.sh
   ```
   This copies runtime files and `SCRIPT_GUIDE.txt` to `~/fleet-kit`, creates `config/fleet.env` and `config/fleet_manifest.json` from the examples, and installs systemd user timers without enabling them. Hub suggestions include `fleet-project.timer`: edit its service's `--repo %h/xxxx-project` to your reviewed checkout before enabling it; the printed suggestion is not a ready-to-run configuration.
3. **Edit `config/fleet.env`:** set `NTFY_TOPIC` and `SITE_NAME`.
4. **Check delivery:**
   ```
   cd ~/fleet-kit && FLEET_ENV=config/fleet.env python3 src/ntfy_notify.py
   ```
   A test message should reach your phone. With no topic set, it prints instead of sending.
5. **Edit `config/fleet_manifest.json`:** one entry per machine, by role. Find MAC addresses with `ip link` on each machine, or from your router's client list. The public `x.x.x.x`, `xx:xx:xx:xx:xx:xx` and `x-mesh-host` values are non-operational; replace them privately before use. Never run against the example inventory unchanged.
6. **Dry-run notification delivery during a real poll** (probes and writes local state, but sends no alert):
   ```
   python3 src/fleet_poll.py --manifest config/fleet_manifest.json
   ```
   The first reachability observation seeds state; later reachability changes produce alerts. With `heartbeat_dir` configured, a missing, invalid or old heartbeat for a reachable node can alert on the first poll. Run it a second time, then stop one machine and run it again to see an alert.
7. **Run the tests:** `python3 -m unittest discover -s tests`
8. **Enable timers** once the dry-run looks right:
   ```
   systemctl --user enable --now fleet-poll.timer fleet-daily.timer
   loginctl enable-linger $USER
   ```
9. **On each client** (optional but recommended): `./install.sh client`, edit the `--name` and `--out` in `fleet-heartbeat.service`, then enable `fleet-heartbeat.timer`. Make the hub collect the file into `state/heartbeats/` with rsync, scp or a shared folder.

## How the pieces behave

| Behaviour | Detail |
|---|---|
| First run | Seeds reachability state without up/down alerts; a configured heartbeat that is missing, invalid or stale can still alert. |
| State change | Up to down and down to up each send one alert. A node that stays down sends one reminder per 24 hours. |
| Resolution order | LAN neighbour table (MAC), then mesh peer list (Tailscale if installed), then the last known address. |
| Unresolved node | Reported as down. Never sent work. |
| Heartbeat | When `heartbeat_dir` is configured, a missing/invalid heartbeat or one older than `heartbeat_max_age_min` marks a reachable node stale and sends one transition alert. |
| Wake-on-LAN | Only nodes marked `wake_required`, only with a MAC, only with `--apply`. |
| Delivery | Three tries, then a disk spool that is flushed on the next send. |
| Privacy | Messages carry roles and names. Keep addresses and hardware identities out of your own templates if you share screenshots. |

## Project maintenance (optional timer, manual activation)

Use the [maintenance contract](../docs/monitoring-and-protection.md#local-project-maintenance) to configure `config/maintenance.json` from the public policy example. Review every tracked and non-ignored new Markdown file (including the [root README maintenance conditions](../README.md#repository-maintenance-conditions)) before approving its SHA256 in evidence `docs`. Add genuine, fresh evidence in ignored `state/maintenance_evidence.json` for all `required_checks`. Do not replace absent observations with sample successes.

The private `config/maintenance.json` copy is ignored, not automatically loaded. The checker defaults to `config/maintenance.example.json`; select the private copy explicitly with `--config` and update the installed project service's arguments to match.

Follow the [manual evidence-authoring workflow](../docs/monitoring-and-protection.md#authoring-evidence-without-automatic-approval): `snapshot(repo)` supplies a checkout fingerprint and **candidate**, not approved, Markdown digests. Record real check outcomes/times against that fingerprint. Evidence connectors are keyed `ntfy` and `rave`; the sorted summary calls them connector-1 and connector-2. Rave remaining planned necessarily means `ATTENTION`/exit 1 and prevents daily `ALL GREEN`, even after the other checks pass.

The local checker writes `state/project_status.json`; daily reporting consumes it through `--project-state` and checks expected fleet members through `--manifest`. Each poll records node `checked_at`. Missing, partial, malformed or stale fleet/project evidence prevents an all-green report, even if the hub's own metrics look fine.

The hub installer copies the optional hourly `fleet-project.timer` but does not enable it or collect missing external evidence. Installation and timer activation are separate operations: edit the service's non-operational `--repo` path to your reviewed checkout, inspect configuration/results, then manually enable the timer. All existing timers remain disabled after installation too. No text found in evidence, Markdown or ingest content is executed.

## Adapting it

- **Different mesh overlay or none:** replace `read_mesh_peers()` in `src/resolver.py`. It returns `{name: address}`.
- **Controller or router integration:** add a poller beside `fleet_poll.py` that reads your controller's client list and diffs it the same way (see `poll_once` for the pattern). Keep it read-only.
- **A different probe:** `probe_port` in the manifest sets the TCP port. Use 22 for SSH, 3389 for Windows remote desktop, or the port of a service you care about.
- **More report sections:** add them in `daily_status.build_report`.
- **Self-hosted ntfy:** set `NTFY_SERVER` and `NTFY_TOKEN`.

## Safety rules the kit follows

- Network changes require explicit approval: Wake-on-LAN needs `--apply`. Polls make read-only network probes and write state even without `--send`; heartbeat and project checks also write their local output files. `--send` authorises notification delivery.
- Nothing runs as root. Timers run as your user.
- No secrets in the repository: `fleet.env`, the real manifest and state are git-ignored.
- Do not point it at networks or machines you do not own or administer.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Nothing arrives on the phone | `NTFY_TOPIC` empty (dry-run), topic mismatch with the app, or the hub has no internet. Check `/var/tmp/fleet-kit-ntfy-spool-*.jsonl`: a backlog means delivery is failing. |
| Every node shows down | The neighbour table has no entry yet. Ping the node once, or add `last_known_address` as a fallback. A different subnet needs the mesh overlay. |
| Discovery failed | An installed LAN/mesh discovery command failed; inspect its local configuration and permissions. This is not silently treated as an empty healthy fleet. |
| A sleeping laptop is always "down" | Expected. Mark it `wake_required` if it should be woken, otherwise accept the alert or lower its priority in your own copy. |
| Duplicate alerts | Two hubs running the same timer. Keep one. |

Licence: use it however you like, at your own risk.
