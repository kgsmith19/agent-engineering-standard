# ADR 0001: Cost-aware independent AI review

Status: accepted; hardened by Issue #21

## Decision

<<<<<<< HEAD
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
=======
Use the smallest provider-specific semantic review set **per mergeable head SHA**, enforced as the required GitHub `AI Review` check.

- Deterministic `PR Gate` runs independently.
- Agent provenance comes from controlled provider branch/author metadata, not editable PR prose.
- ChatGPT implementations require Copilot review.
- Claude/Copilot implementations require Codex review.
- Codex implementations require Copilot review.
- Ordinary/user-authored provenance is ambiguous for independence and therefore requires both Codex + Copilot for unattended merge.
- No Claude fallback is claimed until a mechanical Claude review adapter exists.
- One semantic response batches software/security, business/product, systems/optimization, and leanness lenses.
- Budget: at most two Codex response passes (initial + one re-review) and one Copilot response pass per PR.
- Draft churn does not consume semantic-review budget; exact-head request markers prevent duplicate triggers.
- A push after review creates a new SHA; the previous `AI Review` result cannot authorize that new head.
- `AI Review` evaluator runs are serialized per PR so stale concurrent runs cannot overwrite newer evidence.
>>>>>>> origin/main
- R0-R3 may auto-merge only after latest-head `PR Gate` + `AI Review` and resolved review threads.
- R4 remains an explicit authorization gate for destructive/financial/privileged/irreversible consequence.
- Manual gates require failure class, automation insufficiency, decision owner, and removal condition.

## Why

<<<<<<< HEAD
A call-time script check is insufficient: auto-merge can remain armed after a later push. A required exact-head check makes GitHub itself enforce semantic-review freshness. Provider separation reduces correlated blind spots, and batching business/system/lean lenses into one review avoids multiplying model calls.

## Trust boundary

For product repos, the thin `AI Review` caller uses the shared evaluator in `agent-engineering-standard`. Control-plane changes to the standard remain manually merged while they can alter the evaluator that judges themselves.

## Evolution

Change model/provider/budget only from measured quality, latency, and cost. Eliminate the remaining control-plane manual gate when the evaluator/merge authority is immutable or organization-required and cannot be modified by the PR under judgment.
=======
A call-time script check is insufficient because auto-merge can remain armed after a later push. A required exact-head check makes GitHub itself enforce semantic-review freshness. Known provider provenance allows one truly cross-provider review, while ambiguous provenance pays for both connected providers rather than trusting a self-attested implementer identity. Batching business/system/lean lenses avoids multiplying calls.

## Trust boundary

Product repos use a thin `AI Review` caller backed by the shared evaluator in `agent-engineering-standard`. Control-plane changes to the standard remain manually merged while they can alter the evaluator that judges themselves.

## Evolution

Change provider/model/budget only from measured quality, latency, and cost. Eliminate the remaining control-plane manual gate when evaluator/merge authority is immutable or organization-required and cannot be modified by the PR under judgment.
>>>>>>> origin/main
