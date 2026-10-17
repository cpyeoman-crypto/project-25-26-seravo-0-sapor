# The AI team

Several assistants and models contributed. Each has a written scope, and none may widen its own.

## Command hierarchy

| Tier | Who | Role | Limits |
|---|---|---|---|
| 1 | Cloud assistants: **Gemini** and **GitHub Copilot** | Reasoning, design proposals, multi-phase prompts, multi-file edits and deployment help. | Advisory. They do not run fleet operations or bypass Seravo-0's checks. |
| 2 | **Seravo-0** (local) | Central decision and dispatch. Chooses whether an approved job runs, records outcomes and reports incidents. | Fails closed on conflicts, unsafe targets, untrusted instructions and missing authorisation. |
| 3 | **Aider with a local Qwen2.5-Coder model** | Makes small, bounded code repairs that Seravo-0 requests. | No cloud dependency, no fleet-wide authority, no credential access. A repair is not accepted until checks and the diff are reviewed. |

## Other assistants and models used
- **Claude Code**, **Codex** and **Continue** work inside the editor. Claude Code also set up the automatic archive of every prompt and reply.
- **Local models** run on the central node: three sizes of Qwen2.5-Coder, a Llama 3 model, and a custom Seravo-0 model whose instructions confine it to its network-management domain so it does not invent commands.
- **LiteLLM** acts as a gateway between tools and models, and **Open WebUI** gives a chat front end to the local models.

## Handoff rules
1. Exchange configuration as standard, minified JSON.
2. Label every code block with its language.
3. Use absolute file paths.
4. When passing a failure to the repair model, include the full stack trace and the exact failing command.
5. Name the acting agent and tier in every log line.

## Repair guardrails
- Refuses any target with uncommitted changes.
- Only `.py` and `.sh` files inside Seravo-0's own workspace are eligible.
- Cannot repair itself.
- Runs under a time limit and may not touch the secrets folder.
- Prompts are versioned like code, so a bad change is undone with a revert.
