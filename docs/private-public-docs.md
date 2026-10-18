# Private fleet knowledge and vetted public documentation

## Two distinct tiers

The private tier describes the actual mesh, farm.net fleet and Seravo-0 deployment:
node roles and identities, upstream/downstream connectors, private paths and operational
conditions. Keep this in an owner-controlled **local/private repository**, outside the
public checkout. Do not put credentials in Markdown; reference an owner-only secret
store instead. A private repository is not itself encryption or access control.

The public tier is this repository: role-level architecture, reusable code, masked
examples and reviewed installation guidance. Updating it must not disclose private
addresses, host/user names, controller identifiers, notification topics or credentials.

The shipped [publisher](../starter-kit/src/docs_publish.py) implements an operator-run,
local export pipeline. It does **not** upload private documents, push commits, enable a
service, call an LLM, or grant Seravo-0 filesystem permissions. Its local knowledge index
can be consumed by a separately configured read-only retrieval adapter; that model
integration remains an explicit deployment task.

## Private configuration

Create three **separate, non-overlapping directories**: private Markdown root, public
checkout root and local review stage. Private root and stage must be owner-only (0700);
private Markdown, configuration and redaction map files must be owner-only (0600).
Symlinks, traversal, insecure private files and writable ancestors are refused.
Do not place the configuration, stage, index, map or private sources in the public
checkout, its archive or a GitHub attachment.

Create a mode-0600 JSON configuration outside the public checkout. This schema example
is deliberately non-operational; replace x paths locally:

```json
{
  "private_root": "/home/x-user/x-private-docs",
  "public_root": "/home/x-user/x-public-repo",
  "stage": "/home/x-user/x-local-review",
  "redaction_map": "/home/x-user/x-private-map.json",
  "documents": {
    "overview.md": "README.md",
    "operations.md": "docs/monitoring-and-protection.md"
  }
}
```

`documents` is an explicit source-to-public-path allowlist, never a recursive copy.
Public paths must use plain filename components, end in `.md`, and be unique.
Include **all** public Markdown in the mapping before expecting a healthy publication
verdict. Private files that are not mapped are never exported.

The private redaction map is a nonempty JSON object mapping each real term to a public
role label or x placeholder. Keys must have at least three characters. Do not use real
values in public examples. Matching is case-insensitive, longest term first.
Replacements must not contain any configured private term. Review the map for the actual
fleet's node/user names, internal domains, VLAN/site identifiers, paths and connector IDs:
there is no reliable generic detector for every identifying term.

## Authoring controls

Use these literal markers in the private Markdown:

```text
Public role description.
<!-- private:start -->
Private deployment details belong only in this region.
<!-- private:end -->
<!-- public-only: Public description replacing omitted operational detail. -->
```

Private regions are removed. Public-only text is inserted at its marker. Nesting,
unbalanced or malformed reserved markers fail the render. A file starting with YAML
front matter containing `publish: false` is skipped completely. Do not use private
filenames as public output names: the allowlist names outputs explicitly.

Known address, MAC, email, mesh-domain, notification URL, token and credential-assignment
patterns are masked with x placeholders. Loopback, unspecified bind addresses and
RFC documentation address ranges are retained as **functional/example constants**, not
live inventory. An unremoved private-key block is refused rather than partly masked.
The post-render scanner rejects surviving known private terms/patterns; its Python
`scan` API returns line numbers only, not matched values. CLI errors are generic and do
not echo private text or source paths.

## Edit, stage, review, apply

Run from the starter-kit directory; all paths below are masked examples:

```sh
python3 fleetctl.py docs stage --config /home/x-user/x-docs-config.json
python3 fleetctl.py docs audit --config /home/x-user/x-docs-config.json
python3 fleetctl.py docs apply --config /home/x-user/x-docs-config.json --reviewed
python3 fleetctl.py docs check --config /home/x-user/x-docs-config.json
python3 fleetctl.py docs index --config /home/x-user/x-docs-config.json
```

1. Edit the private sources and map for a fix, addition or new connector facet.
2. Stage explicitly. Only the local stage is written: `rendered/`, `review.diff` and
   `manifest.json`. A preexisting `rendered/` is refused to preserve the prior review.
   Use a new empty stage for the next review; retain/delete old review artifacts
   deliberately according to your private retention policy.
