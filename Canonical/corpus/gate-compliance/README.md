# Gate compliance corpus (Stage 57, #148)

Frozen, hand-adjudicated lane observations. Every entry's
`expected_rule` must equal `tools/gate_compliance.evaluate(entry.observation).rule`
and `expected_verdict` the verdict.
`standardctl gate-compliance` validates the set on every run.

## What the lane proves

Stage 57 feeds Standards Compliance into the existing PR Gate
without a second required context — read-only reporting that
the single final aggregator consumes:

- `missing-receipt` — green tests still need the receipt.
- `stale-route` — expanded paths re-route.
- `adapter-degraded` — degraded adapters block.
- `mold-violation` — unauthorized Mold writes block.
- `self-certify` — policy PRs never self-certify.
- `compact-valid` — valid compact work passes quietly.
- `lane-skipped` — the lane never absents.
- `head-moved` — moved heads re-verify.

## One final Gate

Simple and monorepo profiles both report; the sole required
check stays the final aggregator.
