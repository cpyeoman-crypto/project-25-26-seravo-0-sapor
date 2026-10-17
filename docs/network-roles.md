# Network roles

Status, hardware classes and interactions are in [fleet-clients.md](fleet-clients.md).

Roles only. Devices, addresses and names are deliberately left out.

| Role | What it does |
|---|---|
| AI orchestrator | Runs Seravo-0, the Docker sandbox and the short-term memory store. The central brain. |
| Edge scout clients | Dell laptops. Lightweight machines that report to the orchestrator. They show local stats and a high-level view of the network. One doubles as the template for new clients. |
| Edge enforcer | Security node at the gateway edge. It watches the sandboxed IoT network and is built to fail defensively. |
| Long-term archivist | Immutable vault. It receives logs, audits and media over a dedicated direct link. |
| Core resource and console | Main management machine that also provides subnet routing for the mesh. |
| Router and controller host | TP-Link Omada hardware controller and gateway. Handles DHCP and acts as a subnet router for the mesh. |
| Backup uplink (planned) | A second travel router with a cellular hotspot, held as a standby internet path if the satellite service has problems. |
| Burst compute (planned) | Asleep-by-default clients woken for heavy model work. |
| Field gateway | Serves a remote or travelling LAN. |
| Mobile approvers | Phones used to approve or deny AI actions. |
| Internal auditor | A role that reviews the sandboxed IoT traffic logs weekly. |
| Creative and failover node | Hosts the novel workspace and a creative LLM. It is also the high-availability backup for Seravo-0. |

## Access tiers

1. Unrestricted admin
2. Mobile admin
3. Travel bridge
4. Limited watch-only