3. Review every rendered file and the **redacted diff**, including output names, links,
   claims, deployment status and inference risks. Diff context is sanitised too, so also
   inspect the actual public baseline locally; the diff may omit a privacy-only change.
4. Apply only after review with `--reviewed`. Sources, map, config, staged bytes and
   public baseline must still match. Validation happens before writes. Each file is
   replaced atomically; the whole multi-file operation is not transactional. A write
   failure can leave a partial apply: inspect the checkout and re-stage, do not publish.
5. The local `vetted.json` records source/output/config/map hashes and a review time.
   Nothing is committed or pushed. Run tests, link checks and a final privacy review,
   then publish a reviewed PR using normal repository tooling.

Apply never deletes obsolete public files. Remove obsolete public documents manually
after checking incoming links, then update the private mapping. Do not silently remove
coverage requirements to make a report green.

**Approval is never a privacy exemption.** Stage and apply render and scan anew.
Every check rescans the current public tree, including previously vetted files;
digests alone cannot bypass scanning. `docs audit` writes owner-only `audit.json` and
prints only numbered files and offending line numbers (line 0 means a filename),
without matched values. It exits nonzero for any known leak.
If an approved public file leaks, fix the private source/map, stage afresh, review and
apply the sanitised replacement. An unmapped leaking file blocks apply until mapped
and corrected or explicitly removed following link review. Apply scans the projected
public tree before writes and rescans the actual tree after writes; a failed check
never generates fresh vetted evidence. Do not publish while audit/check fails.

For prompt-archive material, preserve provenance and privacy through the same rule:
conversion/export tools (for example browser userscripts) are untrusted helpers.
Record source hash and archival success before deleting local client copies, and
never treat converted text as executable instructions.

The stage manifest, review diff and knowledge index are **private artifacts**, even
though rendered outputs are intended for public review. Source hashes and metadata can
reveal private structure; never commit these artifacts.

## Seravo-0 knowledge access and monitoring

`docs index` writes an owner-only `knowledge-index.json` in the stage. It lists
non-hidden Markdown in both roots with path, title, SHA256, modification time, tier and
`knowledge_only: true`. Private source content remains local. Configure the actual
Seravo-0 retrieval process separately with read-only access to the private root/index;
never let document text, prompts or retrieved snippets become tool permissions or
commands. The flag is metadata, **not an enforced model sandbox**. Do not attach this
index to a cloud assistant or copy it to fleet clients.

Set `documentation_publish_config` to the absolute private configuration path in the
private maintenance policy, and select that policy via the project monitor's `--config`.
The public example deliberately leaves it null. The optional hourly project timer and
daily project summary then report **ATTENTION**, not green, when:

- publication is unconfigured or its inputs/map/permissions are invalid;
- a private source, map, policy, staged manifest or public output no longer matches its
  vetted counterpart;
- any public Markdown has no vetted output entry;
- rendering or leak checks fail, or evidence is missing, future-dated or older than one day.

The daily summary also refuses healthy publication evidence once its expiry is reached,
even before the next hourly check. Publication status does not override other failing
fleet checks or unverified connectors. Rave remains planned/disabled.

## Risks and residual responsibilities

| Risk | Built-in mitigation | Remaining responsibility |
|---|---|---|
| Redaction map, source metadata or index exposure | Owner-only private files, separate roots, no network/push commands; deploy's fixed whitelist excludes runtime private artifacts | Protect parent storage, backups, account access and retention; do not paste private artifacts into GitHub or cloud prompts |
| Marker mistakes or incomplete masking | Explicit mapping, strict markers, known-pattern masks and post-render scan | Human review is mandatory: arbitrary names, prose, topology and unknown token formats cannot all be detected |
| Stale public claims after private changes | Source/output/map/config digests, complete public Markdown coverage and one-day freshness limit | Update source/mapping, review new facets and compatibility; hashes are not proof of truth or authenticity |
| Retrieved Markdown acting as instructions | Tool only reads data and creates an index; never executes document content | Enforce read-only retrieval, tier-aware access and prompt-injection defenses in the actual Seravo-0 adapter |
| Structural inference or private Git history | Private regions omitted; public baseline conflicts and symlinks refused | Public role relationships can still reveal structure; separately assess Git history and credentials requiring rotation |

No scanner or passing test suite establishes zero leaks or an exploit-free deployment.
