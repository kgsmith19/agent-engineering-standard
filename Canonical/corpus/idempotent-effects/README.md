# Idempotent effects corpus (Stage 47, #138)

Frozen, hand-adjudicated execution attempts. Every entry's
`expected_rule` must equal `tools/idempotent_effects.decide(entry.attempt).rule`
and `expected_verdict` the verdict.
`standardctl idempotent-effects` validates the set on every run.

## What the envelope proves

Stage 47 keeps crash/retry from duplicating comments, Issues,
dispatches, emails, deployments, or other mutations via
fingerprint plus authoritative-result reconciliation:

- `recorded-result` — replay, never re-execute.
- `duplicate-webhook` / `crash-after-remote` — replay paths.
- `conflicting-reuse` — same fingerprint never shifts payload.
- `changed-argument` / `stale-head` — re-guard before running.
- `mutated-result` — results immutable.
- `destructive-action` — unconfirmed deploys refuse.
- `missing-dedupe` — upserts/dispatches carry dedupe keys.

## No live effects

Decisions only: the suite exercises no product-side effects.
Denial is monotonic — no lower-trust callback reverses a
refusal.
