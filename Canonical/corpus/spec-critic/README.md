# Spec critic eval (Stage 28, #119)

Frozen, hand-adjudicated challenge set for the fresh Spec critic.
Every entry's `expected_rules` must equal the sorted rule set from
`tools/spec_critic.critique(spec)`; `standardctl spec-critic`
validates this on every run.

## What the critic challenges

Tenant ambiguity, contradictory examples, untestable adjectives,
missing timeouts, hidden migration order, overconstrained
implementation, and giant Specs — each a blocker or major finding
with repair guidance and an excerpt.

## Severity semantics

- blocker: must fix before the Spec is ready (ambiguity,
  contradiction, missing bound, hidden order, giant Spec).
- major: measurable weakness to fix (vague adjectives,
  implementation-pinned criteria).
- minor: reserved; unused by the frozen rules.

## When it skips compact work

Compact scope (not assured, or risk R0/R1) returns `skipped` with
zero findings regardless of content — the critic never burdens
small or unassured work. Only assured R2/R3 runs the rules.
The `compact-control` entry proves silence; identical words as
assured R2 produce findings.
