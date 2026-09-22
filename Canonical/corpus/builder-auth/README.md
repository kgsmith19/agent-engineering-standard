# Builder authorization corpus (Stage 35, #126)

Frozen, hand-adjudicated Builder authorization requests.
Every entry's `expected_rules` must equal the sorted rule set
from `tools/builder_auth.authorize(entry.request)`;
`expected_granted` must equal the grant flag.
`standardctl builder-auth` validates the set on every run.

## What the gate proves

Stage 35 is the exact gate between no-code Arc A and
production mutation. `authorize` denies until phase, role
receipt, exclusive lease, exact head, digests, paths, scope,
context, disposition, owner hold, and frozen-oracle policy
are all valid:

- `phase-not-authorized` — Arc A below IMPLEMENT_AUTHORIZED
  reopens instead of proceeding.
- `role-not-builder` — only the builder role takes the grant.
- `receipt-missing` — no fresh builder receipt at the exact
  head (absent, wrong-role-held, or stale).
- `lease-conflict` — no exclusive current-generation lease
  held by this builder (absent, чужой holder, shared, or
  fenced generation).
- `head-stale` — observation binds a different head.
- `digest-drift` — Mold or run digest moved after
  qualification (altered expected value).
- `protected-path` — a granted file touches protected ground.
- `scope-expansion` — a granted claim lies outside the
  authorized scope.
- `context-overrun` — footprint in recovery or at the
  read-only rotation boundary.
- `disposition-blocked` — disposition is not IMPLEMENT.
- `owner-hold` — the owner hold blocks even a clean grant.
- `frozen-policy` — the freeze no longer binds.

## Pure decision, no implementation

`authorize` decides; it never mutates, never writes, never
implements. The grant is a decision record only. A suspected
Mold defect never proceeds — digest or freeze drift reopens
back to Arc A (Stage 34) for reopen-and-requalify.
