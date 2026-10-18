# Workflow: from copy-paste to Ctrl-S to VS Code

**Historical/target workflow:** the public kit does not include an ingest watcher, archival hooks or a command dispatcher. Its [local project checker](monitoring-and-protection.md#local-project-maintenance) reads evidence only. Neither evidence nor archived text authorises execution.

## Stage 1: copy and paste
Ask a cloud assistant, copy its command, paste it into a terminal, then paste the output back. It works, but every step is manual, and the history lives only in the browser.

## Stage 2: save and ingest
The workflow changed once the useful part became the conversation itself:

1. Press **Ctrl-S** on a chat page and save it into the **Ingress** folder.
2. A small watcher service notices the new file and waits for the write to finish.
3. It moves the file into the history archive, adding a timestamp if the name already exists so nothing is overwritten.
4. Seravo-0 can then learn from that history.

The proposed Ingress folder is a one-way archival drop box. Tagged deployment text may be indexed for review, but must never be executed or used to trigger commands. Any later action requires a separately reviewed instruction and explicit authorisation outside the ingested content.

### Browser export and archive hygiene (target pattern)

The operator describes a Tampermonkey browser userscript that strips HTML/chat-page
boilerplate and exports reduced JSON for ingestion. Its source and live operation
have not been verified in this public kit. Treat it as an untrusted local export
helper, with this lifecycle contract:

1. Convert HTML to a reduced JSON payload in the client workspace.
2. Place the JSON into the ingress drop path.
3. Archive the received JSON only after write-complete checks and provenance,
   size and hash recording. Receipt is not proof of successful processing.
4. Move successfully processed material to the **learned** state with a durable
   record of what was indexed; failed or suspicious material stays quarantined.
   "Learned" is a processing state, not proof that model weights were trained.
5. Delete the specific client-side source/export copy only after verifying the
   matching archive hash and successful-processing receipt under the operator's
   retention policy. A timer, folder name or elapsed time alone is not approval.

This repository does not ship that userscript and does not treat exported text as
trusted instructions. If you add such a flow privately, keep source, transformed
JSON, archival hash/provenance and deletion decisions auditable.

The locally inspected watcher establishes an ingress-to-archive move, not the
complete JSON validation, learned promotion or client-cleanup contract above.
The archive/drop locations available during review contained no prompt exports;
the public overview therefore does not claim a full archive-content review.
Keep raw exports and extracted code private and inert; an executable file extension
or permission bit must never grant an ingested block authority to run.

## Stage 3: editor-centred
Work moved into **VS Code** on the central node, reached from the other clients over SSH:

- Several assistants work in the same workspace, each inside its tier.
- A hook in the user-level assistant settings archives every prompt and every reply, plus the full session transcript, into a shared archive.
- The shared repository syncs to each client, from GitHub first and from the network mirror second.
- Failures can be handed to the local repair model with the full trace, which closes the loop from a failing script to a checked fix.

## What the workflow achieves
- No more lost context: the chats are saved, indexed and searchable.
- Less copy-paste: the editor and the hooks do the carrying.
- A safer loop: AI text is advice until Seravo-0's checks and a human approve it.
