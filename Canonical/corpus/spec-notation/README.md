# Spec notation corpus (Stage 27, #118)

Frozen, hand-adjudicated translation corpus for Thin Spec notation
selection. Every entry's `expected_notation` must equal
`tools/spec_notation.select_notation(task)`; `standardctl spec-notation`
validates this on every run.

## IDs are stable

`spec-notation.<category>.<nn>` IDs never change across test or file
renames. Never renumber, never repurpose: retire an entry by deleting
it (with an Issue), never by editing its ID.

## Precedence (first match wins)

1. `authorization` -> specification_by_example (actor/resource/action table)
2. `concurrency_or_retry` -> atdd (failing test written first)
3. `external_effects` -> bdd (given/when/then, side effect named)
4. `stateful` -> ears (when/then requirement sentences)
5. otherwise -> plain

Ambiguity >= 2 at any risk: example mapping first (map examples, rules,
questions), then re-select from the mapped rules.

## When plain wins

- Cosmetic UI/text work (ambiguity 0, R0/R1): plain criteria are the
  ceiling; a heavyweight notation here is a finding.
- One input, one outcome (local bugs): a plain criterion is the exact
  behavior.
- A single when/then with no interlocking state: plain still carries it.
  EARS pays off when two or more conditions interlock.

## When to step back to example mapping

Any task with ambiguity 2-3: write concrete examples, distill rules,
keep questions open, then re-select. The mapped rules, not the mapping
session, are what the Spec carries.

## Guards

- plain + stateful/retry/external effects or R2/R3 -> under-specified.
- heavyweight notation + cosmetic (ambiguity 0, R0) -> over-specified.
