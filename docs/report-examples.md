# Report examples (redacted)

These are what arrives on the phone, rebuilt with invented values. Real client names, addresses, hardware identities, access point names and counts are replaced by `[REDACTED]` or by placeholders such as `client-a`. The layout, wording and priorities are real. Each block shows the notification title, the priority, and the markdown body.

Background: [ntfy-alerts.md](ntfy-alerts.md). Timetable: [polling.md](polling.md).

## Events (sent when something changes)

### Device joined the Wi-Fi
**Title** `my-network · CLIENT CONNECT` · **Priority** 3 · **Tags** ✅ 🔌 wireless

```
## 🟢 CLIENT CONNECT

[WLAN Connect] Name: client-a | IP: [REDACTED] | VLAN: [REDACTED]

- **MAC** `[REDACTED]`
- **Category** `IoT`
- **Link** `WLAN`
- **Access point** `[REDACTED]`
- **Network** `[REDACTED: isolated IoT segment]`

*my-network · hub · 2026-01-01 08:02:11 UTC*
```

### Internet uplink dropped, traffic failed over
**Priority** 5 (urgent) · **Tags** 🚨 ⚠️

```
## 🚨 WAN DROP

[WAN Drop] Name: gateway uplink 1 | IP: [REDACTED] | VLAN: N/A

- **Gateway** `[REDACTED]`
- **Port** `[REDACTED]`
- **Outcome** `Failed over to remaining uplink`
- **Uplinks up** `1/2`
```

When every uplink is down, the outcome reads `ALL UPLINKS DOWN`. This is the message the planned backup travel router and cellular hotspot are meant to answer.

### Mesh node offline
**Priority** 4

```
## 📡 NODE OFFLINE · edge-scout-1

Edge scout did not answer on LAN, mesh or last-known address.

- **Node** `edge-scout-1`
- **Role** `Edge scout / console`
- **Wake required** `true`
```

### Fleet healing summary
**Priority** 3, or 4 if any node did not recover

```
## 🔧 FLEET HEALING · 2 recovered, 1 still down

- ✅ client-b is reachable again; SSH verified
- ✅ client-c woke after Wake-on-LAN
- ❌ client-d did not recover (down 5h)

- **Method** `Wake-on-LAN (local broadcast, then relay)`
```

### Unknown device
**Priority** 4

```
## 🆕 UNKNOWN DEVICE

[LAN New] Name: [REDACTED] | IP: [REDACTED] | VLAN: [REDACTED]

First seen on the switch mirror port. Not in the reviewed inventory.
```

### IoT reconnect watch
**Priority** 4

```
## 🛡️ IOT RECONNECT WATCH

- 🔴 **thermostat** absent for 45 min
- 🟠 **home-automation gateway** holding a link-local address (address request failed)
- 🟢 **thermostat** rejoined after 52 min

- **Infrastructure uptime** `gateway up, switch up, access points up`
```

### Mesh node connected from outside
**Priority** 3

```
## 🟢 TAILSCALE CONNECT

[Tailscale Connect] Name: client-a | IP: [REDACTED mesh address] | VLAN: N/A

- **Path** `[REDACTED: direct or relay]`
```

### Autosync blocked a script
**Priority** 4

```
## 🚫 SYNC BLOCKED

- ❌ `[script]` contains what looks like a credential and was stopped before syncing
- ✅ other changes synced to [n] clients
```

### Hardware attention (from a collector)
**Priority** 4

```
## 🌡️ HARDWARE ATTENTION · client-b

- 💽 Disk ▰▰▰▰▰▰▰▰▰▱ **91%**
- 🎮 GPU driver not active
- ⚙️ **[n]** failed systemd units
```

### Online but not reporting
**Priority** 3

```
## 🔭 ONLINE BUT NOT POLLED · 2 open, 1 changed

- client-e: no remote access yet (key not accepted)
- client-f: remote shell service not running
```

## Reports (sent on a schedule)

### Morning briefing, 07:00
**Priority** 3, or 5 if the internet is down

```
## ☀️ MORNING BRIEFING

☀️ **Internet up** · 2/2 uplinks

- 🟢 **gateway uplink 1** — connected
- 🟢 **gateway uplink 2** — connected

### 📶 Clients · [REDACTED COUNT]
- **WLAN** [n]  **LAN** [n]
- VLANs: `untagged`×[n] · `[REDACTED]`×[n]
- Types: IoT [n] · Computer [n] · Mobile [n]

### 🔐 Mesh · [n] online
client-a, client-b, client-c

### 🛸 Satellite dish
⏱️ [n] ms · 💧 [n]% drops · 🌲 [n]% obstructed
```

### Daily status, 07:10
**Priority** 3 when green, 4 when something needs attention

