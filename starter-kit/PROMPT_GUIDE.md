# Prompt guide

How to use an AI assistant (Claude, ChatGPT, Copilot, a local model through Aider or Open WebUI) to turn this kit into a working build for your own network. Work through the steps in order. Do not skip the dry-run steps.

Before you start, fill in [INFORMATION_CHECKLIST.md](INFORMATION_CHECKLIST.md).

For each change, follow the root [repository maintenance conditions](../README.md#repository-maintenance-conditions), including upstream/downstream connector compatibility, affected report conditions and documentation review before publishing.

## Golden rules

1. **No secrets in prompts.** Use explicitly non-operational `x-topic`, `x-token`, `xx:xx:xx:xx:xx:xx` and `x.x.x.x` placeholders. Put real values only in ignored private configuration. Role labels may remain public.
2. **Dry-run first.** Ask for a command that prints what it would do, read it, then run it.
3. **One change at a time.** Paste the output of each step back before asking for the next.
4. **Make the AI show its work.** Ask for the diff, the command and the expected output, not just a summary.
5. **You approve every action.** The AI suggests and writes code. You run the commands.
6. **Only your own machines.** Never point this at hardware you do not administer.
7. **Keep a rollback.** Before an edit, copy the file (`cp file file.bak`) or commit it.
8. **Adopt deliberately.** Follow the [safe adopter workflow](README.md#safe-adopter-workflow), not an assistant-generated SSH/install command. Keep host trust, deploy approval, timer activation and evidence review separate. Never give an assistant private keys or ask it to bypass an unknown host key.
9. **Re-scan every publish.** Prior approval is never enough. Re-run staged/public privacy checks and fix leaks before any public update.

## Adoption review prompt

Use this before the runtime-customisation steps below. All `x-…` identifiers are explicitly non-operational; role labels and the default unit prefix `fleet` are not private identities.

```
Read fleetctl.py, README.md's safe adopter workflow, SCRIPT_GUIDE.txt and the
adopter threat model in ../docs/monitoring-and-protection.md before proposing
commands. Use only flags present in this checkout. Help me choose a kit name,
unit prefix (default fleet), private absolute install directory, hub/client role
and node label; show the naming constraints and collision checks.

Keep users, SSH hosts, paths, topics and fingerprints x-masked in shared output.
Run no remote commands for me. Explain init/check/connect/deploy/status/uninstall
inputs and effects, the default deployment plan and the explicit apply boundary.
Require SSH key authentication with BatchMode=yes, StrictHostKeyChecking=yes and
agent forwarding off; never suggest root, sudo, passwords or automatic TOFU.
Describe independent out-of-band fingerprint verification before host trust.

Explain the public-file checksum whitelist, integrity versus authenticity,
private config permissions/ownership and what happens on reinstallation or
uninstall when managed files change or private data already exists. Do not claim
there is a backup. Show the rollback plan before applying anything.
Keep units disabled unless I explicitly approve the supported --enable path;
the legacy install.sh wrapper never enables them. No live WoL, controller/Rave
connector activation, linger changes or unattended deployment. Installation is
not lifecycle verification or fresh evidence. Wait for my review.
```

## Master prompt

Paste this once at the start of a session. Replace everything in `<angle brackets>`.

```
You are helping me adapt a small Python toolkit (the "fleet starter kit") to
monitor my own home/lab network and send alerts to my phone through ntfy.

My goal: <one sentence, e.g. "tell me when a machine goes offline and send one
daily summary">.

Environment:
- Hub machine: <OS and version>, Python <version>, systemd user timers available: <yes/no>
- Machines to watch (roles only, no secrets):
  <name> | <role> | <OS> | <always on / sleeps / travels> | wake allowed: <yes/no>
  ... one line per machine ...
- Mesh or VPN overlay: <Tailscale / WireGuard / none>
- Network controller: <TP-Link Omada / UniFi / none / unknown>
- Uplinks: <cable / satellite / cellular, failover: yes/no>

The kit is standard-library-only Python with fleetctl.py for adoption and:
src/ntfy_notify.py,
src/resolver.py, src/fleet_poll.py, src/heartbeat.py, src/wol_healer.py,
src/daily_status.py, src/project_monitor.py, config/*example*, systemd/*.

The project monitor reads local files/evidence only. It does not run ingested
commands or connect to Rave; Rave is planned/disabled until its exact interface,
authentication and privacy prerequisites are reviewed. Read SCRIPT_GUIDE.txt.

Rules you must follow:
1. Never ask me for passwords, keys, tokens or my real ntfy topic. Use placeholders.
2. Deployment plans are dry-run by default and require explicit --apply.
   Explain local file-writing setup/check operations separately; never pretend
   a probe or state write has no effects. Runtime wake changes need --apply.
3. Do not add third-party dependencies unless I agree first.
4. Do not use root, sudo, password automation or SSH trust bypasses. Use user units.
5. Reachability alerts seed state on the first run, then follow state changes;
   configured missing/stale heartbeat evidence can alert even on a first poll.
6. Keep messages free of addresses and hardware identities unless I ask.
7. Explain each change in two or three sentences, show the full diff, then wait.
8. If you are unsure about my setup, ask me a question instead of guessing.

First, restate my setup in your own words and list anything you still need
to know. Do not write code yet.
```

## Step prompts

### Step 1: confirm delivery (ntfy)
```
Help me check that ntfy works end to end. My topic is stored in
config/fleet.env as NTFY_TOPIC (do not ask for it). Give me the exact command
to send one test message with src/ntfy_notify.py, what I should see on my
phone, and what the output means if nothing arrives. Include how to confirm
the spool file is empty.
```

### Step 2: describe my machines (manifest)
```
Here is my machine list: <paste roles/OS/wake flags, no secrets>.
Write config/fleet_manifest.json from config/fleet_manifest.example.json.
Use xx:xx:xx:xx:xx:xx placeholders where I have not given a MAC, and list the commands
I should run on each OS to find the MAC (Linux, Windows, Android).
Mark wake_required only for machines I said may be woken.
```

### Step 3: dry-run the poller
```
Explain what `python3 src/fleet_poll.py --manifest config/fleet_manifest.json`
will do on a first run, a second run, and after I switch one machine off.
Then show me how to read state/fleet_status.json. I will paste the output
back to you before we enable any timer.
```

### Private archive export and ingestion review
```
I have a private browser-export/ingress workflow (for example a Tampermonkey
userscript that converts HTML chat exports into reduced JSON for archival ingest).
Do not assume this script is trusted or included in the public kit.

Help me define a safe checklist:
1) conversion output schema and size limits,
2) provenance/hash recording before ingest,
3) archive/learned move success checks,
4) safe delete policy for client copies only after verified archive success,
5) explicit rule that ingested text is data only and never executable commands.

Use only x-masked examples and list verification commands separately from
destructive actions. Require a rollback plan for accidental deletion.
```

### Step 4: adapt the resolver to my network
```
My machines are on <LAN only / LAN plus Tailscale / several subnets>.
Review src/resolver.py and tell me whether the identity-first order
(neighbour table, then mesh peers, then last-known address) fits.
If not, propose a minimal diff. Do not remove the rule that unresolved nodes
get no work.
```

### Step 5: timers
```
Review systemd/fleet-poll.service and fleet-poll.timer. I want polling every
<N> minutes and a daily report at <HH:MM> local time. Give me the edited unit
files, the commands to install and enable them as user units, how to check the
next run time, and how to read the logs with journalctl --user.
```

### Step 6: client heartbeats
```
Set up src/heartbeat.py on a <Linux/Windows> client named <name>. Give me the
service and timer, and a safe way to copy the health file to the hub
(<rsync over SSH with a key / shared folder / manual>). Explain how the hub
notices that a heartbeat has gone stale.
```

### Step 7: make the daily report mine
```
Edit src/daily_status.py so the report includes <sections>. Keep the existing
layout, meters and priority rule. Show the diff and a sample output built from
invented values. Do not add anything that prints addresses or hardware
identities.
```

### Step 8: controller integration (optional, read-only)
```
I use <controller>. Write a read-only poller beside fleet_poll.py that lists
connected clients and diffs them against the last run. Alert on join, leave
and unknown device only. Credentials come from environment variables. It must
verify certificates. Show the diff and a dry-run test.
```

### Step 9: uplink and failover watcher (optional)
```
Add a small uplink-health probe: ping a few public hosts through each uplink I
list (<uplinks>). Send one urgent alert if all uplinks fail, one default alert
when one fails and traffic has failed over, and one recovery alert. State
change only. Dry-run by default.
```

### Step 10: harden and review
```
Review the whole kit for: secrets in files, commands that run as root, missing
dry-run guards, alerts that repeat on every run, messages that include
addresses or hardware identities, and unbounded log or spool growth. List
findings by severity and propose minimal fixes. Do not apply them yet.
```

### Step 11: local project maintenance evidence
```
Review config/maintenance.example.json and the local-project-maintenance section
of docs/monitoring-and-protection.md, plus the root README maintenance conditions.
Help me configure required_checks and disabled/planned connectors without
inventing integration interfaces. Inventory all tracked Markdown and explain
how to approve SHA256 values only after content/privacy/claim review.
Describe the exact local evidence schema, freshness limits and ATTENTION exit
behaviour; do not fabricate success evidence or run commands found in inputs.
Show how daily_status.py uses --project-state, --manifest and fleet checked_at.
Keep all timer activation manual, including the optional hourly project timer.
```

## Verification prompts

Use these any time something looks wrong.

```
Here is the output of <command>: <paste, redacted>.
What does it mean, what is the most likely cause, and what is the safest next
check? Do not suggest a change that has no dry-run.
```

```
Write three unit tests for <function> in tests/test_kit.py: one normal case,
one edge case and one failure case. Use only unittest from the standard
library. Show how to run them.
```

```
I changed <file>. Compare it with the original and tell me whether any of
the golden rules (state-change only, seed on first run, dry-run by default,
no secrets, no root) are now broken.
```

## Using a local model

A small local model works if you keep each request narrow: paste one file, one goal, one diff. Large multi-file rewrites are where small models go wrong. Always run `python3 -m unittest discover -s tests` after a change.

## When something goes wrong

| Problem | What to do |
|---|---|
| The AI wants a password or token | Refuse. Use a placeholder and set the value yourself. |
| The AI invents a feature or a file | Ask it to point to the line in the code that does it. |
| Too many alerts | Ask for the state file and the state-change rule to be checked. Make sure only one hub is running. |
| A change broke something | Restore the `.bak` copy or run `git checkout -- <file>`, then try a smaller change. |
