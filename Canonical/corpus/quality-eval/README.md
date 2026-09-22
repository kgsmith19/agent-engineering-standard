# Implementation-quality evaluation corpus (Stage 41, #132)

Frozen, hand-adjudicated evaluation tasks. Every entry's
`expected_winner` must equal the top-ranked solution from
`tools/quality_eval.rank(entry.solutions)` with rule-grounded
reviewer agreement on every solution.
`standardctl quality-eval` validates the set on every run.

## What the corpus proves

Stage 41 closes the Implementation Quality phase by measuring
whether Builders produce minimum, clear, correct code:

- Duplicate paths, wrapper-only abstractions, excessive
  dependency, wrong plane, and missing cleanup tasks prove
  Stages 36-39 conformance counts.
- A large necessary safety implementation beats any incorrect
  shortcut; the smallest-LOC incorrect solution always loses
  — superficial shortness is never rewarded.
- The Stage 40 simplifier is never favored: simplifier touch
  without conformance still loses.
- Independent reviewers agree on rule-grounded results.

## Baseline measurement only

Correctness gates everything (incorrect scores 0, never
wins); conformance costs 10 per miss; parsimony breaks ties
among the correct. No blocking threshold until data exists —
the corpus measures, the owner decides.
