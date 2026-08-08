# Quality Rules

## Goal

Use the cheapest evidence that gives sufficient confidence for the change.

## 1. Evidence before code

For meaningful behavior:

1. define acceptance criteria
2. define important invariants/properties
3. choose the strongest appropriate oracle
4. establish RED when a meaningful executable failure is possible
5. implement only after the expected behavior is clear

RED must fail because behavior is missing/wrong, not because infrastructure is broken.

## 2. Minimum GREEN

Implement the smallest solution satisfying the evidence.

Refactor only after required evidence is green.

## 3. Match verification to the change

Typical evidence:

- pure/local logic → unit + property/invariant
- bug → reproduction + regression
- API/schema → contract + integration
- user journey → acceptance/E2E
- hostile/untrusted input → security/fuzz
- data migration → data invariants + recovery proof
- risky release → runtime smoke/black-box proof

Do not run every test category for every change.

## 4. Independent evaluation

Critical acceptance/security/policy checks must be protected from the agent implementing the current change.

The implementer may execute them, but may not modify or bypass them.

## 5. Architecture quality

Prefer explicit, mechanically enforceable boundaries over prose.

Add architecture checks when they prevent recurring problems such as:

- forbidden dependencies
- layer violations
- circular dependencies
- cross-domain coupling

Create an ADR only when a decision is consequential, long-lived, or difficult to reverse.

Coverage is diagnostic, not proof of correctness.
