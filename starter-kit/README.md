# Fleet starter kit

A small, tested, standard-library-only toolkit that reproduces the core loop of the Seravo-0 network on your own hardware:

- **Poll** every machine you care about and find it by hardware identity first.
- **Alert your phone** through [ntfy](https://ntfy.sh), on state changes only.
- **Report** once a day, in the same style as the real project.
- **Wake** machines that are allowed to be woken (dry-run by default).
- **Heartbeat** from each client so silence gets noticed.
- **Assess project maintenance** from tracked documentation hashes and reviewed local evidence, without running ingested commands or external connectors.
- **Maintain two documentation tiers** with [local staged exports](../docs/private-public-docs.md),
  human-vetted public Markdown and an owner-only Seravo-0 knowledge index. No automatic
  model connection, commit or public upload is performed.

It does not include any AI model, network controller integration or the author's real configuration. Start with the [safe adopter workflow](#safe-adopter-workflow) and [INFORMATION_CHECKLIST.md](INFORMATION_CHECKLIST.md), then use [PROMPT_GUIDE.md](PROMPT_GUIDE.md) to review adaptations with an assistant.

**Not deployment proof:** installed units, a matching documentation hash and a configured connector entry do not establish live service health. Missing, invalid or stale required evidence yields `ATTENTION` and a nonzero project-check exit. Rave remains planned/disabled with no verified connector; see [project maintenance](../docs/monitoring-and-protection.md#connectors-and-rave).

Read [SCRIPT_GUIDE.txt](SCRIPT_GUIDE.txt) for every Python/shell script's blocks, inputs, outputs, prerequisites and side effects.

## What is in the box

```
README.md                    this file
PROMPT_GUIDE.md              prompts to paste into an AI assistant, in order
INFORMATION_CHECKLIST.md     the facts to gather before you prompt
SCRIPT_GUIDE.txt             complete script/block and connector reference
install.sh                   per-user install of files and systemd timers (nothing runs as root)
fleetctl.py                  standard-library adoption, SSH verification and owned-file lifecycle
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
  docs_publish.py            private-to-public Markdown staging, review checks and local index
config/
  fleet.env.example          your ntfy topic and site name
  fleet_manifest.example.json  your inventory, by role
  maintenance.example.json   required checks, age limit and connector implementation policy
systemd/                     poll, heal, daily, heartbeat and optional hourly project units
tests/                       standard-library unittest checks
```

## Safe adopter workflow

For private mesh/farm.net/Seravo-0 knowledge, follow the
[two-tier documentation workflow](../docs/private-public-docs.md).
`python3 fleetctl.py docs --help` lists the local-only `stage`, `apply`, `check` and
`index` actions. Private publishing configuration is separate from adopter userconfig;
it is never included in deployments. Configure `documentation_publish_config` in the
private maintenance policy or reports intentionally remain at ATTENTION.

Review the [threat model](../docs/monitoring-and-protection.md#adopter-threat-model) first. Python 3.9+ uses only the standard library; applied installation needs Linux, a systemd user session and writable user-owned directories. Remote adoption additionally needs OpenSSH `ssh`, `scp`, `ssh-keyscan`/`ssh-keygen` for explicit fingerprint trust, key-based login and remote Python/systemd. No root, sudo, passwords or agent forwarding are used. This is an operator-run workflow, not unattended deployment.

**Every `x-…` identifying value below is masked and explicitly non-operational.** Replace it privately; never run the examples unchanged. `hub`/`client` and the default unit prefix `fleet` are public role/default labels.

1. **Choose names and paths before installing.** Kit name, unit prefix, hub/client labels and node name must match `^[a-z][a-z0-9-]{0,31}$`. Default settings are kit/prefix `fleet`, installation `~/fleet-kit`, role `hub`, labels `hub`/`client`. Use a distinct prefix and directory for a separate installation; prefixes name units such as `fleet-poll.timer`. The destination must be strictly below the target user's home, absolute or `~/`-relative, without spaces, traversal, symlinks or writable ancestors. Client operations require an explicitly chosen `--node-name`; a kit label is not device identity.
2. **Initialise private choices** from `starter-kit/`:

   ```sh
   python3 fleetctl.py init --output state/x-adopter.json \
     --kit-name x-kit --unit-prefix fleet --install-dir /home/x-user/x-kit \
     --role hub --hub-label hub --client-label client --host x-user@x-host
   ```

   `init` creates a mode-0600 JSON file exclusively; it refuses an existing output and does not install or contact a host. `state/` is ignored in this checkout; protect that directory too. `--userconfig state/x-adopter.json` loads it on later commands; explicit options override saved choices. For a client choose `--role client --node-name x-node` at initialisation. Do not edit identity choices between deployment and uninstall: retain the original userconfig.
3. **Prepare and check private runtime configuration.** Edit `config/fleet.env` and, for a hub, `config/fleet_manifest.json` from reviewed examples; keep files mode 0600 and private directories mode 0700, owned by the acting user. The examples deliberately contain invalid placeholders. Remove or privately replace all runtime placeholders; validate names, MACs, ports and permitted destinations yourself. Do not put shell expressions into `fleet.env`: it is parsed as data, never sourced.

   ```sh
   python3 fleetctl.py check --userconfig state/x-adopter.json
   ```

   This reads local config without network or service changes; it is not a live health check. Config files are **not transferred by default**. Prepare destination config privately, or deliberately opt in to each exact permitted filename with repeated `--include-config fleet.env`, `--include-config fleet_manifest.json` or `--include-config maintenance.json`. Never include private keys, archives or state.
4. **Verify SSH identity separately.**

   ```sh
   python3 fleetctl.py connect --userconfig state/x-adopter.json
   ```

   SSH is noninteractive: `BatchMode=yes`, `StrictHostKeyChecking=yes`, `ForwardAgent=no`, password and keyboard-interactive authentication disabled. Unknown/changed keys halt. Pre-provision independently verified known-hosts entries, or explicitly use `--trust-host-key --expected-fingerprint SHA256:x-out-of-band-fingerprint` after obtaining the actual fingerprint through a separate trusted channel. That masked fingerprint is intentionally invalid. The trust option matches the scanned key against the supplied fingerprint and uses a temporary, private per-operation known-hosts file; it is not automatic TOFU or a global trust change. `connect` runs a fixed remote Python home/UID check, not a deployment.
5. **Review the exact plan, then approve deployment.**

   ```sh
   python3 fleetctl.py deploy --userconfig state/x-adopter.json
   python3 fleetctl.py deploy --userconfig state/x-adopter.json --apply
   ```

   The default deploy prints the exact source-file SHA256 manifest and changes no files, network or services. `--source` selects a reviewed kit tree, not an arbitrary archive installer. Applied deployment stages only a fixed public-file whitelist (plus explicitly selected config), rejects unknown/missing entries and verifies checksums before installation. Checksums prove integrity, **not authenticity**: review source/provenance independently. Applied installation writes files and generated user units, records ownership in `.fleetctl-installed.json` and reloads the user daemon. It never creates a backup.
6. **Inspect before activating.** `python3 fleetctl.py status --userconfig state/x-adopter.json` compares recorded files with installed bytes; it is not live fleet/service-health evidence. Units stay disabled by default. Only `deploy --apply --enable` requests entrypoint activation; review the activation limitations below first. `--send` separately permits poll/daily delivery. Neither flag authorises live Wake-on-LAN, external connectors, lingering or AI actions. Configure genuine project evidence separately; installing units cannot promote a connector to verified.

   Explicit activation selects hub poll/daily timers or the client heartbeat timer; the project timer is eligible only with `--repo` pointing to an existing reviewed target-side Git checkout. The heal timer is never selected by `--enable`, and its generated service has no live-wake `--apply`. A deployed kit tree is not that Git checkout. Configure destination runtime files before approval (or explicitly select their transfer) and retain the original deployment choices for lifecycle commands. Reinstalling without `--enable` does not stop timers you previously enabled; inspect their real state with `systemctl --user status` before making changes.

### Reinstallation, rollback and uninstall

Repeat only with the same choices and unchanged managed bytes: matching owned files are idempotent, while unowned collisions or changed managed files halt rather than being overwritten. An edited/private config is not silently reset. This is not an in-place upgrade/merge or backup mechanism; inspect conflicts and preserve needed data yourself before any deliberate replacement.

Review `python3 fleetctl.py uninstall --userconfig state/x-adopter.json` first; add `--apply` only after inspecting its ownership-bound removal plan. Uninstall removes only recorded, unchanged managed content, not arbitrary directory contents; private configuration, modified files and runtime state need separate operator review. Do not use a recursive directory deletion as rollback. For a failed partial deployment, inspect the reported files/staging location before retrying; retained data is not a backup.

### Local install compatibility

`./install.sh` (hub) and `./install.sh client --node-name x-node` remain supported local entrypoints through the same installer. The client node placeholder must be replaced privately. The wrapper never enables timers and does not support `--enable`; it is not an alternative trust/overwrite bypass. Inspect generated units and edit private config before manual activation. Use `fleetctl.py status`/`uninstall` with matching installation choices for owned-file inspection/removal.

## Runtime setup after adoption

1. **Install ntfy on your phone** (Android or iOS) and subscribe to a long random topic name. Generate one:
   ```
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
   The generated value is private runtime data, not a public example; never paste it into prompts or shared output.
2. **Get the kit** onto the hub machine (the always-on Linux box that will do the polling):
   ```
   cd starter-kit && ./install.sh
   ```
   The local wrapper installs runtime files to `~/fleet-kit`, creates initial private example config only when absent, and installs user units without enabling them. The project unit needs a reviewed repository path before activation; an unconfigured path is not deployment evidence.
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
7. **Validate the reviewed source checkout:** from its `starter-kit/` directory, run `python3 -m unittest discover -s tests`. Tests are not copied into a runtime installation; this result is not deployment evidence.
8. **Enable timers** once the dry-run looks right:
   ```
   systemctl --user enable --now fleet-poll.timer fleet-daily.timer
   ```
   Lingering is a separate policy decision, not a setup prerequisite; review the threat table before an administrator permits timers after logout.
9. **On each client** (optional but recommended): `./install.sh client --node-name x-node` with a privately chosen node name, inspect the generated heartbeat service, then enable `fleet-heartbeat.timer`. Make the hub collect the file into `state/heartbeats/` with an independently approved transfer mechanism.

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

The hub installer supplies the optional hourly `fleet-project.timer` without collecting external evidence. Installation and activation are distinct approvals: the default and legacy wrapper leave units disabled; only the adopter's explicit `deploy --apply --enable` can request activation. Inspect the repository path, configuration and results first. No text found in evidence, Markdown or ingest content is executed.

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
