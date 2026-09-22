# Context rotation corpus (Stage 48, #139)

Frozen, hand-adjudicated rotation signals. Every entry's
`expected_rule` must equal `tools/context_rotation.decide(entry.signal).rule`
and `expected_verdict` the verdict.
`standardctl context-rotation` validates the set on every run.

## What rotation proves

Stage 48 wires the Context Governor to semantic rotation
boundaries (checkpoint->lease->capsule->session->HAT/SAT->
resume), keeping automatic compactions at zero:

- `boundary-due` — Spec->Mold, Mold->Builder, GREEN->Verifier,
  review->Remediator, merge->next-Issue.
- `imminent-compact` / `read-only-bound` / `overflow-output`
  — rotate before tripwires, bounds, and overflows.
- `missing-checkpoint` — HOLD and checkpoint first.
- `provider-switch` — rotate with cross-provider acceptance.
- `compacted` — FREEZE until wake proves state (never recover
  through compaction).
- `polluted` — RECOVER from capsule.
- `canary-missing` — HOLD advisory until provider canaries pass.
