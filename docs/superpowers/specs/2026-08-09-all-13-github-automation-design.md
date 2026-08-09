# All-13 Autonomous GitHub Portfolio Design

Status: approved by Kyle on 2026-08-09  
Tracks: #17, #18, #23, #41, #43

## Outcome

All 13 non-archived repositories use GitHub Issues as the durable work queue and share a lean, exact-version automation contract:

`Issue or trusted queue event -> agent implementation -> PR Gate -> independent AI Review -> bounded repair -> fresh-head gates -> native squash auto-merge`

Routine R0-R3 work completes without requesting Kyle as a reviewer. R4, self-modifying control-plane changes, external forks, missing authority, and exhausted recovery budgets fail closed with an exact explanation.

The five already archived repositories remain unchanged.

## Scope

The complete managed portfolio is:

1. `agent-engineering-standard`
2. `agentic-command-center`
3. `agentic-command-center-ui`
4. `prompt-organizer`
5. `toolbelt`
6. `lifeos`
7. `lifeos-ui`
8. `network-checker`
9. `2048Game`
10. `ShaesChicDesignsWeb`
11. `PitchRandomizer`
12. `AutoHit`
13. `AccountPortal`

No active repository is parked or archived by this work.

## Chosen approach

Extend the existing central PowerShell and GitHub Actions control plane. Product repositories keep only stack-specific `PR Gate` commands and exact-SHA callers.

Rejected alternatives:

- A hosted webhook service adds deployment, persistence, and operational cost before the portfolio needs it.
- GitHub Agentic Workflows remain preview-heavy and are not merge authority.
- GitHub Projects adds a second queue without a reliable repository Actions event. Issues remain the sole source of truth.

A narrowly scoped GitHub App installation token is the write identity for agent fix pushes. `GITHUB_TOKEN` remains suitable for checks, labels, and comments, but not for pushes that must trigger fresh CI.

## Coordination and branch ownership

Claude currently owns the implementation lane in PR #44, branch `agent/chatgpt/43-state-machine-exhaustiveness`. Codex must not push to that branch or edit its commits.

PR #42, branch `codex/issue-41-ai-review-canary`, remains the dispatch-disabled RED contract. It is not merged or made Ready until its implementation is complete and its exact head is green.

Before every implementation batch, the worker must re-fetch:

- current `main` SHA;
- open PR heads and changed files;
- new comments and reviews on #42 and #44;
- active branches touching the intended files.

If another active branch touches the same behavior, Codex pauses that file set and works on a non-overlapping phase. No force-push, cross-agent commit rewriting, or direct edits to another agent's branch are allowed.

The convergence order is fixed:

1. Complete the minimal #42 dispatch kill switch and remove Projects.
2. Rebase the completed #44 state-machine changes onto that result.
3. Add Issue/inbox execution.
4. Prove E2E review and repair.
5. Roll the proven standard to all 13 repositories.

## Control-plane safety baseline

Until the E2E review canary passes:

- `independent_review.dispatch_mode` is `disabled_pending_e2e`;
- no workflow posts a reviewer request or repair request;
- `AI Review` reports `neutral`, which is accepted only for the constrained canary lane;
- unattended auto-merge is capped at R2;
- Projects policy, scripts, switches, and guidance are removed;
- PR #42 and all control-plane changes remain manual integration gates.

PR #44 must make current-head decisions exhaustive, cover full-PR reviewer provenance, fail closed for forks, invalidate stale evidence after material edits, and bound cancelled/stale reruns. The three known post-merge P2 defects are included: paginate beyond 100, inspect all open PRs, and make timeout behavior match the documented value.

## Issue and inbox intake

GitHub Issues are the only durable queue. The intake workflow reacts to:

- issue opened, reopened, assigned, labeled, or edited;
- issue comments that mention a supported agent or Kyle;
- Kyle being requested as a PR reviewer;
- formal or inline PR review findings;
- a six-hour reconciliation schedule.

Execution requires either:

- an event from the repository owner or a collaborator with write permission; or
- the owner-applied `status:ready` label.

Untrusted public mentions never launch a write-capable agent.

When Kyle is requested as reviewer on routine R0-R3 work, automation removes the request, records why, and routes an independent AI review. When Kyle is tagged or assigned an eligible Issue, the router classifies it and dispatches the implementation agent. It tags Kyle again only for R4 authority, a control-plane integration decision, missing requirements that change the outcome, or exhausted repair budgets.

Each work item is deduplicated by `repository + item number + head SHA + stage`. State is represented by authenticated GitHub evidence and bounded labels, not a second database.

## Agent collaboration contract

The implementer and reviewer must be different providers across every commit in the current PR.

Default routing:

- Codex-authored PR -> Copilot review.
- Copilot-authored PR -> Codex review.
- Human or Claude-authored PR -> Codex review, with Copilot fallback only if independent.
- Both Codex and Copilot contributed -> no connected independent reviewer; fail closed.

P0 and P1 findings fail the required `AI Review` check. P2-only findings create or update one deduplicated advisory Issue and do not block.

A repair returns to the original implementer provider. The reviewer does not implement its own finding. The repaired commit must produce a new head SHA, trigger a fresh `PR Gate`, and receive a new independent review. One review-repair head is allowed. A second blocking head stops.

