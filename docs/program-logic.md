# Program logic and integrations

How the software is put together. Product and protocol names only: script names, file names, endpoints, credentials and addresses are `[REDACTED]`.

**Scope:** sections below describe the broader architecture, including private/planned components not shipped here. The public implementation is the [starter kit](../starter-kit/README.md), whose complete script inventory is in [SCRIPT_GUIDE.txt](../starter-kit/SCRIPT_GUIDE.txt). Its [project monitor](monitoring-and-protection.md#local-project-maintenance) is a read-only local repository/evidence checker, not an AI dispatcher or an external connector.

## 1. Core logic: small daemons, tracked state

The system is a set of small, single-purpose Python programs rather than one large application.

| Principle | What it means |
|---|---|
| **Transitions, not pings** | Each run compares live data with a cached last-known state, and acts only on a real change: a device that left the network, not one that is briefly asleep. The first run seeds the cache and sends nothing. The cache is versioned, so its format can change safely. |
| **Scheduler at the OS level** | Timing comes from systemd timers, not sleep loops inside Python. That gives predictable schedules, restart on failure, and per-job logs, with little code to maintain. |
| **Read first, write later** | Watchers only read. Anything that changes the network needs an explicit apply step and a backup. |
| **Glue in shell** | Bash and PowerShell handle bootstrapping, credential hand-off to a script (never stored in it) and Windows-native health queries. Python does the reasoning. |

A runnable, simplified version of the same pattern is in the [starter kit](../starter-kit/README.md).

## 2. Integrations: where the data comes from

| Source | How it is used |
|---|---|
| **Network controller API (TP-Link Omada)** | The main view of the physical layer: connected clients, segment membership, signal strength, access point, uplink and failover state. Read through a local API account. The controller's self-signed certificate is exported and trusted explicitly, so TLS checking stays on. |
| **Tailscale command line, JSON output** | The overlay peer list gives cryptographic reachability of each client even where ICMP ping is blocked. Parsed from the tool's JSON output. |
| **ntfy** | Outbound publishing only: a formatted JSON message to a private topic. See [ntfy-alerts.md](ntfy-alerts.md). |
| **Windows-native queries** | A PowerShell agent on the Windows hub reports health and relays switch mirror-port data. |

Together they cover the physical network, the overlay and the clients. Any gap between them (a device on the network but not on the overlay, for example) is itself reported. "Complete visibility" is the aim, and the reports list what is not yet covered.

These sources are integration targets, not proof of coverage. The public kit directly reads the local neighbour table and optional Tailscale peer output, probes configured TCP ports and optionally publishes ntfy messages. Controller and Windows agents are not included. Rave is planned/disabled pending the [interface, authentication and privacy prerequisites](monitoring-and-protection.md#connectors-and-rave).

## 3. The AI pipeline

| Tier | Who | What they do |
|---|---|---|
| 1 | Cloud assistants (Gemini, GitHub Copilot) | Diagnose from logs, act as prompt architects and write structured, minified JSON work orders. Advisory only. |
| 2 | Seravo-0 (local) | Decides whether an approved job runs, and records the outcome. |
| 3 | Aider with a local code model | Makes small, bounded repairs inside Seravo-0's own workspace. Not accepted until checks pass and the diff has been reviewed. |

The hand-off format is fixed: minified JSON, absolute paths, labelled code blocks, a full stack trace for failures, and the acting agent named in every log line. See [ai-team.md](ai-team.md).

**Cloud and local.** Cloud models are used today for hard reasoning, code review and drafting infrastructure code. Local inference (Ollama) runs on the Linux compute nodes, and a local vector store backs retrieval from past incidents, the fleet standards and archived notes. The direction is more local, less cloud. See [principles.md](principles.md).

## 4. Supporting pieces

- **Open WebUI** in a Docker container is the chat front end for local and external models.
- **Git and rsync over SSH.** The reviewed repository is the source of truth. Approved scripts, scheduled-job definitions and prompts are distributed from the orchestrator to adopted clients every 30 minutes over pinned-key SSH, and a client can also pull from GitHub. Nothing a model writes reaches a client until it has been reviewed.

See also [polling.md](polling.md) and [illustrations.md](illustrations.md).
