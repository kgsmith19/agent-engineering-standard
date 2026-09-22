# Recovery loop corpus (Stage 58, #149)

Frozen, hand-adjudicated failure reports. Every entry's
`expected_rule` must equal `tools/recovery_loop.triage(entry.report).rule`,
`expected_class` the class, `expected_route` the route.
`standardctl triage` validates the set on every run.

## What the loop proves

Stage 58 turns every unexpected failure into preserved
evidence, an explicit class, and the smallest responsible
recovery route — systematic-debugging always before repair:

- `blind-rerun` / `non-idempotent` — never loop blind.
- `partial-green` — partial never completes.
- `misclassified` / `infra-as-product` — classify honestly.
- `exhausted-budget` — spent budgets escalate.
- `unknown-mutation` — UNKNOWN never mutates.
- `unowned-lane` — every failure names its lane.
- `historical-replay` — history reproduces routes.
- `clean-triage` — clean reports repair with evidence.

## Bounded retry

Retry needs a transient hypothesis plus a budget on unchanged
idempotent state; Stage 47's guard still binds.
