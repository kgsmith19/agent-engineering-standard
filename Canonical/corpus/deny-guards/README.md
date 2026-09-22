# Deny guards corpus (Stage 55a, #146)

Frozen, hand-adjudicated guard requests. Every entry's
`expected_rule` must equal `tools/deny_guards.evaluate(entry.request).rule`
and `expected_verdict` the verdict.
`standardctl deny-guards` validates the set on every run.

## What the chain proves

Stage 55a (Standard half) pilots monotonic deny guards over a
trusted base policy — later layers restrict, never restore:

- `later-allow` / `hook-bug` — denial monotonic across layers
  and hook failures.
- `self-weaken` / `base-disagreement` — PR policy never
  self-certifies; disagreements reconcile.
- `owner-replacement` — explicit owner provenance ALLOWs.
- `adapter-gap` — unenforceable layers NO_OP with escalation.
- `protected-path` — unapproved control-plane DENYs.
- `ordinary-allow` — harmless edits ALLOW low-friction.

## Pilot scope

R3 pilot with canaries; the 55b extensions half owns provider
adapters. Owner override stays separate provenance.
