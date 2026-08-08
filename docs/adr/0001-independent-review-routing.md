# ADR 0001: Cost-aware independent AI review

Status: accepted for implementation in Issue #17

## Decision

Use one cheap, current-head, cross-provider semantic review before automated merge.

- Deterministic evidence runs first.
- Claude/Copilot implementations prefer Codex review.
- Codex implementations prefer one Copilot review; a fresh Claude session/model/context is the fallback when available.
- The default semantic pass batches software/security, business/product, systems/optimization, and leanness lenses into one call.
- Default budget: at most two Codex passes (initial + one re-review) and one Copilot fallback per PR.
- Draft churn and every-push Copilot re-review are disabled by default.
- R0-R3 may auto-merge after current-head independent review plus required GitHub evidence when live policy permits.
- R4 remains an authorization gate for destructive/financial/privileged/irreversible consequence.
- A manual gate is invalid unless it states the failure class, why automation is insufficient, decision owner, and removal condition.

## Why

Independent semantic review has value, but multiple paid reviewers on every PR waste time and budget. One batched cross-provider review catches implementation, product, business-system, and complexity problems without multiplying calls. Provider separation reduces correlated implementation/review blind spots.

## Removal / evolution

Change provider/model/budget only from measured quality, latency, and cost evidence. Eliminate remaining manual control-plane review once the governing evaluator and merge authority are external/immutable to the PR being judged.