Provider invocation is enabled only after a real GitHub canary proves that the invocation creates authenticated exact-head evidence. If workflow-authored native `@codex` dispatch fails that canary, the implementation uses a full-SHA-pinned `openai/codex-action` with a scoped secret. No unproven mention is treated as authoritative.

## Repository contract

Every managed repository must have:

- a meaningful stack-specific check named exactly `PR Gate`;
- thin `AI Review` and `PR Automation` callers pinned to one full standard SHA;
- a matching `.agent/standard.lock`;
- Issues enabled and Projects automation absent;
- squash merge only;
- auto-merge, update branch, and delete-head-branch enabled;
- one canonical default-branch ruleset requiring `PR Gate`, `AI Review`, and resolved conversations;
- zero human approvals for R0-R3;
- no requested Kyle reviewer and no native CODEOWNERS approval dependency;
- default workflow token read-only and least-privileged job permissions;
- no bypass actor;
- force-push and default-branch deletion blocked;
- an exact default branch, including legacy `master` repositories;
- no `bootstrap-only` gate at acceptance.

The rollout script must derive each repository's live default branch instead of assuming `main`.

## State and failure behavior

Events are hints. The current GitHub state is authoritative.

The router is idempotent and serialized per repository/item. Every transition has a terminal or bounded recovery result:

- deterministic failure -> up to three CI repairs;
- merge conflict -> up to two conflict repairs;
- blocking AI finding -> one implementer repair;
- cancelled or stale gate -> one same-head rerun;
- action required, skipped, neutral outside the disabled canary, unknown conclusion, fork, missing token, or unsupported provider -> fail closed;
- superseded head -> ignore old evidence and evaluate the new head;
- R4 or control-plane mutation -> collect evidence, then require explicit owner authority.

An agent push uses the scoped GitHub App token so the new SHA starts fresh workflows. Re-running an old workflow is not evidence for a changed head.

## SDD and verification

Each behavior change follows RED -> GREEN -> REFACTOR:

1. Add one focused failing policy, workflow-structure, or integration test.
2. Run it and confirm the expected failure.
3. Add the smallest implementation.
4. Run the focused test and the full standard gate.
5. Commit the independently reviewable slice.

Required automated evidence:

- table-driven PowerShell policy tests;
- workflow event and permission structure tests;
- exact-SHA caller and lock tests;
- default-branch `main` and `master` rollout tests;
- pagination, deduplication, attempt-budget, and actor-trust tests;
- local doctor;
- remote doctor for all 13 repositories.

Required live canaries, in order:

1. Dispatch-disabled R0 PR reaches `PR Gate`, neutral `AI Review`, and native auto-merge.
2. Trusted Issue dispatch creates a same-repository PR.
3. Independent review returns clean evidence for the exact head.
4. Controlled P1 finding routes to the implementer, creates a new SHA, reruns CI, receives a clean re-review, and auto-merges.
5. Kyle review request is removed and replaced by the independent agent route.
6. Six-hour reconciliation repairs one deliberately stranded eligible item.

Review dispatch stays disabled portfolio-wide until canaries 1 through 5 pass.

## Rollout phases

### Phase 1: Control-plane convergence

Complete #42, converge #44 without overwriting Claude's work, remove Projects, add the scoped push identity, and make the standard gate green. No product callers are upgraded yet.

### Phase 2: Issue and inbox execution

Implement trusted Issue intake, Kyle-tag/review-request routing, deduplication, provider-aware repair, and reconciliation. Prove canaries 1 through 6 in one low-risk product repository.

### Phase 3: Current managed products

Upgrade and remotely verify:

- `agentic-command-center`
- `agentic-command-center-ui`
- `prompt-organizer`
- `toolbelt`
- `lifeos`
- `lifeos-ui`
- `network-checker`

### Phase 4: Remaining active repositories

Bootstrap meaningful stack-specific gates and roll out the same pinned contract to:

- `2048Game`
- `ShaesChicDesignsWeb`
- `PitchRandomizer`
- `AutoHit`
- `AccountPortal`

### Phase 5: Acceptance and cleanup

Run remote doctor across all 13, record exact-head canary links, close superseded Projects work, close completed trackers, and enable review dispatch only at the proven standard SHA.

## Acceptance criteria

The work is complete only when:

- policy lists exactly all 13 non-archived repositories;
- all 13 pass remote doctor without warnings;
- all 13 expose the exact required checks and squash-only live settings;
- every caller is pinned to the same proven standard SHA;
- Projects automation and stale Projects trackers are removed or closed;
- no routine PR requests Kyle as reviewer;
- Issue, tag, requested-review, review-repair, fresh-CI, reconciliation, and native auto-merge canaries are linked from #17;
- dispatch is enabled only after the canary evidence exists;
- no open rollout branch contains conflict debris or unreviewed overlap from another agent.

## Out of scope

- Re-enabling GitHub Projects.
- Merge queue while repositories remain user-owned.
- Automatic writes to external fork branches.
- Automatic R4 approval.
- Archiving any of the 13 repositories.
- A hosted orchestration service.
