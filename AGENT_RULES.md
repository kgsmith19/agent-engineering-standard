# Agent Rules

## Goal

Produce correct, useful software with minimum human attention, rework, cost, and unnecessary code.

## 1. Work small

Work one thin slice at a time.

Before coding:

1. read only relevant product/work context
2. define what proves the slice correct
3. keep the change inside that scope

Do not implement a whole large feature when a smaller valuable slice exists.

## 2. Prefer minimum correct implementation

Priority:

**Correct → Simple → Deterministic → Observable → Maintainable → Clever**

Avoid speculative abstractions, unrelated refactors, unnecessary dependencies, future features, and scope expansion without evidence.

## 3. Do not game the system

Never obtain GREEN by weakening/deleting tests, skipping required checks, lowering thresholds, hiding errors, or changing the evaluator/policy judging the current run.

If the specification/evaluator appears wrong, report the conflict instead of bypassing it.

## 4. Verify completion

Writing code is not completion. Claim completion only when applicable independent evidence passes. State exactly what remains unverified when full verification is impossible.

## 5. Retry intelligently

Before retrying, classify the failure as specification/oracle, implementation, environment/dependency, flaky test, missing context, permissions/policy, or tool/infrastructure.

Do not repeat the same failing strategy indefinitely. Escalate consequential ambiguity rather than forcing a result.

## 6. Automated PR state machine

Finish and verify one coherent slice locally, then open its PR Ready. Draft PRs are forbidden because GitHub cannot merge them and a conversion step introduces a race before auto-merge.

- REST, SDK, GraphQL, and connector creation calls set `draft: false` and verify the returned PR is not draft.
- `gh pr create` callers omit `--draft` and verify `gh pr view --json isDraft --jq .isDraft` returns `false`.
- Never use `gh pr ready` or automated draft conversion in the steady-state lane.
- If a draft is observed, automation applies `status:blocked`, emits the exact contract error, and stops before auto-merge.

Every unattended merge requires one GitHub check on the **latest head SHA**:

1. `PR Gate` — deterministic repo-specific build/test/security evidence

`PR Gate` is the sole required merge-authority check (ADR 0004 — inline AI code review was removed from the blocking merge path entirely; see below). A later push invalidates prior authorization: the state machine re-runs the deterministic gate against the new head before GitHub auto-merge proceeds.

### Cost and retry bounds

- CI repair: maximum 3 attempts
- conflict repair: maximum 2 attempts
- gate rerun (cancelled/stale on the current head): maximum 1 attempt
- duplicate exact-head requests are suppressed
- repair dispatch (`pr_automation.repair_dispatch_enabled`) is off by default; while off, CI/conflict repair posts a recoverable `<lane>-dispatch-disabled` block naming the owner instead of tagging an agent
- the six-hourly watchdog is the general convergence net for missed webhooks (a PR whose gate-result event never arrived), not a review mechanism

No routine path requests Kyle as a GitHub reviewer. Native `CODEOWNERS` is absent and required human approvals are `0`; the deterministic `PR Gate` status check is the sole merge authority (ADR 0004).

R0–R3 may auto-merge when `PR Gate` passes and no justified authority gate applies. Control-plane changes remain manually integrated while they can modify the evaluator or merge authority judging themselves. R4 never auto-merges.

## 7. Manual gates must earn their existence

Never add or preserve a manual gate merely because work is "important", "sensitive", or traditionally reviewed by a person.

Every manual gate must state all four:

1. **failure class prevented** — concrete bad outcome
2. **why automation is insufficient today** — missing signal/capability, not vague trust
3. **decision owner** — who has authority the machine lacks
4. **gate removal condition** — measurable condition that lets us automate/delete it

If any field is missing, the gate is unjustified and should be removed or replaced with objective automation.

## 8. Turn manual toil into system improvement

When an agent or human performs a manual workaround, ask whether it can recur.

- If automation is small, safe, and in scope: automate it now.
- Otherwise record one concise automation/research candidate with problem, evidence/frequency, human cost, research needed, smallest experiment, expected payoff, and deletion/expiry condition.
- Discard candidates without evidence, plausible ROI, or a next experiment.

Repeated manual work must not become normal merely because an agent can keep doing it.

## 9. Isolated worktrees and parallel subagents

Every write-capable task runs in one isolated worktree tied to its Issue or slice.

- Prefer a harness-native worktree when available; otherwise use `.worktrees/<branch>`.
- Never share a worktree or working directory between concurrent write agents.
- Read-only investigations/reviews may fan out in parallel with isolated context.
- Parallel write agents require provably disjoint file scopes and separate worktrees/branches.
- One coordinator integrates results and runs the final verification.
- Default parallelism is 3; exceed it only with evidence that added concurrency reduces wall-clock time without increasing rework.
- Remove merged/abandoned worktrees and branches. Dirty or unique work is reported, never destroyed automatically.
