# AGENTS.md

This repository follows `kgsmith19/agent-engineering-standard`, pinned in `.agent/standard.lock`.

## Product truth

Read only the context needed for the assigned work:

1. `PRD.md`
2. relevant `docs/adr/`
3. assigned GitHub Issue

Do not invent consequential product decisions. Record a real blocker and stop that slice when source truth is missing or contradictory.

## Lean delivery loop

`Issue → SPEC only if needed (local, gitignored, never committed) → thin slice → RED/minimum GREEN → local verification → Ready PR → PR Gate → automatic squash merge → release`

- Work one thin slice at a time; scope widening becomes another slice or Issue.
- Prefer the smallest correct implementation. Avoid speculative abstractions, dependencies, and unrelated refactors.
- Write or adjust behavioral proof before implementation when practical.
- RED must fail for missing behavior, not setup noise.
- Never weaken tests, evaluators, required checks, security boundaries, or thresholds to obtain GREEN.
- Update affected product/engineering truth in the same PR.

## Isolation and parallelism

- Every writer uses its own branch/worktree; concurrent writers never share a directory.
- Read-only research/review may fan out.
- Parallel writers require disjoint file scopes and separate worktrees. Default maximum: 3.
- One coordinator integrates and runs final verification.

## Risk and authority

Use R0–R4. The implementing agent may raise risk, never lower it.

- Control-plane changes are at least R3.
- R4 never auto-merges.
- Any manual authority gate must state the failure prevented, why automation is insufficient, decision owner, and measurable removal condition.
- Kyle may be tagged for authority, but must never be assigned as a routine GitHub reviewer.

## PR creation contract

Complete and verify the coherent slice locally before opening its PR. Every PR is Ready at creation.

- REST, SDK, GraphQL, and connector calls set `draft: false` and verify the returned state.
- `gh pr create` omits `--draft`, then `gh pr view --json isDraft --jq .isDraft` must return `false`.
- Never convert a Ready PR to draft and never use `gh pr ready` as a pipeline transition.
- A draft is a policy failure: automation blocks it and never attempts auto-merge.

Copilot cloud agent may repair an existing non-Copilot PR. Do not let Copilot cloud agent own/create a PR intended for unattended merge because GitHub requires those PRs to be human-reviewed and merged.

## PR Gate and repair

`PR Gate` is the cheapest sufficient repo-specific objective evidence.

On failure:

1. classify root cause
2. read complete logs
3. fix the cause, not the symptom
4. never weaken the judge
5. retry through the normal PR flow
6. stop at the bounded repair budget and apply `status:blocked`

Do not push empty commits merely to retrigger CI.

## Optional manual review

`scripts/codex-review.ps1` (in `agent-engineering-standard`) is available for a fresh, local, manual second opinion — no implementation-session context, read-only. It is never a CI check and never gates merge.

## Merge

Routine auto-merge requires:

- Ready-at-creation, non-Copilot-owned PR
- eligible R0–R3 risk
- no `status:blocked`
- no self-modifying control-plane path
- no requested reviewer `kgsmith19`
- current-head `PR Gate` success
- live squash-only zero-human ruleset

GitHub performs the squash merge and deletes the branch.

## Hygiene

- `.worktrees/`, `.superpowers/`, and `.specs/` remain ignored.
- Never destroy dirty work or branches with unique commits.
- Automate recurring manual toil when safe; otherwise record one bounded research candidate with evidence and a next experiment.
