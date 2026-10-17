# Glossary

| Term | Meaning |
|---|---|
| Seravo-0 | The AI that monitors and helps protect the network. |
| Mesh network | A private network where devices reach each other through an encrypted overlay, wherever they are. |
| Client | Any device that joins the mesh and has a role. |
| Orchestrator | The central machine that runs the LLM, sandbox and short-term memory. |
| Scout | A lightweight edge client that reports to the orchestrator. |
| Enforcer | The gateway-edge security node. |
| Archivist | The long-term, write-once vault for logs and history. |
| Sandbox | An isolated network segment for untrusted or IoT devices. |
| Subnet router | A machine that makes a local network reachable through the mesh. |
| Human in the loop | A person approves or denies AI actions before they run. |
| Vector database | A store that finds related items by meaning, used here for short-term memory. |
| Quantised model | A smaller, faster version of an LLM that trades a little accuracy for less memory. |
| Idempotent | Safe to run many times with the same result. |
| ntfy | An open-source push-notification service. The network publishes to a private topic and phones subscribe. |
| Heartbeat | A small health file a client writes on a timer. Silence from the client is itself an alert. |
| Polling | The hub asks a controller or client for its state, instead of waiting to be told. |
| State-change alert | An alert sent only when something changes, not each time it is checked. |
| Spool | A small on-disk queue that holds notifications that could not be delivered until the next send. |
| Failover | Switching to a standby path, such as a cellular uplink, when the main one fails. |
| Host-key pinning | Verifying a machine's SSH fingerprint out of band before trusting it. |
