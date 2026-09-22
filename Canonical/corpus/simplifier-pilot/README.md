# Simplifier pilot corpus (Stage 40b, #131)

Frozen, hand-adjudicated simplification proposals. Every
entry's `expected_rules` must equal the sorted rule set from
`tools/simplifier_pilot.decide(entry.proposal)`;
`expected_verdict` must equal the verdict.
`standardctl simplifier-pilot` validates the set on every run.

## What the gate proves

Stage 40b pilots an existing reputable simplifier as an
on-demand role after GREEN — never resident, never before
GREEN, never without a fresh Verifier full-Mold rerun plus
quality-gate rerun:

- `pre-green` — activation only after qualified GREEN.
- `resident-plugin` — on-demand role only, never resident.
- `scope-breach` — inside the Builder diff, under the cap.
- `contract-change` — semantics and contracts preserved.
- `unevidenced` — new abstractions need reduction evidence.
- `no-rerun` — fresh Verifier + quality reruns required.

## Advisory pilot only

PROCEED records before/after evidence (LOC, complexity,
duplication, review effort, regressions, model/context cost).
Promotion or eject requires owner review after a
representative sample.
