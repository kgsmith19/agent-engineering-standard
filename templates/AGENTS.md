# AGENTS.md

This repository follows `kgsmith19/agent-engineering-standard`, pinned in `.agent/standard.lock`.

## Product truth

Read only the context needed for the assigned work, in this order:

1. `PRD.md` — what/why/outcomes/requirements
2. relevant `specs/` — exact behavior when nontrivial
3. relevant `docs/adr/` — consequential architecture constraints
4. the assigned GitHub Issue — durable work scope

The portfolio GitHub Project is the planning/status surface; the linked Issue is the executable backing record.

Do not invent a consequential product decision when the source truth is missing or contradictory. Record the blocker and stop that slice.

## Lean delivery loop

`Project → Issue → SPEC if needed → thin slice → RED/minimum GREEN → local verification → draft PR → PR Gate → independent AI Review → merge/release`

- Work one thin slice at a time; scope widening becomes another slice/Issue.
- Use the smallest correct implementation. Avoid speculative abstractions and unrelated refactors.
- Write/adjust behavioral proof before implementation when practical; RED must fail for the missing behavior, not setup noise.
- Never weaken tests, evaluators, required checks, security boundaries, or thresholds merely to obtain GREEN.
- Update affected product/engineering truth in the same PR.

## Isolation and parallelism

- Every write-capable task uses its own branch/worktree. Never share a working directory between concurrent writers.
- Controlled agent branches use `agent/<provider>/<issue-or-work>` when the harness allows it.
- Read-only research/review may fan out in parallel.
- Parallel writers require disjoint file scopes and separate worktrees. Default maximum: 3.
- One coordinator integrates results and runs final verification.

## Risk and authority

Use the shared R0–R4 scale. The implementing agent may raise risk, never lower it.

- Control-plane changes are at least R3.
- R4 never auto-merges; the manual step authorizes the destructive/financial/privileged/irreversible consequence.
- Any manual gate must state: failure class prevented, why automation is insufficient, decision owner, and measurable gate-removal condition.

## CI and repair

Keep active implementation in a draft PR. Run fast local checks before pushing coherent changes.

When `PR Gate` fails:

1. classify the failure: implementation, specification/oracle, environment, flaky, or policy
2. fix implementation/environment failures at the root cause
3. retry a genuinely flaky failure once
4. do not silently override specification/policy conflicts
5. stop after 3 failed fix attempts for the same cause and record the blocker

Do not push cosmetic or empty commits just to retrigger CI.

## Independent review and merge

Writing code is not completion.

- A semantic reviewer must be independent of the implementing agent/session; use another provider when practical and mechanically supported.
- Use the shared review automation when available, but never claim review success unless GitHub records the required `AI Review` evidence on the current head SHA.
- A later push invalidates prior exact-head semantic evidence.
- Resolve review threads only after the finding is fixed or explicitly demonstrated to be a false positive.
- Auto-merge is allowed only when the current head has required `PR Gate` + `AI Review`, review threads are resolved, risk is eligible, and no justified authority gate applies.

## Hygiene

- `.worktrees/` and `.superpowers/` are local scratch state and must stay ignored.
- Remove merged/abandoned branches and stale worktree metadata only when no unique or dirty work can be lost.
- If a manual workaround is likely to recur, automate it when small/safe or log one bounded automation/research candidate with evidence and a next experiment.

## Reviewer rules

- Flag requirement/spec mismatches even when tests pass.
- Flag tests that can pass without proving the claimed behavior.
- Flag weakened authority/security/evaluator boundaries and unnecessary complexity.
- For UI changes, require appropriate user-visible evidence such as a focused Playwright journey unless stronger evidence is justified.
