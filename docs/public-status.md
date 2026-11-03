# Anonymous status display

The [tablet-friendly display](index.html) reads `status.json` once per minute.
It does not connect to a private notification server or receive its credentials.

The publisher constructs fresh structured output privately using a persistent,
owner-only HMAC key. Real identifiers never become display aliases directly.
Only these fields are accepted:

- Schema version `1`.
- Nodes: a keyed `client-` alias, an enumerated state, optional CPU/RAM/disk
  percentages between 0 and 100.
- Incidents: a keyed `incident-` alias, an enumerated state and priority 1-5.
- Events (optional, at most 50): a keyed `client-` alias, an enumerated public
  event kind, priority 1-5 and a coarse age in minutes (up to one week). The
  kind vocabulary is fixed and generic (`connect`, `uplink-drop`, `healing`,
  `report`, `pulse`, ...): it names the shape of a notification, never its text.

No raw message, title, MAC/IP address, owner, login, hostname, credential,
private URL or alias key may be uploaded. Masking raw alert text is not safe.
Both the publisher and browser reject unknown fields. The browser inserts text,
not HTML. Incident aliases and client aliases use separate namespaces.

The masked feed exists to show how the notification pipeline works, live,
without disclosing it: the same machine keeps the same made-up alias across the
client grid and the feed (stable keyed aliasing), kinds come only from the fixed
vocabulary, and ages are coarse relative offsets, not clock timestamps. Event
rows reuse the `client-` namespace so cross-referencing stays consistent.

Node presence describes observations, not successful SSH/RDP or device health.
Old monitoring observations become `unknown`; disappearance does not prove the
cause of an outage. The UI explicitly does not certify source freshness.
Public snapshots can expose aggregate activity and incident counts even without
identities. Do not publish metrics if those aggregates are confidential.

The initial empty snapshot is not a success/health claim. Publication requires
an authorized private exporter and a locally authenticated GitHub publisher.
The page never performs remediation. If publication fails, it retains the prior
snapshot; it must not fabricate healthy results.

Run schema fixtures with:

```sh
node docs/test-status.cjs
```
