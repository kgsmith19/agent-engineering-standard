# Mold qualification corpus (Stage 31, #122)

Frozen, hand-adjudicated qualification runs for one Mold.
Every entry's `expected_rules` must equal the sorted rule set
from `tools/mold_qualification.qualify(entry.run)`; qualified
entries carry zero rules and earn a digest-bound receipt.
`standardctl mold-qualify` validates both sets on every run.

## What qualification proves

The Mold rejects hard-coded examples, omitted state,
swallowed errors, mock-only assertions, setup
self-assertions, structural failures mistaken for RED, and
equivalent mutants — while accepting a genuinely valid
alternative implementation after true RED. Skipped, filtered,
empty, and placeholder tests never qualify.

## The receipt digest binding

On qualified only, `issue_receipt` binds `mold_digest`,
`head`, `provider`, and `run_digest` (sha256 hex of the
canonical JSON of the run: `json.dumps` with
`sort_keys=True`, UTF-8). `verify_receipt` recomputes the
digest and reports mold/head/run mismatches. The digest
binding IS the trust mechanism — no signatures or keys.

## Meta-test guarantees

`tools/meta_tests.check_meta` proves the Arc A process stayed
honest: zero production writes (`src/`, `packages/`,
`apps/`, `services/`), zero protected-path touches, every
expected control ran, every hash matches. The real Arc A
session (PRs #188-193) is asserted clean by test.
