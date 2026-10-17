# Architecture

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

## Memory tiers

| Tier | Holds | Lifetime |
|---|---|---|
| Working | The current prompt and context | Seconds to minutes |
| Short-term | Recent telemetry and events, kept in a vector database for fast recall | Roughly 40 days |
| Long-term | Logs, audits and history, written once to the archivist | Permanent |

## Telemetry rhythm

- **Heartbeat:** a simple weekly ping from each client confirms it is alive.
- **Spark telemetry:** a planned five-minute thermal and health report in a lightweight JSON format.
- **Watchdog:** a planned local job that restarts a client's tunnel and flushes firewall rules if connectivity drops.

## Models

- The orchestrator runs the larger local models.
- Scouts are designed to talk to the orchestrator rather than run heavy models themselves. Where a scout runs a model locally, it is a small, quantised one.
- The creative node runs its own separate model.
