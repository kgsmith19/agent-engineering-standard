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

Ids are `role-contract.allow.<slug>` or `role-contract.refuse.<slug>`
and are stable; never repurpose a case.