```
## 🩺 DAILY STATUS · ALL GREEN

✅ **All nodes green**

### 🖥️ Orchestrator
- Uptime **[n] days** · kernel `[REDACTED]`
- Load `[n] [n] [n]` on [n] cores
- Memory ▰▰▰▰▱▱▱▱▱▱ **[n]%** of [n] GB
- Disk / ▰▰▰▰▰▰▱▱▱▱ **[n]%** · [n] GB free
- Vault ▰▰▱▱▱▱▱▱▱▱ **[n]%**

### ⚙️ Automation
**[n]** services and timers healthy

### 🛰️ Mesh
🟢 client-a, client-b, client-c
```

With a problem:

```
## 🩺 DAILY STATUS · ATTENTION

⚠️ **2 item(s) need attention**

- 🕰️ Controller telemetry snapshot is [n] h old
- 📨 [n] message(s) waiting in the retry spool
```

### Hardware overview, 07:20
```
## 🌡️ HARDWARE OVERVIEW

- CPU ▰▰▱▱▱▱▱▱▱▱ **[n]%** · [n] threads · load [n]
- RAM ▰▰▰▰▱▱▱▱▱▱ **[n]%** of [n] GB
- GPU ▰▱▱▱▱▱▱▱▱▱ **[n]%** · [n] °C
- 💽 `[REDACTED mount]` ▰▰▰▰▰▱▱▱▱▱ **[n]%**
```

### AI, pipeline and mesh overview, 07:30
```
## 🧠 AI · PIPELINE · MESH

### 🧠 LLM status
🟢 **orchestrator** · [n] model(s) · served by `[REDACTED].service`
    - `[model]` [n] GB · loaded · GPU/CPU · [n] GB resident

### 🔬 Pipeline
🟢 **Ingest watcher** `[REDACTED].service` · running since [time]
🟢 **Scheduler service** `[REDACTED].service` · running

**Schedulers**
🟢 `[timer]` · last run [time] · result success
🟠 `[timer]` · last run [time] · result success · **STALLED**
- 📶 Controller telemetry snapshot **[n] h** old
- 📨 Notification spool backlog **[n]**

### 🛰️ Mesh routes
🟢 **client-a** · [n] ms · direct · rx [n] MB / tx [n] MB · advertises `[REDACTED]`
🔴 **client-c** offline · Windows
**Subnet routes via mesh:** `[REDACTED]`
```

A node routed through a relay instead of directly is flagged in the warnings.

### Fleet census, 08:00
```
## 📋 FLEET CENSUS · [n] clients · [n] mesh nodes

### 🔐 Mesh · [n]/[n] online
- 🟢 **client-a** `[REDACTED]` Linux
- 🟢 **client-b** `[REDACTED]` Windows
- 🔴 **client-c** `[REDACTED]` Linux

### 🏷️ Segment [REDACTED] · [n]
- 📶 **client-d** `[REDACTED]` ⭐ fleet node
- 🔌 **client-e** `[REDACTED]`

- **Fleet-mapped clients** `[n]`
- **Unmapped** `[n]`
```

### Nightly audit with AI analysis, 02:00
```
## 🌙 NIGHTLY AUDIT · 2026-01-01

**Fleet facts**
- Clients: [n] total, [n] wireless, [n] wired.
- Clients per access point: [REDACTED].
- Weak-signal clients (<40): [n] named in the full report.
- Poor health score (<50): none.
- Top talkers: [REDACTED].

**🧠 AI analysis**
- [Short bullets from the local model, based only on the facts above.]
- If the model times out: "Local model timed out; facts above are authoritative."
```

The model is told to use only the listed facts and not to invent hardware. The same text is archived in full.

### Link speed and satellite poll, every 4 hours
**Priority** 3, with "ATTENTION" added to the headline when a threshold is crossed

```
## 🚀 SPEED & SATELLITE POLL

✅ **All systems nominal**

### 🌐 WAN speed test
⬇️ **[n] Mbps** (trend vs the last 7 days)
⬆️ **[n] Mbps** (trend)
⏱️ **[n] ms** to [REDACTED test server]

### 🛸 Satellite dish
⏱️ PoP latency **[n] ms** · 💧 drops **[n]%** · 🌲 obstructed **[n]%**

### ⚡ Network path
Internet host: avg **[n] ms** · loss [n]%
Router LAN port: ARP **reachable**
Mesh link to a field node: **[n] ms** via [direct or relay]
```

Thresholds: a download below 10 Mbps or latency above 150 ms adds a verdict line. Forty-two polls (seven days) are kept for the trend arrows. If the dish cannot be reached, the dish section says so instead.

## What is never in a message

Hardware identities, full address plans, keys, tokens, passwords, device serials and file paths on the vault. Where a report would show them to the owner, this repository replaces them with `[REDACTED]`.
