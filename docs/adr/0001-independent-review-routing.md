# ADR 0001: Cost-aware independent AI review

Status: accepted; hardened by Issue #21

## Decision

Use the smallest provider-specific semantic review set **per mergeable head SHA**, enforced as the required GitHub `AI Review` check.

- Deterministic `PR Gate` runs independently.
- Agent provenance comes from controlled provider branch/author metadata, not editable PR prose.
- ChatGPT implementations require Copilot review.
- Claude/Copilot implementations require Codex review.
- Codex implementations require Copilot review.
- Ordinary/user-authored provenance is ambiguous for independence and therefore requires both Codex + Copilot for unattended merge, in that order.
- Required-provider order is fail-closed: if the next required provider is unavailable or at budget, later providers are not skipped ahead.
- For ambiguous provenance, provider #2 is requested only after provider #1 has passed the current head. A current-head FAIL suppresses additional provider spend until the code changes.
- No Claude fallback is claimed until a mechanical Claude review adapter exists.
- One semantic response batches software/security, business/product, systems/optimization, and leanness lenses.
- One response per required provider is the normal path. Each exact head is requested at most once per provider. A PR may consume at most three semantic responses per provider across legitimate head changes/fix cycles; after that it must stop and be split/restarted instead of entering an unbounded review loop.
- Draft churn does not consume semantic-review budget; exact-head request markers prevent duplicate triggers.
- A push after review creates a new SHA; the previous `AI Review` result cannot authorize that new head.
- A successful `PR Gate` may request semantic review only when that completed run's `head_sha` still equals the PR's current head.
- `AI Review` evaluator runs are serialized per PR so stale concurrent runs cannot overwrite newer evidence.
- R0-R3 may auto-merge only after latest-head `PR Gate` + `AI Review` and resolved review threads.
- R4 remains an explicit authorization gate for destructive/financial/privileged/irreversible consequence.
- Manual gates require failure class, automation insufficiency, decision owner, and removal condition.

## Why

A call-time script check is insufficient because auto-merge can remain armed after a later push. A required exact-head check makes GitHub itself enforce semantic-review freshness. Known provider provenance allows one truly cross-provider review, while ambiguous provenance pays for both connected providers rather than trusting a self-attested implementer identity. Ordered chaining prevents spending a later provider before its prerequisite reviewer has passed, while current-head failure suppression avoids paying for extra opinions on code already known to need repair. Batching business/system/lean lenses avoids multiplying calls. A small hard cap preserves a bounded path through legitimate post-review fixes and changed heads without making semantic review an unlimited per-push tax.

## Trust boundary

Product repos use a thin `AI Review` caller backed by the shared evaluator in `agent-engineering-standard`. Control-plane changes to the standard remain manually merged while they can alter the evaluator that judges themselves.

## Evolution

Change provider/model/budget only from measured quality, latency, and cost. Eliminate the remaining control-plane manual gate when evaluator/merge authority is immutable or organization-required and cannot be modified by the PR under judgment.
