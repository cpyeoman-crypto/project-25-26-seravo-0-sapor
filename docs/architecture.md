# Architecture

**Target architecture, not deployment evidence.** The public [starter kit](../starter-kit/README.md) implements a smaller local/fleet subset. Its [project monitor](monitoring-and-protection.md#local-project-maintenance) checks local files and reviewed evidence; it does not deploy or directly observe the layers below.

## Layers

| Layer | Purpose | Roles involved |
|---|---|---|
| Sense | Collect telemetry, logs and traffic | Edge scouts, edge enforcer, field gateway |
| Think | Analyse, correlate, decide what needs attention | AI orchestrator |
| Remember | Keep short-term context and the long-term record | Short-term memory store, long-term archivist |
| Decide | Approve or deny consequential actions | Mobile approvers |
| Act | Apply approved changes to the network | AI orchestrator, router and controller host |

## Connectivity model

- **LAN first, mesh fallback.** Clients prefer the physical wired network for internal traffic. If the local link fails, they fall back to the encrypted mesh overlay.
- **One site router per site.** Only designated machines advertise subnet routes. Mobile devices never act as routers, which prevents routing loops.
- **Isolated sandbox.** Untrusted or unknown devices live on their own network segment, away from servers and workstations.
- **Direct link to the vault.** Logs and audits travel to the archivist over a dedicated wired link rather than the shared network.

More detail, including updates and off-site machines: [mesh-and-updates.md](mesh-and-updates.md).

## One OS per job
The fleet avoids a one-size-fits-all operating system. Linux (Pop!_OS) carries the AI compute and scheduled jobs, containers carry the secondary services, and a native Windows node is kept for Windows-only tooling. Hand-offs between platforms follow the same written rules: absolute paths, minified JSON and named roles. See [stack.md](stack.md).

## Memory tiers

| Tier | Holds | Lifetime |
|---|---|---|
| Working | The current prompt and context | Seconds to minutes |
| Short-term | Recent telemetry and events, kept in a vector database for fast recall | Roughly 40 days |
| Long-term | Logs, audits and history, written once to the archivist | Permanent |

## Telemetry rhythm

- **Starter-kit heartbeat:** a local JSON health file written every five minutes when its user timer is enabled. Hub collection is configured separately; it is not a weekly ping.
- **Spark telemetry:** broader thermal telemetry is planned, beyond the kit's load, memory and disk metrics.
- **Watchdog:** a planned local job that restarts a client's tunnel and flushes firewall rules if connectivity drops.

## Models

- The orchestrator runs the larger local models.
- Scouts are designed to talk to the orchestrator rather than run heavy models themselves. Where a scout runs a model locally, it is a small, quantised one.
- The creative node runs its own separate model.
