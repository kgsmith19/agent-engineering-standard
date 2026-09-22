# Clean Implementation Charter corpus (Stage 36, #127)

Frozen, hand-adjudicated change descriptions for the charter.
Every entry's `expected_rules` must equal the sorted rule set
from `tools/clean_charter.classify(entry.change)`; `expected_clean`
must equal the clean flag. `standardctl clean-charter` validates
the set on every run.

## What the charter proves

Stage 36 makes minimum correct, clear, tidy implementation an
explicit reviewable contract — without a resident generic
clean-code skill. One change description maps to its rule hits:

- `CLEAN-1` — a wrapper layer adding no behavior needs a
  behavioral reason (a necessary safety layer never trips).
- `CLEAN-2` — a duplicate implementation of one behavior must
  reuse the canonical implementation (or name its reason).
- `CLEAN-3` — speculative configuration with no current caller
  waits for its caller (stack tooling owned by Stage 37).
- `CLEAN-4` — a huge mixed-responsibility file splits by
  behavior; a tiny justified abstraction stays.
- `CLEAN-5` — dead code (unreached, unused, commented-out) is
  deleted; history keeps the record.
- `CLEAN-6` — unrelated cleanup never rides a behavior-focused
  change; it moves to its own thin Issue.
- `CLEAN-7` — tiny abstractions need a stated reason; the
  exception path is explicit, never a bypass.

## No resident skill, no riders, no stack tooling

The charter classifies; it never rewrites code, never installs
a resident skill, never permits unrelated cleanup to ride
along, and never defines stack-specific linter tooling itself
(that is Stage 37's job, named per rule in RULE_TOOLING).
