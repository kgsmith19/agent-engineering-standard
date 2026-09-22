# Bootstrap reminders (operational)

Committed, copy-mode reminders that `standardctl update` refreshes. This file
carries **no policy** — normative rules live in `AGENTS.md` and the routed
modules. It only says how to load and use them.

1. **Read the rules first.** `AGENTS.md` (constitution + module index) and
   `project.yaml` (facts and commands). Owner instruction outranks everything.
2. **Provision the capability layer if absent.** Skills, plugins, and the
   continuity capsule come from the provider-neutral bundle. If `~/.agents/skills`
   is missing or empty:
   `curl -fsSL https://raw.githubusercontent.com/kgsmith19/agent-extensions/main/bootstrap.sh | bash`
   The capability layer is machine-global — never commit it into this repository.
3. **Extension process.** A capability is a **CLI first**, so it works in every
   harness including those without MCP. MCP is an optional adapter: `mcporter`
   (MCP→CLI) or `any-cli-mcp-server` (CLI→MCP).
4. **Working defaults.** Feature branch from the start (`issue/<n>-<slug>`), one
   git worktree per active Issue, one writer per worktree, subagents for
   independent work, and the Superpowers TDD flow (RED → GREEN → REFACTOR) with
   `verification-before-completion` before any success claim.
5. **Fresh evidence.** Never claim completion without a fresh check at the exact
   head.
6. **Committed vs uncommitted.** Own the repository? Adopt the standard committed
   (`standardctl init`). Cannot commit it here (for example, a team repo)? Keep
   the standard's process on the machine-global capability layer and put
   repo-specific rules in a gitignored `AGENTS.local.md` — the capability layer
   injects it at session start, additively, so the committed AGENTS.md still
   governs.

Edit the standard, not this copy: it is regenerated from the pinned commit in
`standard.lock`.
