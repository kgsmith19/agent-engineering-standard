# Independent review corpus (Stage 59a, #150)

Frozen, hand-adjudicated review requests and remediation
rounds. Review entries: `expected_rule` equals
`tools/independent_review.review(entry.request).rule` and
`expected_verdict` the verdict. Remediation entries:
`expected_rule` equals `remediate(entry.remediation).rule`
and `expected_outcome` the outcome.
`standardctl independent-review` validates the set on every run.

## What review proves

Stage 59a standardizes trusted provider-separated
evidence-bound review with deterministic verdicts plus a
bounded remediation loop — one Gate input, never a second
authority:

- `clean` — PASS with stable fingerprints.
- `p1-block` — P0/P1 BLOCK; `p2-advisory` — P2 advises.
- `fake-citation` / `oracle-weakening` / `prompt-injection` —
  untrustworthy, policy-breaking, or tainted reviews block.
- `malformed-input` / `reviewer-outage` / `stale-head` /
  `same-provider` — non-pass verdicts with recheck paths.
- `verdict-shopping` / `scope-creep` / `repeat-non-engage` —
  remediation rounds REFUSE.
- `dispute` — grounded disputes route via the criterion.
- `owner-override` — explicit owner provenance fixes.

## Bounded remediation

FIXED or DISPUTE only through the original criterion with
recheck; P2 never blocks; scope locks to the reviewed diff.
