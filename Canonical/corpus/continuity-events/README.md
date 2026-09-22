# Continuity event corpus (Stage 42, #133)

Frozen, hand-adjudicated event journals. Every entry's
`expected_rules` must equal the sorted rule set from
`tools/continuity_events.check_journal(entry.events)`; clean
entries must replay to a batching-stable state hash via
`tools/continuity_events.project`.
`standardctl continuity-events` validates the set on every run.

## What the model proves

Stage 42 represents non-derivable task transitions as compact
typed events with deterministic projection — a delta layer
over Git/GitHub, never a second tracker:

- `unknown-type` — taxonomy is frozen.
- `conflicting-duplicate` — append-only; same-payload
  re-append is idempotent, conflicts refuse.
- `gap` / `out-of-order` — ordered journals, no skips.
- `broken-hash` — hash-chain integrity (blocker).
- `secret-payload` — no credentials in journals (blocker).
- `oversized-payload` — 2 KiB budget; transcripts in Git.
- `git-contradiction` — Git/GitHub wins (blocker).

## Deterministic projection

State hash covers ordered (seq, type, payload-hash) triples:
replay batching never changes state. Claims project to
active/done; large payloads and side effects stay out.
