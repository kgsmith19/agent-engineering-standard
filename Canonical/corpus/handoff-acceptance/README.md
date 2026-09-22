# Handoff acceptance corpus (Stage 45, #136)

Frozen, hand-adjudicated acceptance attempts. Every entry's
`expected_rules` must equal the sorted rule set from
`tools/handoff_acceptance.accept(entry.attempt)`;
`expected_accepted` must equal the accepted flag.
`standardctl handoff-acceptance` validates the set on every run.

## What the gate proves

Stage 45 denies write authority until a fresh role proves exact
task, reconciled state, applicable critical rules, and next
action — HAT always, selective SAT on trigger:

- `wrong-phase` / `stale-head` — exact task and state.
- `missing-decision` / `protected-omitted` — decisions and
  full scope recorded.
- `guardrail-gap` / `prompt-injection` — guarded providers,
  injected prompts never write.
- `sat-required` — new provider, R2/R3, privileged path, or
  authority change needs passed SAT (R0/compact exempt).
- `cross-provider` — restatement matches the Standards route.

## Receipts bind forward

ACCEPT mints an acceptance receipt (task, head, rules, action,
HAT/SAT kind) bound into the Stage 46 lease and evidence chain.
