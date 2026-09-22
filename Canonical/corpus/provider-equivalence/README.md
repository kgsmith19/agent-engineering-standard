# Provider equivalence corpus (Stage 56a, #147)

Frozen, hand-adjudicated equivalence cases. Every entry's
`expected_rule` must equal `tools/provider_equivalence.decide(entry.case).rule`
and `expected_outcome` the outcome.
`standardctl provider-equivalence` validates the set on every run.

## What equivalence proves

Stage 56a (Standard half) proves Claude, Codex,
Gemini/Antigravity, and local agents share canonical authority
with fail-safe divergence — owner/direct > normative policy >
verified capsule > task data > untrusted content:

- `nested-conflict` / `agents-override` — precedence holds.
- `comment-injection` / `filename-injection` /
  `tool-injection` — untrusted content never wins.
- `version-drift` — degraded parity recorded, never silent.
- `child-inheritance` / `missing-hook` / `manual-equivalent`
  — inheritance, lowered autonomy, explicit manuals.
- `hash-parity` — normalized hashes match across providers.

## Adapters separate

This half defines and canaries the contract; the 56b
extensions half builds provider adapters.
