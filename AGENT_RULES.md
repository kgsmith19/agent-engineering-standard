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

Open a coherent PR non-draft with its `risk:R*` label already applied, so the lane engages with zero promotion latency. Use a draft only while implementation is genuinely still changing — drafts cannot auto-merge, and `status:ready` promotes one to Ready automatically when it becomes coherent.

Every unattended merge requires one GitHub check on the **latest head SHA**:

1. `PR Gate` — deterministic repo-specific build/test/security evidence

Machine review is advisory-only and off by default (ADR 0002); when enabled via policy it never replaces the deterministic gate. A later push invalidates prior authorization: the state machine re-runs the deterministic gate against the new head before GitHub auto-merge proceeds.

### Machine reviewer selection

- The latest head commit's authenticated machine actor determines reviewer independence.
- Copilot-implemented head → Codex review.
- Codex-implemented head → Copilot review.
- Human/unknown head → Codex primary with one Copilot fallback.
- Branch names and editable PR prose are descriptive only; they are never trusted as implementation identity.
- Claude may be added later only after a mechanical GitHub review adapter is implemented and verified.

The machine review batches these lenses into one response:

1. software correctness/security
2. requirement/spec fit
3. business/product outcome and ROI
4. systems/operational optimization
5. strict leanness, complexity, dead code, and manual toil

A clean formal review, structured exact-head Copilot PASS, or exact-head Codex thumbs-up can satisfy `AI Review`. Material P0–P2 findings in the review summary **or inline review comments** make `AI Review` fail and trigger one batched repair attempt. A fix creates the second and final reviewed SHA; if that head still has material findings, automation blocks instead of buying an indefinite review loop.

### Cost and retry bounds

- deterministic checks run before model review
- the AI Review runner wakes only when review evidence changes
- no AI review for drafts or every micro-push
- normal budget: initial reviewed head plus one post-fix reviewed head
- CI repair: maximum 7 attempts
- review repair: maximum 1 batched attempt
- conflict repair: maximum 6 attempts
- duplicate exact-head requests are suppressed
- stalled Codex review may use one independent Copilot fallback
- reviewer timeout is enforced by the low-frequency watchdog, not a permanent busy runner

No routine path requests Kyle as a GitHub reviewer. Native `CODEOWNERS` is absent and required human approvals are `0`; the deterministic `PR Gate` status check is the sole merge authority (ADR 0002).

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
