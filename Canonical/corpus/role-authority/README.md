# Role authority corpus (Stage 30, #121)

Frozen, hand-adjudicated path-authority canaries: every
entry's `expected` outcome must equal the decision from
`tools/role_authority.evaluate_canary(entry)` — allowed or
refused-with-`expected_rule`. `standardctl role-authority`
validates the set on every run.

## Role matrix

- spec_author: `specs/`, `plans/` — never `src/`, `tools/`.
- spec_critic: `evidence/critic-findings/` only.
- mold_designer: `verification/pending/`, `evidence/`.
- mold_qualifier: `evidence/qualification/` only.
- builder: `src/`, `plans/`, `evidence/builder-notes/`.
- verifier: `evidence/verification/` only, never `src/`.
- reviewer: `evidence/review/` only (verdicts).
- remediator: `src/`, `evidence/remediation/` only.

Frozen `Canonical/corpus/` is immutable to every role.

## Receipt freshness

A receipt is fresh only at its issued head; a stale head
blocks the write. Same-agent builder+verifier reuse requires
disclosure, never silent independence. Children inherit only
their granted role via the parent agent, never more.

## Provider separation

R2/R3 blocking review needs reviewer family != builder
family; R0/R1 stays advisory. Owner override is honored only
when explicit: owner `kgsmith19` plus non-empty decision and
scope. Mold qualification logic is left to Stage 31.
