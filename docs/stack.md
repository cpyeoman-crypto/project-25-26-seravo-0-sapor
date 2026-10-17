# Operating systems and software

Names and categories only. Versions, configurations, hostnames and ports are withheld on purpose.

## Operating systems
- **Pop!_OS (Ubuntu-based Linux):** the central brain and several workstations and scouts.
- **Debian Linux:** a subnet-router node.
- **Android:** mobile approvers and the architect's uplink.
- **Windows 10/11:** a management hub and workstations.

## Linux services and tooling
- **systemd:** timers and services for scheduled jobs.
- **Docker and Docker Compose:** container host for the chat front end.
- **File sharing:** a shared audit folder for clients. `[REDACTED: service details]`
- **cron:** lightweight scheduled checks on clients.
- **ntfy:** push notifications to phones.
- **Git and GitHub CLI:** version control and sync.
- **SSH:** key-based remote access between clients.

## Network
- **Encrypted mesh VPN overlay:** joins every client. `[REDACTED: product and configuration]`
- **Software-defined networking controller:** gateway, switching and Wi-Fi management. `[REDACTED: product and configuration]`

## AI stack
- **Ollama:** runs the local models.
- **Models:** Qwen2.5-Coder (three sizes), Llama 3, and a custom Seravo-0 model.
- **Aider:** applies bounded code repairs.
- **LiteLLM:** gateway between tools and models.
- **Open WebUI:** chat front end for local models.
- **Cloud assistants:** Gemini, GitHub Copilot, Claude Code, Codex and Continue.

## Languages and libraries
- **Python 3** with virtual environments, plus Bash and PowerShell.
- Libraries for file watching, HTTP, system metrics and web APIs.

## Editor
- **VS Code** with Python, Pylance, Bash and PowerShell support, used over SSH from other clients.
