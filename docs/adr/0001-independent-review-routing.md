# ADR 0001: Cost-aware exact-head machine review

Status: accepted; revised by autonomous PR control-plane work

## Decision

Require one fresh machine review task/session for every mergeable PR head SHA and expose its result as the required GitHub `AI Review` check.

- `PR Gate` remains independent deterministic evidence.
- Branch names and editable PR prose are not trusted as implementation identity.
- A PR authored by the Codex GitHub App requires Copilot review.
- All other PRs prefer a fresh Codex review task/session.
- Copilot is the bounded fallback when Codex stalls.
- Claude is not counted until a mechanical GitHub review adapter exists.
- One review response batches correctness/security, requirement fit, business ROI, systems optimization, and strict leanness.
- Any exact-head P0-P2 finding fails `AI Review`; repair produces a new SHA and restarts both gates.
- Clean formal review, structured Copilot exact-head PASS, or Codex thumbs-up bound to an exact-head request can pass the check.
- A later push invalidates previous review evidence.
- Normal cost budget is two reviewed heads: initial plus one post-fix head.
- Drafts receive no semantic review.
- Native CODEOWNERS is absent and required human approval count is zero, so review never silently becomes a Kyle bottleneck.
- R0-R3 may auto-merge after latest-head `PR Gate`, `AI Review`, and resolved threads.
- R4 and self-modifying control-plane changes retain explicitly justified authority gates.

## Why

A call-time script check is insufficient because GitHub auto-merge can remain armed after a later push. A required exact-head status makes GitHub enforce freshness.

Provider claims based on branch prefixes are forgeable. The selected rule uses authenticated review-service identities and treats each review invocation as a fresh task/session. The Codex App author exception prevents the clearest same-agent self-review case without paying for two models on every ordinary PR.

A single multi-lens response is cheaper and faster than several specialist calls. Bounded repair and fallback prevent indefinite model spend or stuck PRs.

## Trust boundary

Product repositories use thin callers pinned to the exact SHA in `.agent/standard.lock`. The shared evaluator and PR orchestrator live in `agent-engineering-standard` and are checked out at that pinned SHA. Product PRs cannot silently drift onto a moving evaluator.

Changes to the standard's own evaluator remain manually integrated while the repository can change the judge that evaluates itself.

## Evolution

Change providers, models, budgets, or manual gates only from measured latency, cost, finding quality, false positives, and recovery success. Add Claude only after an exact-head GitHub adapter is implemented and can be tested as mechanically as Codex and Copilot.
