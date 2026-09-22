# Arc A phase-gate corpus (Stage 34, #125)

Frozen, hand-adjudicated Arc A packets for one demo slice.
Every entry's `expected_rules` must equal the sorted rule set
from `tools/arc_gate.advance(entry.packet)`; `expected_phase`
must equal the reached phase state and `expected_authorized`
the authorization flag. `standardctl arc-a` validates the set
on every run.

## What the gate proves

The Arc A packet composes every Stage 29-33 contract plus the
DoR, disposition, prompt, capsule, and budget gates into one
phase-state machine (SPEC_READY through IMPLEMENT_AUTHORIZED).
A clean packet advances; each negative pins at the last
fully-held state with exactly its rule:

- SPEC_READY pins: `no-spec`, `spec-blocked`, `mold-unqualified`
- MOLD_QUALIFIED pins: `attack-missing` (absent, same-provider,
  bad verdict, or unbound fixed-requalified)
- ATTACK_CLEAN pins: `session-dirty`, `portfolio-invalid`,
  `freeze-invalid`
- CHECKPOINTED pins: `not-ready`, `disposition-blocked`,
  `prompt-impure`, `capsule-unready`, `budget-recovery`,
  `production-write`

## The independence proof

The attack report is the Stage 34 addition over Stages 29-33:
a different-provider attacker reviews the Mold. `clean` means
nothing material was found; `fixed-requalified` means the
owner fixed the finding and earned a fresh digest-bound
receipt (verified by `mold_qualification.verify_receipt`).
Same-provider reports are refused — independence is
mechanical, not honor-system.

## No production code

Arc A authorizes no production writes: `production-write`
fires on any `src/`, `packages/`, `apps/`, or `services/`
write or any protected-path touch, even when every other
gate is clean. Builder authorization itself is Stage 35.
