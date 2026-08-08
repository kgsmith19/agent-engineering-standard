# Delivery & GitHub

## Goal

Make GitHub the protected integration/enforcement plane while keeping feedback fast.

## 1. CI

Select required checks from risk and affected components.

Run independent checks in parallel where safe:

- build/types/lint
- unit/property
- integration/contract
- acceptance/E2E
- security/dependency
- protected evaluator

Keep expensive mutation, extended fuzzing, performance, or large matrices outside the fastest path unless they are necessary blockers.

## 2. Protect enforcement

Use branch protections/rulesets so required checks cannot be bypassed by the implementing agent.

Protect or separately authorize changes to:

- required workflows
- evaluator configuration
- security/risk policy
- deployment policy

## 3. PRs

PRs are coherent integration units, not necessarily one PR per microscopic slice.

Generate PR descriptions from machine evidence where possible.

Auto-merge when:

- required evidence passes
- risk policy permits it
- protected controls are unchanged or separately approved
- no blocker remains

## 4. Release

Keep low-risk releases simple:

`merge → deploy → smoke`

For higher-risk releases:

- build once
- identify the immutable artifact/commit
- promote the same artifact
- use staging/canary/feature flags when they meaningfully reduce risk
- verify after deployment
- preserve rollback/recovery

## 5. Shared workflows

Prefer centrally maintained reusable GitHub workflows for universal checks.

Project repos should contain only thin configuration/wrappers needed for their stack and product.
