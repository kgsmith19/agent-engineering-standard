# Human-by-exception corpus (Stage 51, #142)

Frozen, hand-adjudicated topology proposals. Every entry's
`expected_rule` must equal `tools/human_exception.decide(entry.proposal).rule`
and `expected_verdict` the verdict.
`standardctl human-exception` validates the set on every run.

## What the policy proves

Stage 51 keeps autonomy high and coordination low: one
accountable producer plus targeted independent evaluation by
default, councils only on explicit justification:

- `clean-produce` — PRODUCE: the default.
- `ambiguous-owner` / `intervention-due` — ESCALATE.
- `no-ready-work` / `false-escalation` / `generic-council` —
  HOLD (no busywork, no triggerless escalation, no token burn).
- `conflicting-advice` — CONSULT one critic.
- `competitive-mold` / `approved-council` — COUNCIL explicit.

## Consensus is never proof

Conversational agreement among agents proves nothing; only
rule-grounded evaluation counts. The owner may always request
teams explicitly.
