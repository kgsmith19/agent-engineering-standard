# Role contract corpus (Std#300)

Frozen conformance fixtures for the runtime-neutral role and authority
contract. Each `expect` must equal `tools/role_contract.decide(...)`;
the suite is `tests/test_role_contract.py`.

The corpus pins:

- Grant validity: duty in `role_authority.ROLES`, 1-hour window,
  expiry boundaries, unknown or mistyped fields.
- Provenance: observed provider must match the declared family.
- Forbidden self-review: builder self-validation and same-actor review
  refused; R2/R3 same-family review refused, other family allowed.
- Scope: path matrix plus grant scope; traversal refused.
- GitHub writes: `post` and `mutate_github` need `github_identity`.
- Owner override: waives only expiry and stale head, and only when
  explicit.

Std#301 adds:

- Decide cases for same-agent verification, unscoped delegation,
  stale-head receipts, parallel writes (prefix overlap), and privilege
  escalation (`delegated: true`, owner or grantor holding the duty).
- A top-level `flows` list. Each flow is an ordered list of `record(...)`
  steps; each step's `expect` gives `decision` and `rules`. Covered:
  a four-role planner, builder, reviewer and verifier flow (distinct
  `provenance.source` per step, reviewer and verifier families differ
  from the builder), a builder and reviewer flow, an R3 security
  specialist (`specialty` on the receipt only), and a refusal for
  `missing-evidence`.

Ids are `role-contract.allow.<slug>` or `role-contract.refuse.<slug>`
and are stable; never repurpose a case. Flow ids are `flow.<slug>`.
