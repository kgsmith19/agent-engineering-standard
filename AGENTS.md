# Agent Engineering Standard

Micro-constitution: binding core rules and routing to 4 governance modules for complete normative content, procedures, evidence standards, and rationale. **All policies preserved; depth and details routed.**

## Objective

Deliver small, verified, independently mergeable changes with honest evidence — under absolute owner authority — using **GitHub Issues**, **Milestones**, **pull requests**, and a single fail-closed **PR Gate** as the machinery of record.

## Capability Layer (agent-extensions)

The capability bundle — **agent-extensions** — is the provider-neutral layer this
standard assumes: skills, plugins, MCP wiring, and the continuity capsule. It is
**machine-global and never committed into a repository.**

- **Provision or repair (idempotent, one command):**
  `curl -fsSL https://raw.githubusercontent.com/kgsmith19/agent-extensions/main/bootstrap.sh | bash`
- **Check at session bootstrap:** if `~/.agents/skills` is missing or empty, or
  the continuity adapter is absent, provision before starting work.
- **Extension plane:** a capability is a **CLI first** — it works in every
  harness, including those without MCP. MCP is an optional adapter: bridge with
  `mcporter` (MCP→CLI) or `any-cli-mcp-server` (CLI→MCP).
- **Continuity:** keep the project capsule current
  (`capsule capture --task ... --next ...`); it is injected at session start and
  refreshed before compaction, so a fresh session resumes without re-deriving
  context.
- **Provenance:** skills are vendored at exact commits and the lockfile is the
  provenance ground truth. A live provider marketplace is never the authority
  for cross-provider content.

## High-Value Practices (Aggressive by Default)

Defaults, not suggestions. Deviating requires an owner instruction or a recorded
reason on the Issue.

- **Feature branch from the start.** Never work directly on the default branch:
  claim the Issue and construct `issue/<n>-<slug>` before the first edit.
- **Git worktrees for isolation.** One worktree per active Issue
  (`.worktrees/issue-<n>-<slug>`); one writer per worktree.
- **Subagents for independent work.** One focused writer per worktree;
  read-only scouts and critics run concurrently; never trust a subagent success
  claim without re-running verification at the exact head.
- **TDD through Superpowers.** Brainstorm before creative work; write the
  failing test first (RED), implement to GREEN, then REFACTOR;
  `verification-before-completion` before any success claim.
- **Superpowers skills route by default.** brainstorming, writing-plans,
  executing-plans, systematic-debugging, test-driven-development,
  requesting-code-review, receiving-code-review, using-git-worktrees,
  subagent-driven-development — prefer the process skill over ad-hoc procedure.
- **Baseline before specifics.** This file is the baseline; the repository's own
  AGENTS.md is project-specific and takes precedence where they differ.

## Core Rules

### Owner Authority (Binding)

**The OWNER is `kgsmith19`.** The standard governs agents by default; the owner governs the standard. **Precedence order:** (1) current explicit owner instruction, (2) owner-authorized GitHub Issue and acceptance criteria, (3) AGENTS.md, (4) project.yaml, (5) pinned standard from standard.lock, (6) harness defaults.

The owner **may override, replace, suspend, or delete any part of this standard at any time** without satisfying prior policy. An agent **must not** silently disregard an owner override; report once as **"Not run by owner instruction."** When work runs under owner account, self-approval does not protect control-plane changes — explicit owner administrative merge decision required.

