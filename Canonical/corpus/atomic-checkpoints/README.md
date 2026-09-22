# Atomic checkpoint corpus (Stage 43, #134)

Frozen, hand-adjudicated checkpoint attempts. Every entry's
`expected_rules` must equal the sorted rule set from
`tools/atomic_checkpoints.decide(entry.attempt)`;
`expected_outcome` and `expected_coherent` must match.
`standardctl atomic-checkpoints` validates the set on every run.

## What the mechanism proves

Stage 43 recovers every context/role transition at coherent
semantic barriers (PREPARE->SAVE->PUBLISH->READ-BACK->FINALIZE)
with compare-and-swap staleness protection:

- `dirty-worktree` / `tests-incomplete` — never checkpoint
  half-finished or unproven work as complete.
- `stale-cas` — CAS never bypassed (blocker).
- `crash-interrupt` — every barrier crashes back to its last
  coherent barrier.
- `push-failed` — publish faults recover to SAVE.
- `corrupt-artifact` — invalid bytes refuse (blocker).
- `duplicate-finalize` — second finalize is a no-op signal.
- `remote-ahead` — remote-before-local recovers to READ-BACK.

## Recovery to coherence

Outcomes are CHECKPOINTED (at FINALIZE), RECOVER (with the
coherent barrier), or REFUSE. No general-purpose snapshots;
no CAS bypass.
