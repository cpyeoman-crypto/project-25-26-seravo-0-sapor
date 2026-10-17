# Monitoring and protection

## What is watched
- **Client health:** liveness, temperature, memory and disk pressure.
- **Network behaviour:** routing state, unexpected route advertisements, tunnel stability.
- **Untrusted devices:** everything on the isolated sandbox segment, especially cheap or unknown IoT hardware.
- **Security events:** audit logs on the gateway and on each admin client.

## How protection works
1. **Contain.** Unknown and IoT devices are kept in the sandbox. The edge enforcer is allowed to fail closed.
2. **Observe.** Sandbox traffic is logged and fed to the orchestrator.
3. **Review.** A weekly audit role goes through the sandbox logs for "nuisance offenders" and anything malicious.
4. **Propose.** Seravo-0 proposes an action, such as blocking a device or reissuing a credential.
5. **Approve.** A human approves or denies it from a phone. Nothing destructive runs without that step.
6. **Record.** The action and its reason go to the long-term archivist.

## Change watching
- **Client alert watcher.** A continuous watcher compares the controller's live client records with a cached last-known state and captures every transition on the network (connect, disconnect, roam, uplink change).
- **Fixed alert format.** `[<Network type> <Event>] Name: <mapped client name> | IP: <address> | VLAN: <segment>`. Address and segment values are redacted in this repository.
- **Escalation.** An uplink drop is urgent (priority 5) and says whether the gateway failed over or every uplink is down. Ordinary LAN and Wi-Fi connections are default-priority information. See [ntfy-alerts.md](ntfy-alerts.md).

## Self-healing and optimisation
- **Signal optimiser.** Finds Wi-Fi clients with a weak signal and forces a reconnect at staged intervals (15, 30 and 60 minutes), so a client can land on a stronger access point. Persistent weak signals are eventually marked as settled.
- **IoT guard.** Patrols the isolated IoT segment for devices that disappeared or are stuck on a link-local address, triggers a reconnect and audits the address reservations.
- **Fleet healer.** Watches the mesh peer list and sends a Wake-on-LAN packet when a critical node drops, with a cooldown to prevent alert fatigue.
- **Fleet autosync.** Pushes the reviewed scripts, scheduled-job definitions and prompts to every adopted Linux client every 30 minutes, so the fleet learns new protocols together.

All of these are dry-run until applied. Diagrams: [illustrations.md](illustrations.md).

## Credential hygiene
- **Zero-trust storage.** No passwords, API keys or private certificates live in the repository history. Scripts that need a login read it through one loader from an owner-only file kept outside the repository `[REDACTED: location]`.
- **Automated scrubbing.** The import tool quarantines any script that embeds a password, token or remote-desktop login before it reaches the catalog.
- **Host-key pinning.** Adopting a node requires independent verification of its SSH host-key fingerprint, which protects against interception while the network grows.
- **Certificates.** A controller with a self-signed certificate is trusted by explicitly passing its certificate to the tools. TLS verification is never turned off globally.

## Levels of authority
- **Edge view:** local stats and a high-level status of other nodes.
- **Admin view:** the full picture, available only to admin-tier clients.

## Recovery
A planned vault holds credentials and system states so a lost or compromised client can be rebuilt quickly and issued a new identity.
