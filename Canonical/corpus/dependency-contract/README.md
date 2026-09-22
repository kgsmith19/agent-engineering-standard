# Dependency decision corpus (Stage 39, #130)

Frozen, hand-adjudicated dependency proposals. Every entry's
`expected_rules` must equal the sorted rule set from
`tools/dependency_contract.decide(entry.proposal)`;
`expected_verdict` must equal the verdict.
`standardctl dependency-contract` validates the set on every run.

## What the contract proves

Stage 39 prefers proven libraries or native platform
capability only when they reduce total owned complexity:

- `license-conflict` — incompatible licenses reject (blocker).
- `supply-chain-alert` — abandoned or alerted packages reject.
- `duplicates-platform` — platform-owned capability wins.
- `heavy-for-value` — popular-but-heavy weight must delete
  real owned complexity (>= 500 LOC).
- `local-cheaper` — a tiny secure local helper wins as
  ADOPT-LOCAL, never a ban on local code.

## Advisory baseline only

A clean library proposal is ADOPT-LIBRARY; the local helper
is ADOPT-LOCAL; anything else is REJECT with its rule. No
blocking threshold in this stage — the baseline informs, the
owner decides. Rollback data (pin + revert plan) rides every
ADOPT verdict.
