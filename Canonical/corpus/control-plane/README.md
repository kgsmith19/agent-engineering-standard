# Control plane corpus (Stage 60a, #151)

Frozen, hand-adjudicated control-plane observations. Every
entry's `expected_rule` must equal
`tools/control_plane.evaluate(entry.observation).rule` and
`expected_verdict` the verdict.
`standardctl control-plane` validates the set on every run.

## What the contract proves

Stage 60a (Standard half) binds every claim, lane, review,
standards result, and merge action to the exact current head
under a versioned control-plane contract — simple and monorepo:

- `missing/duplicate/skipped/neutral/cancelled/stale` lanes —
  REFUSE and rerun.
- `path-filter` / `unsafe-target` / `floating-pin` /
  `excess-permission` — control hygiene REFUSEs.
- `head-moved` / `missing-evidence` / `policy-fail` — exactness
  REFUSEs.
- `merge-conflict` / `draft-hold` / `rearm` — HOLD states.
- `clean-arm` — green exact-head expected-OID observations ARM.

## One final Gate

Worker lanes read-only/least-privilege/full-SHA; privileged
jobs run no PR code; auto-merge arms on expected OIDs only.
