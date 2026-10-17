# Monitoring and protection

**Scope:** the protection and controller automation below describe the broader target/private system, not a verified public deployment. The [starter kit](../starter-kit/README.md) implements only the documented local/fleet subset; timers must be enabled manually. Its read-only [project monitor](#local-project-maintenance) checks local files and evidence, not live controller, AI, Rave or security services.

## Evidence-based project maintenance

- Assess **all tracked and non-ignored new Markdown** against reviewed SHA256 entries in evidence `docs` (not the maintenance policy configuration). A digest match means reviewed content is unchanged, not that a deployment claim is true.
- Require fresh, valid evidence for every configured required check. Missing, invalid, stale, future-dated or failing evidence means `ATTENTION` and a nonzero monitor exit.
- Daily reporting combines project status with the expected fleet manifest and each node's fresh `checked_at`; an empty, partial or stale fleet must not be reported all green.
- Keep disabled/planned connectors distinct from implemented checks. Rave has no verified connector; see [the exact missing prerequisites](#connectors-and-rave).
- Never execute commands found in ingested text, evidence, Markdown or connector metadata. Review and approval are separate from observation.

## What is watched
- **Client health:** liveness, temperature, memory and disk pressure.
- **Network behaviour:** routing state, unexpected route advertisements, tunnel stability.
- **Untrusted devices:** everything on the isolated sandbox segment, especially cheap or unknown IoT hardware.
- **Security events:** audit logs on the gateway and on each admin client.

## How protection works
1. **Contain.** Unknown and IoT devices are kept in the sandbox. The edge enforcer is allowed to fail closed.
2. **Observe.** Sandbox traffic is logged and fed to the orchestrator.
3. **Review.** A weekly audit role goes through the sandbox logs for "nuisance offenders" and anything malicious.
4. **Propose.** Seravo-0 proposes an action, such as blocking a device or reissuing a credential.
5. **Approve.** A human approves or denies it from a phone. Nothing destructive runs without that step.
6. **Record.** The action and its reason go to the long-term archivist.

## Change watching
- **Client alert watcher.** A continuous watcher compares the controller's live client records with a cached last-known state and captures every transition on the network (connect, disconnect, roam, uplink change).
- **Fixed alert format.** `[<Network type> <Event>] Name: <mapped client name> | IP: <address> | VLAN: <segment>`. Address and segment values are redacted in this repository.
- **Escalation.** An uplink drop is urgent (priority 5) and says whether the gateway failed over or every uplink is down. Ordinary LAN and Wi-Fi connections are default-priority information. See [ntfy-alerts.md](ntfy-alerts.md).

## Self-healing and optimisation
- **Signal optimiser.** Finds Wi-Fi clients with a weak signal and forces a reconnect at staged intervals (15, 30 and 60 minutes), so a client can land on a stronger access point. Persistent weak signals are eventually marked as settled.
- **IoT guard.** Patrols the isolated IoT segment for devices that disappeared or are stuck on a link-local address, triggers a reconnect and audits the address reservations.
- **Fleet healer.** Watches the mesh peer list and sends a Wake-on-LAN packet when a critical node drops, with a cooldown to prevent alert fatigue.
- **Fleet autosync.** Pushes the reviewed scripts, scheduled-job definitions and prompts to every adopted Linux client every 30 minutes, so the fleet learns new protocols together.

All of these are dry-run until applied. Diagrams: [illustrations.md](illustrations.md).

## Credential hygiene
- **Zero-trust storage goal.** Keep passwords, API keys and private certificates out of tracked files and history. Private-system scripts may use an owner-only credential loader outside the repository `[REDACTED: location]`; the starter kit reads ntfy settings from its private environment file. Neither is proof that historical secrets were removed or rotated.
- **Automated scrubbing.** The import tool quarantines any script that embeds a password, token or remote-desktop login before it reaches the catalog.
- **Host-key pinning.** Adopting a node requires independent verification of its SSH host-key fingerprint, which protects against interception while the network grows.
- **Certificates.** A controller with a self-signed certificate is trusted by explicitly passing its certificate to the tools. TLS verification is never turned off globally.

## Levels of authority
- **Edge view:** local stats and a high-level status of other nodes.
- **Admin view:** the full picture, available only to admin-tier clients.

## Recovery
A planned vault holds credentials and system states so a lost or compromised client can be rebuilt quickly and issued a new identity.

## Local project maintenance

### What is implemented

`starter-kit/src/project_monitor.py` is a standard-library, read-only **local repository/evidence checker**. It reads maintenance policy configuration, tracked/non-ignored new documentation and local evidence; it writes a derived status report to `state/project_status.json`. Approved document hashes live in **evidence `docs`**, not in the maintenance configuration. “Read-only” means no network/device changes, command execution from input or external service polling; writing the report is its explicit local side effect.

It does not install the broader architecture, repair code, invoke a model, authenticate to a controller, scan the network or establish that a private service is deployed. All timers remain manually enabled, including the optional hourly `fleet-project.timer`. A fresh report only describes the configured checks.

### Documentation review and SHA256 approval

The maintenance configuration starts from `starter-kit/config/maintenance.example.json`, which remains the CLI default. An optional private copy at `starter-kit/config/maintenance.json` is git-ignored but is **not automatically selected**: pass its path through `--config` and edit the installed service's `--config` likewise. The repository root and local evidence location are CLI paths, not configuration fields. No existing runtime configuration needs to be changed for a public documentation cleanup.

Review **all tracked Markdown**, not just `docs/`: root `README.md`, starter-kit Markdown, and any later tracked Markdown count too. Use Git's tracked-file inventory as the baseline. The checker also includes non-ignored new files, so review pending documents and track intended additions before establishing the final baseline. After reviewing accuracy, privacy, links and deployment claims, record each relative path and SHA256 in the private evidence manifest's `docs` map. A missing approval, unreadable file or changed digest requires attention. Recompute approvals after later Markdown edits; never copy hashes as a substitute for review.

Approval attests only to the reviewed bytes. It cannot prove that a service runs, that external connectors exist, that an old audit is current or that history has been scrubbed. The public examples deliberately lack successful local evidence and must not produce an all-green deployment verdict.

### Required evidence and status

#### Configuration contract

The maintenance configuration has these fields:

| Field | Meaning |
|---|---|
| `max_age_seconds` | Positive numeric evidence lifetime, at most 86400 seconds; example/default is one day. |
| `required_checks` | Nonempty unique list of check IDs. Example: `unit-tests`, `syntax`, `privacy`, `connector-compatibility`. |
| `connectors` | Map including `ntfy` and `rave`; each policy has a boolean `implemented`. Example: ntfy true, Rave false. This is implementation policy, not a health observation. |

#### Evidence manifest contract

Evidence belongs in ignored `starter-kit/state/maintenance_evidence.json`, not in public Markdown or a checked-in success fixture.

The monitor reads each JSON input in binary mode with a **1 MiB byte limit**, not a character limit. An oversized, malformed or non-object document is invalid; do not attach large logs to the evidence JSON.

The evidence is a JSON object with three maps:

| Map | Record |
|---|---|
| `checks` | Keyed by configured check ID; each record has `status` (`passed`, `pending`, `failed`), numeric Unix-epoch `checked_at` and `revision` matching the current checkout fingerprint. |
| `docs` | Repository-relative Markdown path to its reviewed lowercase SHA256 hex digest. Approve only after content, privacy, link and claim review. |
| `connectors` | Keyed by connector ID; record has lifecycle `status` (`planned`, `blocked`, `implemented`, `verified`) and `prerequisites`. Verification additionally requires current `revision` and fresh numeric `checked_at`. |

Connector prerequisite keys are exactly `interface`, `auth`, `privacy`, `compatibility`, `verification` and `approval`. Each gate passes only for JSON `true`, not a truthy string. A verified record must satisfy every gate and implementation policy. Rave cannot be promoted to implemented/verified by supplying evidence.

Checks are numbered in `required_checks` order: with the example policy, check-1 is `unit-tests`, check-2 `syntax`, check-3 `privacy` and check-4 `connector-compatibility`. Connectors are numbered by sorted name: **connector-1 is ntfy; connector-2 is Rave**. This explains the privacy-preserving numbered daily summary; the source evidence remains keyed by name.

This parseable **non-operational, pending-only** template names every example requirement. It contains no observations or approvals and cannot establish health; null times and x fingerprints are deliberately invalid for passing checks. Fill genuine results manually using the workflow below, rather than merely replacing pending with passed:

```json
{
  "checks": {
    "unit-tests": {
      "status": "pending",
      "checked_at": null,
      "revision": "x-current-checkout-fingerprint"
    },
    "syntax": {
      "status": "pending",
      "checked_at": null,
      "revision": "x-current-checkout-fingerprint"
    },
    "privacy": {
      "status": "pending",
      "checked_at": null,
      "revision": "x-current-checkout-fingerprint"
    },
    "connector-compatibility": {
      "status": "pending",
      "checked_at": null,
      "revision": "x-current-checkout-fingerprint"
    }
  },
  "docs": {
    "README.md": "x-sha256-only-after-review"
  },
  "connectors": {
    "ntfy": {
      "status": "planned",
      "checked_at": null,
      "revision": "x-current-checkout-fingerprint",
      "prerequisites": {
        "interface": false,
        "auth": false,
        "privacy": false,
        "compatibility": false,
        "verification": false,
        "approval": false
      }
    },
    "rave": {
      "status": "planned",
      "checked_at": null,
      "revision": "x-current-checkout-fingerprint",
      "prerequisites": {
        "interface": false,
        "auth": false,
        "privacy": false,
        "compatibility": false,
        "verification": false,
        "approval": false
      }
    }
  }
}
```

The `revision` is **not a Git commit SHA**: it hashes the current sorted tracked/non-ignored file paths and their contents, including working-tree edits. Changes to code, tests, docs or other included files invalidate earlier evidence even without a commit. The checker does not run those checks or verify the provenance of a human's assertion; preserve actual result/source/time records privately and approve the evidence separately.

The inventory is the sorted unique result of `git ls-files --cached --others --exclude-standard`: **a newly created, non-ignored code file changes the fingerprint before it is staged; a newly created, non-ignored Markdown file also needs a reviewed `docs` hash**. Ignored runtime configuration and state are excluded. Regression coverage must exercise both new-code and new-document additions, not just modifications to tracked files.

#### Authoring evidence, without automatic approval

1. **Finish the change first.** Review the final diff, intended tracked/new files and the required checks. Keep real configuration, observations and evidence in ignored/private locations so writing evidence does not itself change the checkout fingerprint.
2. **Acquire candidate digests.** From the repository root, an operator may deliberately run the following fixed local helper. It imports the supplied `snapshot` function, invokes Git's file inventory and prints the current fingerprint plus candidate Markdown hashes. It does **not** run checks, read commands from inputs, write an evidence file or approve any digest:

   ```sh
   PYTHONPATH=starter-kit/src python3 - <<'PY'
   import json
   from pathlib import Path
   from project_monitor import snapshot

   revision, candidates = snapshot(Path.cwd())
   print("Current checkout fingerprint:", revision)
   print("CANDIDATES ONLY — review every document before approving:")
   print(json.dumps(candidates, indent=2, sort_keys=True))
   PY
   ```

3. **Review every document.** Read each candidate Markdown file for accuracy, privacy, links and deployment claims. Only then manually place that path/digest in the private evidence `docs` map. Do not paste the candidate map wholesale as an automatic approval. Include the root README maintenance conditions and all other tracked Markdown; remove approvals for deleted documents.
4. **Collect actual required results.** Deliberately run the project's existing, reviewed validation commands or perform the required manual review outside the monitor. Preserve actual output/source privately. For each configured check, record its genuine `passed`, `pending` or `failed` outcome, its observation/completion time as a numeric Unix epoch, and the exact fingerprint of the tested checkout. Do not substitute “now” for an old observation, a commit SHA for the fingerprint, or success for an unrun check. This page does not define executable commands inside evidence; the monitor never runs them.
5. **Record connector facts separately.** Create `ntfy` and `rave` records keyed by name. Record lifecycle status and the six reviewed boolean gates. A claim of `verified` requires genuine fresh `checked_at`, the same current `revision`, implementation support and all six gates true. Merely having ntfy code installed is not verification. Keep Rave `planned` with unresolved gates false: its interface, authentication and privacy prerequisites remain missing. Never fabricate credentials or a successful handshake.
6. **Check for intervening changes.** Re-run the read-only snapshot helper and compare its fingerprint with the recorded check/connector revisions. If anything included changed, rerun the affected validations and re-review changed Markdown before updating evidence. Writing ignored evidence alone should not change the fingerprint.
7. **Run the checker and inspect attention.** Use the commands below; keep the JSON evidence and derived output private. A successful validation run is not equivalent to a fully healthy project: **Rave still planned means project `attention`, exit 1 and no daily `ALL GREEN`**, even if all required checks and Markdown reviews pass. Claiming Rave implemented/verified forces it to `blocked` rather than bypassing the gate.

Missing, malformed, stale, future-dated or unsuccessful required evidence yields `ATTENTION` and a nonzero monitor exit. An absent evidence file is unknown, not healthy. Refresh the observation or repair its collection path; do not bypass the gate by deleting requirements, extending age limits without review or changing result text to success.

The derived `state/project_status.json` is an output, not authoritative evidence. Its `schema` is `1`; `health` is `healthy`, `attention` or `invalid`. It contains `checked_at`, fingerprint `revision`, earliest evidence `expires_at`, `last_successful_check`, numbered check/connector summaries, documentation-review count/paths, `obsolete_documentation_approvals` and findings. Invalid input produces a reduced invalid result. The file is atomically replaced. Console/daily summaries do not echo arbitrary source text or private connector names.

`documentation_review_paths` identifies exact Markdown paths needing review in the private JSON output; the daily project summary shows counts, numbered statuses and allowed prerequisite names instead of those paths or arbitrary evidence text. `last_successful_check` retains historical passed timestamps, even if that check is now stale/outdated. The daily summary labels a timestamp older than one day stale; it is not evidence that current checks passed.

The daily report consumes it with `--project-state` and uses `--manifest` to compare fleet state with the expected inventory. Project status must be no older than two hours and must not have outlived its evidence expiry. Fleet poll entries include numeric epoch `checked_at`; daily fleet freshness is at most ten minutes. Missing, future-dated, invalid, incomplete or stale observations must not yield an all-green report. Both the monitor and an attention daily report exit nonzero. Local hub metrics alone do not prove fleet or project health.

#### Manual invocation

From the repository root, after privately configuring evidence and requirements:

```sh
python3 starter-kit/src/project_monitor.py --repo . \
  --config starter-kit/config/maintenance.example.json \
  --evidence starter-kit/state/maintenance_evidence.json \
  --out starter-kit/state/project_status.json
python3 starter-kit/src/daily_status.py \
  --state starter-kit/state/fleet_status.json \
  --manifest starter-kit/config/fleet_manifest.json \
  --project-state starter-kit/state/project_status.json
```

Use `--config` to select your reviewed private copy instead of the public policy example when needed. No `--send` is shown: the daily report prints only. Attention is expected while required evidence or connector prerequisites are missing; do not suppress the nonzero result.

For the installed hourly user unit, edit `fleet-project.service`: its `--repo %h/xxxx-project` is a non-operational placeholder, not the installed kit's repository root. Point it to the reviewed checkout and supply your chosen configuration/evidence paths if they differ from defaults. Reload the user units after editing, then enable the timer manually only when ready. Installation itself leaves the timer disabled.

#### Scheduling, refresh and operator diagnostics

- **Nothing starts on installation.** Only after explicit manual activation does `fleet-project.timer` recompute local fingerprints/document hashes and reassess existing evidence hourly (`OnCalendar=hourly`, with a boot trigger after two minutes). It never periodically approves those hashes, runs tests or refreshes observation timestamps.
- **Daily versus hourly.** `fleet-daily.timer` uses `07:10:00` in the host's local system timezone; the project timer runs hourly using the same systemd calendar/timezone context. Both calendar timers are persistent, so missed calendar runs can be caught up when activated. Verify the actual next-run times on the host instead of assuming UTC.
- **Refresh manually.** A person runs the existing reviewed tests/checks outside the monitor, reviews their real result, updates genuine epoch/fingerprint evidence and approves changed documentation separately. Repeatedly running the monitor only changes the derived report time, not the underlying evidence's expiry. A fresh report over expired evidence remains attention.
- **Read exit states honestly.** Monitor exit `0` means its configured evidence gates passed; exit `1` means `attention` or `invalid`. Daily exit `1` means attention or failed delivery. A systemd oneshot marked failed because it returned `1` can be the intended evidence gate, not a collector crash. Missing files, bad configuration or invalid evidence must be investigated, not hidden by ignoring the result.
- **Rave is an intentional unresolved gate.** The current implementation requires both ntfy and Rave connector policy entries and blocks a Rave implemented/verified claim. Rave remains planned/attention until a deliberate, reviewed implementation change provides a real connector and its prerequisites. No evidence-only edit or timer run can make the current project `ALL GREEN`.

These are fixed, read-only operator diagnostics, not commands stored in evidence. They may return a nonzero status for inactive/failed units; inspect the reason locally:

```sh
systemctl --user status fleet-project.timer fleet-project.service fleet-daily.timer fleet-daily.service --no-pager
systemctl --user list-timers --all fleet-project.timer fleet-daily.timer --no-pager
journalctl --user -u fleet-project.service -u fleet-daily.service --since today --no-pager
```

Inspect private `state/project_status.json` for numbered outcomes, `documentation_review_paths`, `obsolete_documentation_approvals`, `expires_at` and `last_successful_check`. Do not publish raw logs, configuration or evidence. A derived report is **report data, not proof of deployed AI/controller/Rave services**, and a historical successful check does not override a current failure or stale observation.

### Connectors and Rave

The public kit has a local neighbour-table reader, optional Tailscale CLI reader, configured TCP probes and optional outbound ntfy publisher. It does **not** include controller/Windows relay, archive/ingest, AI dispatch or Rave adapters. Connector metadata and manually supplied evidence are not implementations.

**Rave: planned, disabled; no verified connector found.** The name alone does not identify a product or interface. Before implementation, obtain and review:

1. **Interface:** the exact product/project and version, supported local API/CLI/export documentation, endpoint or executable, transport, response/event schema, read-only operations, timeouts and freshness semantics.
2. **Authentication:** the supported authentication method, required least-privilege read-only scopes/account, private credential source, rotation/revocation process and TLS/trust requirements. Do not put credentials in this repository or disable certificate verification.
3. **Privacy:** the exact fields collected and their sensitivity, approved purpose and operator consent, redaction/minimisation rules, local storage/access policy, retention/deletion limits and whether any data leaves the local system.

Until all three are resolved, retain a disabled/planned connector entry and report the missing prerequisites honestly. Do not fabricate endpoints, credentials, a connector module or successful evidence. Enabling metadata does not create a connector. Other integrations follow the same read-only-first review process; see [future integrations](future-integrations.md).

### Operational boundaries

- Inputs are data only: never execute ingested commands, Markdown snippets, chat directives, evidence fields or connector metadata.
- Review the [script guide](../starter-kit/SCRIPT_GUIDE.txt) before invoking a script. Poll dry-runs still make probes and write state; the notifier can publish when configured; Wake-on-LAN changes require `--apply`.
- Install units without enabling them. Inspect configuration and results before manually enabling the optional project timer or any existing timer.
- Share roles and sanitised summaries, not real addresses, MACs, hostnames, credentials, topic names or raw private evidence. Public identifying examples use non-operational x placeholders; functional protocol/bind/loopback constants and role labels are not identities.
- Follow the root [repository maintenance conditions](../README.md#repository-maintenance-conditions) whenever scripts, requirements, evidence schema or documentation change.
