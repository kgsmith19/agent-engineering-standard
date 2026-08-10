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

- pure/local logic → unit + property/invariant (T-U-NNN / T-P-NNN)
- bug → reproduction + regression (T-R-NNN)
- API/schema → contract + integration (T-C-NNN / T-I-NNN)
- user journey → acceptance/E2E (T-A-NNN / T-E-NNN)
- hostile/untrusted input → security/fuzz (T-S-NNN)
- data migration → data invariants (T-P-NNN) + recovery proof
- risky release → runtime smoke/black-box proof

Do not run every test category for every change.

Use `T-*-NNN` identifiers (unit, property/invariant, integration, contract, end-to-end, security, regression, acceptance) as the durable reference for a piece of test evidence when a slice or spec cites it. `T-M-NNN` records mutation-test evidence for a specific test — proof that the test actually kills an injected mutant — independent of which category the mutated test belongs to.

## 4. Independent evaluation

Critical acceptance/security/policy checks must be protected from the agent implementing the current change.

The implementer may execute them, but may not modify or bypass them.

For semantic review, use a fresh reviewer with no implementation-session context. The default lightweight path is an ephemeral, read-only Codex review that inspects the PR diff plus the relevant PRD, active SPEC, tests, and nearby code.

Reviewer priorities:

1. requirement/spec mismatch
2. false-green or missing test evidence
3. correctness/regression risk
4. security/authority boundary violations
5. unnecessary complexity or scope

Do not spend reviewer budget on formatting or style that deterministic tooling can enforce.

Fresh semantic review (`AI Review`) is advisory at every risk tier: the deterministic `PR Gate` is the sole required merge-authority check (ADR 0002). R3/R4 and engineering-control-plane changes still receive that review when the lane is active, and findings still surface as blocking (P0/P1) versus advisory (P2) evidence — but merge for those changes is withheld by an explicit manual authority gate naming the decision owner, not by the review outcome.

## 5. UI end-to-end evidence

For repositories with a real UI, Playwright should exercise actual user interactions in a browser: navigation, clicks, form entry, and visible outcomes tied to important PRD requirements or acceptance criteria.

Keep E2E broad in **journey coverage**, not browser-matrix size:

- ready PR: critical changed/affected journeys on one primary browser; retain screenshot + trace on failure
- merge queue: same critical gate against the combined queue head
- main/release/nightly: broader critical-user-journey sweep; retain HTML report and selected successful end-state screenshots as durable proof
- extra browsers/devices only when the product requirement or a real defect justifies them

Prefer deterministic fixtures/test accounts and controlled APIs over flaky uncontrolled dependencies. Do not mock away the boundary the E2E test is specifically intended to prove.

Every important user-facing requirement should eventually map to at least one acceptance/E2E journey or an explicitly documented reason why a lower-level oracle is stronger.

## 6. Architecture quality

Prefer explicit, mechanically enforceable boundaries over prose.

Add architecture checks when they prevent recurring problems such as:

- forbidden dependencies
- layer violations
- circular dependencies
- cross-domain coupling

Create an ADR only when a decision is consequential, long-lived, or difficult to reverse.

Coverage is diagnostic, not proof of correctness.
