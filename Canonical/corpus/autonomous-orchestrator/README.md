# Autonomous orchestrator corpus (Stage 50, #141)

Frozen, hand-adjudicated orchestrator ticks. Every entry's
`expected_rule` must equal `tools/autonomous_orchestrator.next(entry.tick).rule`
and `expected_verdict` the verdict.
`standardctl orchestrator` validates the set on every run.

## What the dispatcher proves

Stage 50 advances authorized work without a human continue
command — one bounded action per tick inside existing
authorization (never around the PR Gate or owner escalation):

- `duplicate-event` — WAIT: never double-dispatch.
- `crash-around` / `double-worker` / `stale-head` — RECOVER.
- `no-ready-work` / `provider-down` — WAIT.
- `owner-hold` / `budget-exhausted` / `deadlock` — ESCALATE.
- `review-finding` / `merge-cleanup` / `clean-next` — NEXT one
  bounded action.
- `milestone-done` — COMPLETE hands to the Release Mold.

## Dry-run only

Advisory/dry-run until canaries pass: `advance --apply`
stays disabled for real mutation in this stage.
