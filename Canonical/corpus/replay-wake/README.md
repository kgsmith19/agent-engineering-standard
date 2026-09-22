# Replay/wake corpus (Stage 44, #135)

Frozen, hand-adjudicated wake observations. Every entry's
`expected_rule` must equal `tools/replay_wake.wake(entry.observation).rule`
and `expected_verdict` the verdict.
`standardctl replay-wake` validates the set on every run.

## What wake proves

Stage 44 reconstructs task plus next safe action from replayed
journal and reconciled state — never transcript, never model
recollection, never fabricated defaults:

- `clean` — CLEAN_RESUME: replay clean, head matches.
- `interrupted-phase` / `incomplete-check` — RECHECKPOINT.
- `moved-head` / `missing-commit` — RECONCILE_HEAD.
- `stale-capsule` / `corrupt-snapshot` / `provider-change` /
  `duplicate-event` — RECONCILE_STATE.
- `github-down` — GITHUB_DOWN: read-only only.
- `merged-done` — MERGED_DONE: close out, never resume.
