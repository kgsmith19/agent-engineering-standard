# Plane enforcement corpus (Stage 38, #129)

Frozen, hand-adjudicated file events for plane enforcement.
Every entry's `expected_rules` must equal the sorted rule set
from `tools/plane_enforcement.classify(entry.event)`;
`expected_clean` must equal the clean flag.
`standardctl plane-enforcement` validates the set on every run.

## What the classifier proves

Stage 38 keeps agents editing the right representation across
six planes (source/generated/artifact/cache/evidence/
protected, mirroring tools/repo_map.py precedence):

- `generated-direct-edit` — direct generated edits refused;
  regenerate via the owning tool.
- `generated-stale` — stale generated output after a source
  change refused; regenerate before merging.
- `cache-committed` — caches never committed.
- `evidence-misplaced` — evidence lives under .evidence/.
- `protected-unauthorized` — control-plane edits need owner
  authorization (blocker).
- `orphan-directory` — new directories need a current owner.
- `stale-artifact` — deleted sources must not leave stale
  artifacts.

## Exceptions that pass

A declared generated migration (`declared_migration`) and an
authorized protected-path edit (`authorized`) are CLEAN — the
exception paths actually pass, so the gate is a classifier
with repair messages, not a blanket refusal.
