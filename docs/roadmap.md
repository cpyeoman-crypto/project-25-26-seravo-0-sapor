# Roadmap: clients to come

Status per client is in [fleet-clients.md](fleet-clients.md). This page groups what is still to build.

## In progress
- **Golden master laptop fleet:** reconditioned Dell laptops stamped from one image and one idempotent install script.
- **Fleet adoption:** bringing the remaining clients under remote management, once their access is confirmed out of band.
- **Identity clean-up:** resolving conflicting hardware identities so every dispatch target is unambiguous.
- **Remote desktop access** to clients, with a LAN-first, mesh-fallback path.
- **Ingest upgrade:** moving from a watcher service to a native filter inside the chat front end.
- **IoT onboarding:** fixing join problems on one segment.

## Further integrations (idea stage)
Details in [future-integrations.md](future-integrations.md): a second LLM (Seravo-1), voice and speech-to-text, home-automation control, media capability, a weather station, LiDAR presence sensing, solar and utilities monitoring, and wider IoT plans (onboarding checklist, behaviour baselines, lifecycle tracking, quarantine).

## Planned clients
- **Edge enforcer in line:** a Dell OptiPlex micro-PC (candidate) with dual-uplink (satellite plus cellular) firewall, intrusion prevention, DNS filtering, transparent proxy, mirror telemetry, a fail-closed bypass cable and audible alarms.
- **Backup travel router with cellular hotspot:** a second travel router (TP-Link) paired with a cellular hotspot, kept as a standby uplink for when the satellite service has problems. Adds an uplink-health probe, automatic failover testing and a push report. Exact model and plan `[REDACTED]`.
- **Controller migration:** the network controller moves into a container on the edge enforcer, with audible hardware-level alarms for physical intrusion.
- **Long-term archivist machine:** a dedicated machine on its own isolated direct link, so the orchestrator has a fallback if its own drive fails.
- **Internal auditor:** a small CPU-only model that reviews sandbox logs weekly.
- **Creative and failover node:** a second LLM that takes over if the orchestrator loses its heartbeat.
- **Burst compute orchestration:** asleep-by-default spare nodes that the orchestrator wakes over the network (Wake-on-LAN) for heavy local LLM inference, then lets sleep again when the queue clears.
- **Mobile quarantine buffer:** a retired Samsung Galaxy phone that scans files before they reach the orchestrator.
- **Credential vault:** recovers a wiped or compromised client and reissues its cryptographic identity. Reissue stays behind a human approval until the process has proved itself.
- **Autonomous node provisioning ("insta-join"):** a new edge scout bootstraps itself into the mesh using a pre-approved, tagged, single-purpose join key, after the human has confirmed its host-key fingerprint. Applies to new fleet nodes and the repeat-build laptop.
- **Smart-home integration** (Home Assistant) for the IoT devices.
- **Status HUD or touchscreen display** with an audible alarm.
- **Remote-desktop wall:** one screen showing every client session.

## Planned behaviour
- **Autonomous fleet behaviour:** clients update themselves, send thermal telemetry, and restart their own tunnels.
- **Full-disk encryption and wake-on-LAN** on every client, with a standard weekly update window.
- **Token budgets and resource limits** for the orchestrator's model.
- **Honeypot segment, tarpit and quarantine playbooks:** practised in a dry-run simulation, not yet applied.
- **WAN-isolated planning:** a fully local fallback so the orchestrator can plan and repair with no internet.
- **Voice ingestion (idea):** dictated voice notes, field commands and spontaneous creative notes transcribed locally, then pushed into the ingest queue and archive like any saved chat. Once archived they would be indexed into the vector memory, so spoken context can be recalled in later terminal sessions. Not built yet; no audio leaves the network by design.
- **Bigger local models:** more RAM and fast storage.
- **Memory upgrade through collaboration (planned):** the orchestrator is a laptop-class machine, so its memory is DDR4-2400 laptop (SO-DIMM) RAM. The plan is to source spare modules together with a collaborator on the project rather than buy new. More RAM lets the orchestrator hold a larger local model and more of the vector memory at once. Before any swap: match the speed, capacity and module type the machine supports, test the modules, and note that a mixed-speed pair runs at the slower speed. Open: how much RAM the machine can take, and which modules are on hand.
