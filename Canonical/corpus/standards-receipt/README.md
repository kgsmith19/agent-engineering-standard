# Standards receipt corpus (Stage 53, #144)

Frozen, hand-adjudicated receipt attempts. Every entry's
`expected_rule` must equal `tools/standards_receipt.issue(entry.attempt).rule`
and `expected_verdict` the verdict.
`standardctl standards-receipt` validates the set on every run.

## What receipts prove

Stage 53 proves standards were supplied and acknowledged where
risk justifies it — no low-risk theater, no skipped SAT:

- `wrong-ack` / `missing-critical` — exact acknowledgement.
- `stale-spec` / `stale-path` / `stale-phase` /
  `stale-standard` — fresh routing inputs.
- `r0-no-quiz` — R0/R1 issue without a quiz.
- `r3-required` — triggers quiz until SAT passes.
- `adapter-omitted` / `own-receipt` / `lower-trust` — refuse.
- `clean-receipt` — complete triggered attempts with passed
  SAT issue with bound hashes.

## Hash binding

Route, receipt, and SAT hashes bind into Work State and
evidence; any drift re-routes.
