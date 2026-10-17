# Project 25/26 Seravo-0 / Sapor

> **Who will save us in our final hour?**

A private mesh network with an AI at its centre. Seravo-0 is a large language model (LLM) built into the clients of the network. It watches the network around the clock, reports what it sees, and helps protect it. It never acts alone on anything important: a human approves or denies its actions from a phone.

That question belongs to the network and to the novel it grows beside. A 20-year-old sci-fi/fantasy novel is being revived, and its world-building shares a home with the technical build. The two run on separate machines, so the creative work never touches the security work. Story details are deliberately kept out of this repository.

## The idea in one minute

Most home and small-site networks are watched by nobody. Devices join, firmware ages, cheap IoT gadgets talk to the internet, and problems show up only after something breaks.

This project puts a small team of machines on the job, each known here by its function:

1. A **central brain** reads telemetry and logs and reasons about them with a local LLM.
2. **Scouts** at the edge report in and show a local view.
3. An **enforcer** at the gateway isolates anything untrusted.
4. An **archivist** keeps the long-term record.
5. **A person**, on a phone, says yes or no to anything consequential.

Everything runs locally. The LLM is hosted on the network's own hardware, not a cloud service, so network data stays inside it.

## The clients, by function

| Function | What it does | Status |
|---|---|---|
| AI orchestrator | Runs Seravo-0, the sandbox and short-term memory. The central brain. | Active |
| Edge scouts | Lightweight clients that report to the orchestrator and show a local view. One is the template for new clients. | Active |
| Edge enforcer | Gateway-edge security. Watches the isolated sandbox and fails closed. | Active, gaining features |
| Long-term archivist | Write-once vault for logs, audits and history. | Active |
| Core resource and console | Main management machine, also provides subnet routing. | Active |
| Router and controller host | Handles addressing and routing for the mesh. | Active |
| Field gateway | Serves a remote or travelling LAN. | Active |
| Mobile approvers | Phones used to approve or deny AI actions. | Active |
| Internal auditor | Reviews sandbox traffic logs weekly. | Active role |
| Creative and failover node | Hosts the novel workspace and a creative LLM. Also the backup for Seravo-0. | Active |
| New fleet nodes, burst compute, credential vault | See the [roadmap](docs/roadmap.md). | Planned |

## Architecture at a glance

```mermaid
flowchart LR
    Phone["Mobile approvers"] -- approve / deny --> Brain
    Scout1["Edge scouts"] -- heartbeat + telemetry --> Brain
    Brain["AI orchestrator<br/>(Seravo-0: LLM, sandbox, short-term memory)"]
    Brain -- logs, audits --> Vault["Long-term archivist"]
    Enforcer["Edge enforcer<br/>(gateway security)"] -- sandbox traffic logs --> Brain
    Brain -. failover .-> Creative["Creative + failover node"]
    Field["Field gateway<br/>(remote LAN)"] --- Brain
```

More detail: [docs/architecture.md](docs/architecture.md).

## Infrastructure (details redacted)

The real build is described only by what each part does. Anything that could help someone attack it is withheld on purpose.

| Layer | What is public here | What is withheld |
|---|---|---|
| Hardware | The type of role each machine plays | `[REDACTED: models, specs, serials]` |
| Addressing | That servers, workstations, IoT and guests sit on separate segments | `[REDACTED: ranges, VLAN IDs, address plan]` |
| Mesh overlay | An encrypted overlay joins every client, with the LAN preferred when available | `[REDACTED: provider config, route lists, ACL rules]` |
| Access control | Four access tiers, least privilege | `[REDACTED: tags, keys, credentials]` |
| Storage | A write-once long-term vault, reached over a dedicated direct link | `[REDACTED: paths, shares, mount layout]` |
| Remote access | Remote clients can reach the mesh | `[REDACTED: ports, services, exit points]` |
| Telemetry | Weekly heartbeat, planned five-minute health reports | `[REDACTED: endpoints, scripts, schedules]` |

## Documentation

| Document | What's in it |
|---|---|
| [docs/architecture.md](docs/architecture.md) | Data flow, memory tiers, connectivity model |
| [docs/network-roles.md](docs/network-roles.md) | Every role and the four access tiers |
| [docs/monitoring-and-protection.md](docs/monitoring-and-protection.md) | How the network is watched and defended |
| [docs/principles.md](docs/principles.md) | The design rules the build follows |
| [docs/roadmap.md](docs/roadmap.md) | Clients and upgrades still to come |
| [docs/novel-and-seravo.md](docs/novel-and-seravo.md) | Where the creative project fits, and questions to explore |
| [docs/glossary.md](docs/glossary.md) | Short definitions of the terms used here |

## Repository layout

```
archive/
  <session-id>.md              # per-session notes/summary
  transcripts/
    <session-id>.jsonl         # raw transcript for the same session
docs/                          # overview documents listed above
```

Each session has one `.md` and one matching `.jsonl` sharing the same `<session-id>`. Real archive content is git-ignored; only the folder layout is tracked.

## What is not in this repository

Device names, IP addresses, subnets, keys, logs, raw transcripts and story details. The documents describe roles and design, not the live network.
