# Fleet clients: roles, hardware, interactions and status

Every client is described by its function. Names, addresses, hardware models and serials are withheld (`[REDACTED]`).

**How status was decided.** It comes from the project's own audit records and from past planning chats. Chat transcripts are plans, not proof, so anything only seen in a chat is marked *planned* or *in progress*. Where a recent audit could not verify a client, it says so.

| Status | Meaning |
|---|---|
| **Active** | Seen working in a recent audit or live job record. |
| **Active, degraded** | Running, but with a known access, identity or latency problem. |
| **In progress** | Partly built, or built but blocked on something. |
| **Planned** | Designed in prompts, not yet built or not yet seen working. |

## Inventory at a glance

The reviewed inventory holds about 40 records. Roughly a third are compute, mobile and network-infrastructure roles, and about two-thirds are IoT devices on an isolated segment. Each record carries a role, a hardware identity, a segment and a status. Records that cannot be verified stay marked as unconfirmed, and the AI is not allowed to send work to them.

## Compute and control clients

| Function | Hardware class | OS | What it does | Status |
|---|---|---|---|---|
| **AI orchestrator** (Seravo-0) | Laptop-class workstation, run headless `[REDACTED: model]` | Linux | Runs the local LLM, the chat front end, the vault and ingest services, the scheduled jobs and the sandbox. Decides, dispatches and records. | **Active** |
| **Edge scout / operator console** | Laptop-class workstation | Linux | The operator's day-to-day console. Hosts the Ingress drop folder, a status HUD and the template for new clients. Acts as a mesh subnet router and exit point. | **Active**, remote shell access to it still being fixed |
| **Windows hub and mirror-port relay** | Laptop-class | Windows | Relays the switch mirror port's neighbour data to the vault and stands in as the controller relay. Also serves as an archive target and mesh exit point. | **Active, degraded**: remote key authorisation is blocked and latency was seen on the relay path |
| **Mobile Linux medic client** | Laptop-class, travels | Linux | Sends telemetry to the orchestrator every five minutes and runs a local watchdog. Restricted by policy: it can report and query but cannot start SSH sessions. | **Active** |
| **Windows fleet node** | Desktop-class | Windows | General fleet member, woken on demand. | **Active, degraded**: offline at last audit, identity record conflicted |
| **Field gateway (stealth portal)** | Small Linux box | Debian | Subnet router for a remote or travelling LAN. | **Planned / unverified**: in the design roster, not seen in recent audits |
| **Reconditioned laptop fleet** | Reused laptops of one family | Linux | Stamped from one "golden master" image and one idempotent install script so each client is identical. | **In progress** |
| **Repeat-build laptop** | Laptop-class | Linux | The next machine built from the golden master image. | **Planned** |

## Network and edge infrastructure

| Function | Hardware class | What it does | Status |
|---|---|---|---|
| **Network controller** | Hardware controller appliance | Holds the network's configuration: segments, DHCP, Wi-Fi and access points. | **Active**. Its management API cannot set a few options, so those are set by hand in its web interface. |
| **Gateway router** | Wired router | Routing, static routes, firewall rules. | **Active** |
| **Switch and access points** | Managed switch and Wi-Fi access points | Segment the network and carry the mirror port. | **Active**; identities not individually verified by the AI |
| **Edge enforcer** | Small appliance, to sit between the uplinks and the gateway | Dual-uplink (satellite plus cellular) firewall, intrusion prevention, DNS filtering, transparent proxy and mirror telemetry. Fails closed. | **Planned**: hardware not yet placed in line |
| **Controller migration** | Same appliance | Moves the controller software into a container on the enforcer so the hardware controller can retire. | **Planned** |
| **Travel router** | Small router, open firmware | Brings a travelling LAN back into the mesh, with failover between uplinks. | **Active, intermittent** |

## Mobile and wearable clients

| Function | Hardware class | What it does | Status |
|---|---|---|---|
| **Mobile approvers** (phone and tablet) | Android | Approve or deny AI actions, approve new mesh routes, and wake or reboot a client in the field. | **Active** (phone); the tablet shows as offline at times |
| **Limited watch client** | Watch | Read-only status and limited sync. | **Active in policy**, light use |
| **Mobile quarantine buffer** | Retired phone | A scanning and landing drive. Files arrive, get virus-scanned, and pass on to the orchestrator for review. | **Planned** |