[Full rules and credentials: AGENTS/governance.md#owner-authority](./AGENTS/governance.md#owner-authority)

### Sources of Truth

- **Product/quick start:** README.md
- **Rules:** AGENTS.md
- **Facts/commands:** project.yaml
- **Release scope:** GitHub Milestone
- **Intent/criteria:** GitHub Issue
- **Evidence:** Pull request
- **Standard version:** standard.lock

[Full table and policy: AGENTS/governance.md#sources-of-truth](./AGENTS/governance.md#sources-of-truth)

### Session Bootstrap

At session start: (1) invoke superpowers, (2) read AGENTS.md and project.yaml, (3) initialize dev/reviewer agents, (4) identify active Issue/milestone/branch/PR/head, (5) detect isolation, (6) reconcile local state with Git/GitHub, (7) run baseline verification. Use Superpowers skills. Resume first incomplete task.

[Full procedure: AGENTS/governance.md#session-bootstrap](./AGENTS/governance.md#session-bootstrap)

### Thin Issues and Claiming

One Issue = **one observable outcome:** cohesive behavioral boundary, independently testable and mergeable, reversible or recoverable, with one branch, one worktree, one PR. Thin Issues are the unit of atomic work.

Split an Issue when it contains multiple independently valuable outcomes, crosses unrelated domains, needs multiple writers in same files, could be part-approved, can partly ship independently, exceeds ~5 behavior claims, defeats one evidence strategy, or cannot be reviewed in one focused pass. Prefer vertical behavior slices over horizontal layer-only Issues.

**Claim protocol** — 6 steps: (1) confirm Issue open, `status:ready`, not `status:blocked`, (2) resolve current SHA, (3) construct branch/worktree names, (4) atomically create remote branch via API (fail if exists), (5) add `status:active`, remove `status:ready`, (6) post work-state comment with Issue, milestone, branch, base/head SHA, providers, task, status, blocker.

[Full rules: AGENTS/work.md#thin-issues-and-work-claiming](./AGENTS/work.md#thin-issues-and-work-claiming)

### PR Gate (Binding Enforcement)

**The sole required status check** is the final aggregator job `Agent Engineering Standard PR Gate` (or application-specific name). The gate:
- Runs with `if: always()`, depends on every applicable job
- **Fails unless every required dependency concluded exactly `success`** (rejecting failure, cancelled, skipped, neutral, or missing)
- Verifies tested SHA equals current PR head
- Publishes concise summary
- Is the only required check; `main` protection uses only this gate plus up-to-date requirement

**No bypass except owner administrative override.** Agents create **ready PRs — never drafts, never converting to draft.** Incomplete work remains on branch; failing gate = incomplete or invalid work.

[Full design: AGENTS/boundaries.md#pr-gate-and-merge-behavior](./AGENTS/boundaries.md#pr-gate-and-merge-behavior)

### Independent LLM Review (Status Check)

Independent LLM Review is a **status check, never approving review.** Runs as one job feeding PR Gate; owner bypass always overrides red result. **Provider separation enforced in CI:** reviewer family MUST differ from builder's; gate fails closed when equal. No agent review blocks owner. Findings require evidence and citations.

[Full rules: AGENTS/boundaries.md#independent-llm-review](./AGENTS/boundaries.md#independent-llm-review)

### Prohibited Actions

Agents **must not:**
- Submit reviews, request reviewers, approve changes, or post unsolicited comments
- Bypass PR Gate or push directly to `main`
- Weaken tests, oracles, or assertions to obtain green status
- Use administrative bypass without owner authorization
- Claim completion without fresh verification evidence at exact head
- Store credentials in the repository or claim live settings without reading back
- Create automatic fleet-wide propagation or second work tracker
- Lecture, argue with, reverse, or warn repeatedly about owner decisions

[Full boundary list and adoption: AGENTS/boundaries.md#agent-boundaries](./AGENTS/boundaries.md#agent-boundaries)

## Module Index and Routing

For complete normative rules and procedures:

| Module | Purpose |
|---|---|
| [governance.md](./AGENTS/governance.md) | Owner authority, bootstrap, roles, risk tiers |
| [work.md](./AGENTS/work.md) | Issues, claiming, worktrees, recovery |
| [verification.md](./AGENTS/verification.md) | Intent, tests, flow, evidence, completion |
| [boundaries.md](./AGENTS/boundaries.md) | PR Gate, LLM Review, corrective action |

## Stable Anchor IDs for Tools and Scripts

Use these anchors to reference specific rules and procedures in implementations:

- `governance#owner-authority` — owner, precedence order, override authority, credentials, ID flow
- `governance#session-bootstrap` — 7-step bootstrap procedure, Superpowers integration, resume rules
- `governance#agent-identities` — dev/reviewer GitHub Apps, credential flow, provider separation, CI setup
- `governance#risk-classification` — R0–R3 risk tiers and verification scaling
- `work#thin-issues-and-work-claiming` — scope, splitting rules, label set, 6-step protocol, work-state
- `work#worktrees-and-parallel-work` — isolation rules, baseline, cleanup, safe parallelization
- `work#context-recovery-and-subagent-tracking` — recovery after restart, task states, ledger
- `verification#test-quality` — oracle standards, empty-green prohibition, portfolio guidance
- `verification#verification-flow` — end-to-end pipeline from owner intent through production
- `verification#completion-standard` — completion criterion (fresh evidence at exact head, no unresolved)
- `boundaries#pr-gate-and-merge-behavior` — sole required check, aggregator design, merge automation
- `boundaries#independent-llm-review` — provider separation enforcement, review protocol, findings
- `boundaries#agent-boundaries` — may/must-not action lists and adoption rules

## Completion Standard (Preview)

Work is complete **only with fresh evidence at exact head:**
- Every acceptance criterion satisfied and verified
- Local verification and tests green on exact head
- PR Gate green on exact tested head (not stale)
- Required artifacts uploaded, digested, indexed
- Independent verification recorded (R2/R3 work)
- No silently weakened oracle or test coverage
- Issue closed by merged PR
- Worktree and subagent state reconciled

**Never report completion while any required verification, cleanup, or acceptance criterion remains unresolved. Do not substitute confidence for evidence.**

[Full rule and rationale: AGENTS/verification.md#completion-standard](./AGENTS/verification.md#completion-standard)

---

**Adoption by other repositories:** explicit, Issue-backed, pinned via `standard.lock`, independently verified, owner-controlled — never automatic. Repository-specific instructions take precedence.
