# Roadmap: clients to come

Status per client is in [fleet-clients.md](fleet-clients.md). This page groups what is still to build.

## In progress
- **Golden master laptop fleet:** reconditioned laptops stamped from one image and one idempotent install script.
- **Fleet adoption:** bringing the remaining clients under remote management, once their access is confirmed out of band.
- **Identity clean-up:** resolving conflicting hardware identities so every dispatch target is unambiguous.
- **Remote desktop access** to clients, with a LAN-first, mesh-fallback path.
- **Ingest upgrade:** moving from a watcher service to a native filter inside the chat front end.
- **IoT onboarding:** fixing join problems on one segment.

## Planned clients
- **Edge enforcer in line:** dual-uplink (satellite plus cellular) firewall, intrusion prevention, DNS filtering, transparent proxy, mirror telemetry, a fail-closed bypass cable and audible alarms.
- **Controller migration:** the network controller moves into a container on the edge enforcer.
- **Long-term archivist machine:** a dedicated machine on its own isolated direct link, so the orchestrator has a fallback if its own drive fails.
- **Internal auditor:** a small CPU-only model that reviews sandbox logs weekly.
- **Creative and failover node:** a second LLM that takes over if the orchestrator loses its heartbeat.
- **Mobile quarantine buffer:** a retired phone that scans files before they reach the orchestrator.
- **Credential vault:** recovers a wiped client and reissues its identity.
- **New fleet nodes and a repeat-build laptop,** joined through pre-approved, tagged keys.
- **Smart-home integration** for the IoT devices.
- **Status HUD or touchscreen display** with an audible alarm.
- **Remote-desktop wall:** one screen showing every client session.

## Planned behaviour
- **Autonomous fleet behaviour:** clients update themselves, send thermal telemetry, and restart their own tunnels.
- **Full-disk encryption and wake-on-LAN** on every client, with a standard weekly update window.
- **Token budgets and resource limits** for the orchestrator's model.
- **Honeypot segment, tarpit and quarantine playbooks:** practised in a dry-run simulation, not yet applied.
- **WAN-isolated planning:** a fully local fallback so the orchestrator can plan and repair with no internet.
- **Burst compute:** cold spares that wake on demand for heavy jobs. Idea only, not requested in detail.
- **Bigger local models:** more RAM and fast storage.