## Memory and archive

| Function | Hardware class | What it does | Status |
|---|---|---|---|
| **Long-term archivist (vault)** | Local disk now; a separate machine is planned | Write-once history, logs, audits and chat exports. | **Active** (local vault). The dedicated machine on its own direct link is **Planned**. |
| **Internal auditor** | Small desktop, CPU-only model | Weekly review of sandbox traffic logs. | **Planned** |
| **Creative and failover node** | Server-class | Hosts the creative workspace and a second LLM. Takes over if the orchestrator loses its heartbeat. | **Planned** |
| **Credential vault** | Dedicated drive or host | Recovers a wiped client and reissues its identity. | **Planned** |

## IoT and sandbox devices
Cameras, floodlights, plugs, a thermostat, smart speakers, a TV, a printer and a hub live on isolated segments. They are observed, not trusted, and the orchestrator watches how they behave. Work in progress here includes onboarding problems on one segment, and a TV with no internet that needs a fix in the controller's web interface.

## How the clients interact

```mermaid
flowchart TB
    subgraph Approve["Approval"]
        Mobile["Mobile approvers"]
    end
    subgraph Core["Core"]
        Brain["AI orchestrator<br/>Seravo-0"]
        Vault["Long-term archivist"]
        Hands["Local repair model"]
    end
    subgraph Edge["Edge"]
        Scout["Edge scout / console"]
        Medic["Mobile medic client"]
        Hub["Windows hub<br/>mirror-port relay"]
        Travel["Travel router"]
    end
    subgraph Net["Network"]
        Ctl["Controller"]
        GW["Gateway + switch + APs"]
        IoT["IoT sandbox segments"]
    end
    Scout -- Ingress drop folder --> Brain
    Medic -- telemetry --> Brain
    Hub -- neighbour data --> Brain
    Brain -- poll, read-only --> Ctl
    Hub -. relay if direct path fails .-> Ctl
    Ctl --- GW --- IoT
    Travel --- GW
    Brain -- bounded repair requests --> Hands
    Brain -- logs, audits --> Vault
    Brain -- approve / deny request --> Mobile
    Mobile -- decision --> Brain
    Brain -- push approved scripts --> Scout
    Brain -- wake / heal --> Medic
```

### Interaction rules in plain language
- **Hub and spoke.** Edge clients run a small reporting agent with no local LLM. They report to the orchestrator and take approved work from it.
- **LAN first, mesh second.** Clients use the local network when they can and the encrypted overlay when they cannot.
- **Identity before address.** The orchestrator finds a client by its hardware identity first. Addresses are only a last resort and never override hardware evidence. A client whose identity is in doubt gets no work.
- **Ingest.** A chat or note saved into the Ingress folder crosses to the vault, is archived and indexed, and is treated as information only. See [workflow.md](workflow.md).
- **Outbound scripts.** The orchestrator stages scripts it has reviewed, and a human approves them before they reach clients.
- **Wake and heal.** A healer checks a client over the LAN, then over the mesh, then wakes it using its registered hardware identity. Only clients marked wake-required are woken, and mobile clients only on explicit request.
- **Alerts.** Phone notifications fire on a state change only, not on every check.
- **Controller access.** The orchestrator talks to the controller directly first, and falls back to a relay through the Windows hub. Certificate checks stay on.
- **Changes.** Nothing alters the live controller, the inventory or a trust anchor without an explicit apply step and a backup first.
- **External AI.** Cloud assistants are rate-limited by a token circuit breaker, so a runaway loop cannot spend the budget.

## Scheduled behaviour (shape only)
- A weekly maintenance window with a wake-up beforehand.
- A weekly auditor review.
- Frequent health, signal-tuning and IoT-guard checks, and daily fleet discovery.
- Hourly sync of the shared repository.

## Known open issues (honest status)
- Remote shell access to several clients is blocked on their side, and fingerprints are pinned only when supplied out of band.
- Some inventory records conflict on identity, so dispatch to those clients is disabled until a person confirms them.
- A few controller options cannot be set through its API and need the web interface.
- A credential found in a service file was quarantined and still needs rotating.
- The security-training simulation (honeypot segment, tarpit, quarantine, thermal breaker) was run as a dry run only. None of it is applied to the live network.
