# Bootstrap reminders (operational)

Committed, copy-mode reminders that `standardctl update` refreshes. This file
carries **no policy** — normative rules live in `AGENTS.md` and the routed
modules. It only says how to load and use them.

1. **Know your environment first.** Session start writes a names-only inventory
   to `~/.agents/inventory.md`: credentials in the environment and in every
   configured secret store, what each is for, retired entries, and the CLIs on
   PATH. Read it before the first task. If it is missing or stale, run
   `ae inventory --write` (or `python3 -m agent_extensions.inventory --write`).
   - Never print, log, commit or copy a secret value. Names, ids, versions and
     short fingerprints only.
   - Use a secret through `ae secret-run --env VAR=/path:KEY -- <command>`. The
     value exists only in that command's environment and its output is redacted.
   - Never report a credential or tool as unavailable without checking the
     inventory first. A credential missing from the catalog is a gap to fix there,
     not something to guess about.
   - Owner-only steps (creating PATs, OAuth consent, billing) stay with the owner.
2. **Read the rules first.** `AGENTS.md` (constitution + module index) and
   `project.yaml` (facts and commands). Owner instruction outranks everything.
3. **Provision the capability layer if absent.** Skills, plugins, and the
   continuity capsule come from the provider-neutral bundle. If `~/.agents/skills`
   is missing or empty:
   `curl -fsSL https://raw.githubusercontent.com/kgsmith19/agent-extensions/main/bootstrap.sh | bash`
   The capability layer is machine-global — never commit it into this repository.
4. **Extension process.** A capability is a **CLI first**, so it works in every
   harness including those without MCP. MCP is an optional adapter: `mcporter`
   (MCP→CLI) or `any-cli-mcp-server` (CLI→MCP).
5. **Working defaults.** Feature branch from the start (`issue/<n>-<slug>`), one
   git worktree per active Issue, one writer per worktree, subagents for
   independent work, and the Superpowers TDD flow (RED → GREEN → REFACTOR) with
   `verification-before-completion` before any success claim.
6. **Fresh evidence.** Never claim completion without a fresh check at the exact
   head.
7. **Committed vs uncommitted.** Own the repository? Adopt the standard committed
   (`standardctl init`). Cannot commit it here (for example, a team repo)? Keep
   the standard's process on the machine-global capability layer and put
   repo-specific rules in a gitignored `AGENTS.local.md` — the capability layer
   injects it at session start, additively, so the committed AGENTS.md still
   governs.

Edit the standard, not this copy: it is regenerated from the pinned commit in
`standard.lock`.
