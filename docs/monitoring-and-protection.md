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

## Levels of authority
- **Edge view:** local stats and a high-level status of other nodes.
- **Admin view:** the full picture, available only to admin-tier clients.

## Recovery
A planned vault holds credentials and system states so a lost or compromised client can be rebuilt quickly and issued a new identity.
