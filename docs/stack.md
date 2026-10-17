# Operating systems and software

Product names and categories only. Versions, configurations, hostnames and ports are withheld on purpose.

## Hardware by vendor
- **Dell:** Precision laptops (orchestrator and operator console), OptiPlex micro-PCs, a 5000-series laptop, a USB-C dock and reconditioned laptops. Exact models `[REDACTED]`.
- **TP-Link Omada:** hardware controller, wired VPN router, managed switch and EAP access points. Firmware and configuration `[REDACTED]`.
- **GL.iNet:** OpenWrt travel router.
- **TP-Link travel router (planned):** second, backup travel router with a cellular hotspot for uplink failover.
- **Samsung Galaxy and other Android:** phones and a tablet.
- **Windows laptop and PC**, a **Linux laptop with an NVIDIA GPU**, a smartwatch, and IoT devices (floodlights, cameras, plugs, an Emerson Sensi thermostat, a Legrand gateway, Google Nest speakers, a TV, a printer).

## Operating systems
- **Pop!_OS (Ubuntu-based Linux, 24.04 LTS):** the AI compute backbone: the central brain and the other heavy AI nodes. Chosen for its out-of-the-box NVIDIA GPU handling and power management for local inference, and for a solid systemd base for the scheduled jobs.
- **Debian Linux:** a subnet-router node.
- **Android:** mobile approvers and the architect's uplink.
- **OpenWrt:** the GL.iNet travel router.
- **Windows 10/11:** kept on purpose, not by accident. The fleet does not force a Linux-only world, so Windows tools and workflows that have no good Linux equivalent stay available. The Windows hub joins the mesh and runs a native Python telemetry agent that bridges it to the Linux core.

## Linux services and tooling
- **systemd:** timers and services for scheduled jobs.
- **Docker and Docker Compose:** keeps the host clean and avoids dependency clashes. Hosts the chat front end (Open WebUI) and the vector store behind archive memory `[REDACTED: ports, volumes]`. Untrusted code and packet analysis are meant to run in short-lived sandbox containers.
- **Samba:** a shared audit folder for clients. `[REDACTED: shares, accounts, paths]`
- **cron:** lightweight scheduled checks on clients.
- **ntfy:** push notifications to phones.
- **Git and GitHub CLI:** version control and sync.
- **SSH:** key-based remote access between clients.

## Network
- **Tailscale:** the encrypted mesh overlay that joins every client. `[REDACTED: tags, ACLs, routes, keys]`
- **TP-Link Omada SDN:** gateway, switching and Wi-Fi management through the hardware controller. `[REDACTED: sites, VLANs, SSIDs, credentials]`

## AI stack
- **Ollama:** runs the local models.
- **Models:** Qwen2.5-Coder (three sizes), Llama 3, and a custom Seravo-0 model.
- **Aider:** applies bounded code repairs.
- **LiteLLM:** gateway between tools and models.
- **Open WebUI:** chat front end for local models.
- **Cloud assistants:** Gemini, GitHub Copilot, Claude Code, Codex and Continue.

See [program-logic.md](program-logic.md) for how these pieces connect.

## Languages and libraries
- **Python 3** with virtual environments, plus Bash and PowerShell.
- Libraries for file watching, HTTP, system metrics and web APIs.

## Editor
- **VS Code** with Python, Pylance, Bash and PowerShell support, used over SSH from other clients.
