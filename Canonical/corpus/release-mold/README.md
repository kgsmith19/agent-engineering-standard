# Release mold corpus (Stage 61a, #152)

Frozen, hand-adjudicated release packages. Every entry's
`expected_rule` must equal `tools/release_mold.evaluate(entry.package).rule`
and `expected_verdict` the verdict.
`standardctl release-mold` validates the set on every run.

## What the Mold proves

Stage 61a (Standard half) proves integrated release readiness
independently of slice-level green — seven claim IDs, canary
discipline, rollback/restore proof:

- `open-issues` / `stale-artifact` / `broken-integration` —
  REFUSE incomplete work.
- `failed-rollback` / `unusable-backup` — REFUSE unrecoverable
  releases.
- `missing-attestation` / `invariant-breach` /
  `missing-telemetry` — REFUSE unproven releases.
- `partial-green` / `expired-evidence` — REFUSE stale proof.
- `restore-rpo` — proven restores PROMOTE.
- `mold-unqualified` / `canary-missing` — HOLD until proven.
- `clean-promote` — complete fresh packages PROMOTE (covered
  by restore-rpo path entries; rule retained for direct
  promotion).

## No percentage releases

Milestone percentages never authorize promotion; the runtime
proofbed follows as Stage 61b.
