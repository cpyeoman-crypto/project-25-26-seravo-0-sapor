# Illustrations: how it all fits together

Diagrams only show roles and flows. Names, addresses, schedules in exact form and file paths are `[REDACTED]`. The diagrams render on GitHub.

## 1. The big picture

```mermaid
flowchart TB
    subgraph Field["In the field"]
        Phone["Approver phone<br/>(ntfy app)"]
        Travel["Travel router"]
        Backup["Backup router +<br/>cellular hotspot (planned)"]
        Medic["Mobile medic client"]
    end
    subgraph Uplinks["Internet uplinks"]
        Sat["Satellite"]
        Cell["Cellular (planned)"]
    end
    subgraph Home["Home network"]
        GW["Gateway + switch + access points"]
        Ctl["Network controller"]
        IoT["IoT sandbox segment"]
        Scout["Edge scout / console"]
        WinHub["Windows hub<br/>mirror-port relay"]
        Enf["Edge enforcer (planned)"]
    end
    subgraph Core["Seravo-0 core"]
        Brain["AI orchestrator"]
        Hands["Local repair model"]
        Vault["Write-once archivist"]
        Ntfy["Notification publisher"]
    end
    Sat --> GW
    Cell -. failover .-> GW
    Backup -. standby .-> Cell
    GW --- Ctl
    GW --- IoT
    Brain -- "read-only poll" --> Ctl
    Brain -- "probe, wake, heal" --> Scout
    Brain -- "probe" --> WinHub
    WinHub -- "neighbour data" --> Brain
    Medic -- "heartbeat" --> Brain
    Travel -- "mesh" --> Brain
    Brain --> Ntfy -- "push (outbound HTTPS)" --> Phone
    Phone -- "approve / deny" --> Brain
    Brain -- "bounded repair requests" --> Hands
    Brain -- "logs, audits" --> Vault
    Enf -. "sandbox logs" .-> Brain
```

## 2. From a network event to a phone alert

```mermaid
sequenceDiagram
    participant D as Device
    participant C as Controller
    participant W as Client alert watcher
    participant S as State cache
    participant N as ntfy
    participant P as Phone
    D->>C: joins, leaves or roams
    loop every 2 minutes
        W->>C: read-only: list live clients and uplinks
        W->>S: compare with last known state
    end
    alt state changed
        W->>W: map device to a friendly name
        W->>N: [Network Event] Name, IP, VLAN
        N->>P: push (priority by event kind)
        W->>S: save new state
    else no change
        W-->>S: nothing sent
    end
```

The payload format is fixed, so every alert reads the same way:

```
[<Network type> <Event>] Name: <mapped client name> | IP: <address> | VLAN: <segment>
```

In real messages the address and segment are redacted in this repository. See [report-examples.md](report-examples.md).

### Escalation

```mermaid
flowchart LR
    E["Event"] --> K{"What kind?"}
    K -- "Client joins or leaves (LAN/WLAN)" --> P3["Priority 3<br/>default info"]
    K -- "Unknown device, node offline,<br/>healing failed" --> P4["Priority 4<br/>high"]
    K -- "Uplink dropped, traffic failed over" --> P5a["Priority 5<br/>urgent: says failed over"]
    K -- "All uplinks down" --> P5b["Priority 5<br/>urgent: says ALL UPLINKS DOWN"]
    K -- "Test, weak-signal reconnect" --> P2["Priority 2<br/>low"]
```

## 3. Self-healing loops

```mermaid
flowchart TB
    subgraph Wifi["Weak Wi-Fi clients: signal optimiser"]
        W1["Find clients below the weak-signal threshold"] --> W2{"Weak for how long?"}
        W2 -- "15 min" --> W3["Reconnect once, so it can pick a stronger access point"]
        W2 -- "30 min" --> W4["Reconnect again"]
        W2 -- "60 min" --> W5["Last reconnect, then mark as settled"]
    end
    subgraph Iot["IoT segment: IoT guard"]
        I1["Patrol the IoT segment"] --> I2{"Absent, or holding a<br/>link-local address?"}
        I2 -- yes --> I3["Reconnect, then audit the address reservation"]
        I3 --> I4["Push: absent, failed or rejoined (with delay)"]
    end
    subgraph Fleet["Fleet nodes: healer"]
        F1["Read mesh peer list"] --> F2{"Critical node down?"}
        F2 -- yes --> F3["Resolve by hardware identity"]
        F3 --> F4["Wake-on-LAN (LAN, then relay)"]
        F4 --> F5["Cooldown, so one failure is one alert"]
    end
```

All three run dry-run until an apply flag is given. The healer only wakes clients marked wake-required.

## 4. Credential hygiene

```mermaid
flowchart LR
    Script["Script needing a login"] --> Loader["Credential loader"]
    Loader --> Env[("Locked file outside the repository<br/>owner-only permissions")]
    Import["Importing a new script"] --> Scan{"Embedded password,<br/>token or RDP login?"}
    Scan -- yes --> Quar["Quarantine: never committed"]
    Scan -- no --> Cat["Catalog"]
    New["Adopting a new node"] --> Pin["Verify SSH host-key fingerprint independently"]
    Pin --> Ok["Adopt"]
    Ctrl["Controller with a self-signed certificate"] --> CA["Trust its certificate explicitly<br/>(TLS checking stays on)"]
```

## 5. Self-regenerating fleet

```mermaid
flowchart LR
    Repo["Reviewed repository<br/>scripts, units, prompts"] --> Sync["Fleet autosync<br/>every 30 minutes"]
    Sync --> A["Linux client A"]
    Sync --> B["Linux client B"]
    Sync --> C["Future clients"]
    Sync --> Rep["Push only when a node's result changes"]
```

Every adopted Linux client receives the same scripts, scheduled-job definitions and prompts, so the whole fleet learns a new protocol at the same time.

## 6. Where the novel fits

```mermaid
flowchart LR
    Net["Security mesh"] --- Failover["Creative and failover node"]
    Failover --> Novel["Writing workspace<br/>(kept separate from the security mesh)"]
    Failover -. "takes over if the orchestrator goes quiet" .-> Brain["AI orchestrator"]
```

See [novel-and-seravo.md](novel-and-seravo.md).
