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

Avoid:

- speculative abstractions
- unrelated refactors
- unnecessary dependencies
- future features
- scope expansion without evidence

## 3. Do not game the system

Never obtain GREEN by:

- weakening/deleting tests
- skipping required checks
- lowering thresholds
- hiding errors
- changing the evaluator or policy judging the current run

If the specification/evaluator appears wrong, report the conflict instead of bypassing it.

## 4. Verify completion

Writing code is not completion.

Claim completion only when applicable independent evidence passes.

State exactly what remains unverified when full verification is impossible.

## 5. Retry intelligently

Before retrying, classify the failure:

- specification/oracle
- implementation
- environment/dependency
- flaky test
- missing context
- permissions/policy
- tool/infrastructure

Do not repeat the same failing strategy indefinitely.

Escalate consequential ambiguity rather than forcing a result.
