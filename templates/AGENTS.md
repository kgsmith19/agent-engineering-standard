# AGENTS.md

This repository follows `kgsmith19/agent-engineering-standard`, pinned in `.agent/standard.lock`.

## Product truth

Read only the context needed for the assigned work:

1. `PRD.md`
2. relevant `specs/`
3. relevant `docs/adr/`
4. assigned GitHub Issue

Do not invent consequential product decisions. Record a real blocker and stop that slice when source truth is missing or contradictory.

## Lean delivery loop

`Issue → SPEC only if needed → thin slice → RED/minimum GREEN → local verification → draft PR → Ready → PR Gate → exact-head AI Review → automatic squash merge → release`

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

## Draft and Ready

Keep active implementation draft so micro-pushes do not spend semantic-review budget or arm merge.

When coherent and locally verified, add `status:ready`. Automation marks the PR Ready and removes the label. Converting back to draft pauses the lane again.

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

## Machine AI Review

After `PR Gate` passes, automation requests one fresh machine review task/session for the exact head SHA.

- Codex is primary for ordinary PRs.
- Copilot is the bounded fallback and the required reviewer for a PR authored by the Codex GitHub App.
- Branch names and PR prose do not prove implementation identity.
- One review covers correctness/security, requirement fit, business ROI, systems optimization, and strict leanness.
- Any P0–P2 finding fails `AI Review` and triggers bounded repair on the same PR.
- A fix creates a new SHA; both gates repeat.
- Never reviewer-shop around a material finding.

## Merge

Routine auto-merge requires:

- non-draft, non-Copilot-owned PR
- eligible R0–R3 risk
- no `status:blocked`
- no self-modifying control-plane path
- no requested reviewer `kgsmith19`
- current-head `PR Gate` success
- current-head `AI Review` success
- resolved review threads
- live squash-only zero-human ruleset

GitHub performs the squash merge and deletes the branch.

## Hygiene

- `.worktrees/` and `.superpowers/` remain ignored.
- Never destroy dirty work or branches with unique commits.
- Automate recurring manual toil when safe; otherwise record one bounded research candidate with evidence and a next experiment.
