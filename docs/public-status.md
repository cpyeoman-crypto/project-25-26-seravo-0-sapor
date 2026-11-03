# Anonymous status display

The [tablet-friendly display](index.html) reads `status.json` once per minute.
It does not connect to a private notification server or receive its credentials.

The publisher constructs fresh structured output privately using a persistent,
owner-only HMAC key. Real identifiers never become display aliases directly.
Only these fields are accepted:

- Schema version `1`.
- Incidents: a keyed `incident-` alias, an enumerated state and priority 1-5.
- Nodes: a keyed `client-` alias, an enumerated state, optional CPU/RAM/disk
  percentages between 0 and 100 (accepted in the snapshot; not displayed).
- Events (optional, at most 50): masked replicas of the delivered phone
  notifications — a fleet-role label (`hub`, `ap`, `assistant`, `printer`,
  `iot floodlight`, …), an enumerated kind, the masked title and body with the
  phone's own layout, priority 1-5 and a coarse age in minutes (up to one week).

Masked text must satisfy hard rules enforced by the exporter, the publisher and
the browser: devices appear only as fleet-role labels; every IPv4 address must
be an RFC 5737 documentation stand-in (`192.0.2.*`, `198.51.100.*`,
`203.0.113.*`); every hardware identity must be an `02:00:00` stand-in; the
private site/topic vocabulary is rejected outright; timestamps, VLAN numbers,
internal artifact names and any value not meant for other eyes are replaced by
`X`. A message that still contains any known private term after masking is
published as a bare `X`. Stand-ins are assigned consistently, so the same
device keeps the same role label and the same fake identifiers.

No raw MAC/IP address, owner, login, hostname, credential, private URL, topic
or alias key may be uploaded. Both the publisher and browser reject unknown
fields and unmasked identifiers. The browser inserts text, not HTML.

The masked feed exists to show how the notification pipeline works, live,
without disclosing it: it is produced from a read-only poll of the same
delivered notification stream the phone subscribes to, with the same icons,
titles and body layout. Clients are not listed separately: role labels in the
feed are the only public description of the fleet's members.

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
