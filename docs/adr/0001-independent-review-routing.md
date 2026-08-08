# ADR 0001: Cost-aware independent AI review

Status: accepted; hardened by Issue #21

## Decision

Use one cheap, cross-provider semantic review **per mergeable head SHA**, enforced as the required GitHub `AI Review` check.

- Deterministic `PR Gate` runs independently.
- GitHub Actions attests implementation provenance from recognized provider author/branch metadata instead of trusting editable PR-body LLM claims.
- Claude/Copilot implementations prefer Codex review.
- Codex implementations use one Copilot review. No Claude fallback is claimed until a mechanical Claude review adapter exists.
- Human implementation uses Codex by default.
- One semantic pass batches software/security, business/product, systems/optimization, and leanness lenses.
- Budget: at most two Codex passes (initial + one re-review) and one Copilot fallback per PR.
- Draft churn does not consume semantic-review budget.
- A push after review creates a new SHA; the previous `AI Review` result cannot authorize that new head.
- R0-R3 may auto-merge only after latest-head `PR Gate` + `AI Review` and resolved review threads.
- R4 remains an explicit authorization gate for destructive/financial/privileged/irreversible consequence.
- Manual gates require failure class, automation insufficiency, decision owner, and removal condition.

## Why

A call-time script check is insufficient: auto-merge can remain armed after a later push. A required exact-head check makes GitHub itself enforce semantic-review freshness. Provider separation reduces correlated blind spots, and batching business/system/lean lenses into one review avoids multiplying model calls.

## Trust boundary

For product repos, the thin `AI Review` caller uses the shared evaluator in `agent-engineering-standard`. Control-plane changes to the standard remain manually merged while they can alter the evaluator that judges themselves.

## Evolution

Change model/provider/budget only from measured quality, latency, and cost. Eliminate the remaining control-plane manual gate when the evaluator/merge authority is immutable or organization-required and cannot be modified by the PR under judgment.
