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

## 6. PR and merge behavior

Keep a PR draft while implementation is still changing. Run the repo's local/fast verification during slices, then mark the coherent PR ready so the independent `PR Gate` runs.

- R0–R2: once the PR is ready and policy permits, enable auto-merge; required checks/review threads still decide when it actually merges.
- R3/R4 or control-plane changes: request a fresh independent semantic review after the final substantive push. Do not enable auto-merge until that review has no unresolved material finding.
- An agent that implemented a control-plane change must never treat its own review as independent.
