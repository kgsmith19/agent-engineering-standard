# Lifecycle

## 1. Capture

Record ideas with near-zero friction.

Accept rough text, voice-derived text, errors, links, or observations.

Do not create a project or backlog item for every idea.

## 2. Shape / Research

Use AI to:

- clarify the problem
- find related code/work/solutions
- identify important assumptions
- research only uncertainties likely to change the decision
- recommend `KILL`, `DEFER`, `PROTOTYPE`, or `BUILD`

Preserve conclusions, not research clutter.

## 3. Outcome / Bet

Before building, state:

- problem
- expected useful outcome
- success signal
- major assumption
- decision

Do not design architecture unless it is needed to make the decision.

## 4. Product Truth

For approved work, keep a compact PRD containing:

- problem/users
- outcomes
- important functional requirements
- important quality constraints
- out of scope

Product truth describes what should exist, not implementation details.

## 5. Work

Use:

- GitHub Issue = durable work item
- SPEC = only when behavior/decisions are nontrivial
- Slice = smallest independently understandable and verifiable increment
- ADR = only for consequential or hard-to-reverse architecture decisions

A PR may contain one or a few tightly related slices.

## 6. Build

For each slice:

1. define evidence
2. determine risk/authority
3. work in isolation where practical
4. establish RED when meaningful
5. implement minimum GREEN
6. run applicable verification
7. open PR
8. let protected CI decide merge eligibility

## 7. Release / Learn

After merge:

- build/deploy appropriately for risk
- prove important behavior in the running system
- preserve rollback/recovery when warranted
- record outcome, quality, cost, retries, and interventions
- feed repeated failures/opportunities back into the next idea or slice
