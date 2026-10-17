# Design principles

1. **Local first.** Seravo-0, its repair model and its data stay on the network's own hardware. Cloud assistants may advise, but they never run operations or see the live network.
2. **Human in the loop.** The AI proposes, a person approves. Consequential actions are never automatic.
3. **Fail defensively.** The security edge is allowed to fail closed. A blocked device is better than an exposed network.
4. **Separation of concerns.** The creative node is kept apart from the security nodes, and each can back the other up without sharing data by default.
5. **Least privilege.** Four access tiers, and mobile devices never route for the network.
6. **Idempotent scripts.** Every deployment script can be run twice safely. A "golden standard" set of scripts keeps every client consistent.
7. **Self-healing, with limits.** Clients are meant to update themselves and restart their own tunnels, but not to change policy on their own.
8. **Immutable memory.** Long-term logs are written once and never edited.
9. **Roles, not names.** Every client has a role. Hardware can change without the design changing.
