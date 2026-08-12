# ADR 0004: Remove AI code review from the blocking merge path

Status: accepted (2026-08-11). Supersedes ADR 0001's requirement/routing mechanics and ADR 0003's dispatch-disabled canary in full; formalizes issue #58 ("Remove AI Review from the blocking merge path fleet-wide"). Does not touch ADR 0002's manual control-plane/R4 authority gates, which are a separate mechanism.

## Decision

Inline AI code review is removed from the primary CI/CD blocking path entirely, fleet-wide. The mandatory blocking gate consists exclusively of deterministic checks: `PR Gate` (lint, unit tests, security audit, merge-conflict validation). There is no `AI Review` check, required or advisory, produced by the standard's own automation anymore.

Removed outright (not demoted to advisory-only — issue #58 left that choice open; this ADR resolves it):

- `.github/workflows/ai-review.yml`, `ai-review-reusable.yml`, `pr-automation-review-event.yml`, `pr-automation-comment-event.yml`
- `scripts/evaluate-ai-review.ps1`, `request-machine-review.ps1`, `request-review-repair.ps1`, `reconcile-machine-review-threads.ps1`, `pause-pending-review.ps1`, `review-metrics.ps1`, `request-independent-review.ps1`
- `templates/AI_REVIEW.yml`, `templates/PR_AUTOMATION_REVIEW_EVENT.yml`, `templates/PR_AUTOMATION_COMMENT_EVENT.yml`
- the `independent_review` policy block (`dispatch_mode`, `dispatch_policy_version`, provider routing, review-wait budgets) and `required_ai_review_context`
- Dependabot as a provisioned mechanism: `templates/dependabot.yml`, and `bootstrap-repo.ps1`/`upgrade-repos.ps1` no longer install `.github/dependabot.yml` (a repo owner may still run Dependabot independently; the orchestrator's `@dependabot rebase` conflict-repair path is unaffected since it only reacts to a PR's author identity, it does not provision anything)

## What is explicitly *not* changed

- **The R4/control-plane manual authority gate** (`policy/manual_gates`, `Tag-Authority`, `Assert-ManualGateJustification`) is untouched. It is a separate mechanism from AI Review: it requires the owner's explicit sign-off for destructive/irreversible actions and for changes to the evaluator/merge-authority code itself, and was never gated on the review check.
- **Bounded CI and conflict repair dispatch** (`@copilot investigate and fix ...`, `@dependabot rebase`) is preserved as-is, including its current disabled state — relocated from `independent_review.dispatch_mode` to `pr_automation.repair_dispatch_enabled` (still `false`) since its original canary justification (proving the AI-review state machine safe before full rollout, ADR 0003) no longer applies once that state machine is deleted.
- **The six-hourly watchdog** is preserved for its general purpose — catching PRs whose gate-result webhook was missed — which is independent of AI Review. Only its review-timeout-specific branches were removed.
- **`scripts/codex-review.ps1`** remains available as an optional, local, manual second opinion. It was never part of the blocking path and is not part of this removal.

## Why

Real, live friction (2026-08-10): `lifeos` PR #95, a pure mechanical standard-adoption PR, was held by AI Review's `dispatch-disabled-R3` hold and required an `--admin` merge override to unblock, despite `PR Gate` (deterministic CI) passing cleanly. This is the same failure class ADR 0002 already partially addressed by demoting AI Review to advisory — this ADR finishes that trajectory by removing the mechanism outright, since a fleet-wide semantic-review dispatch system that costs real engineering surface (a ~3,200-line orchestrator/evaluator/test suite across this repo alone) never reached a state where it produced net-positive signal over deterministic checks alone.

## Scope note

Issue #58 flagged this as "real, multi-file, cross-repo -- needs its own spec pass, not a quick toggle." This ADR is that pass. `agentic-command-center`, `lifeos`, and `toolbelt` were audited individually; none had AI Review, Dependabot, or watchdog machinery provisioned, so no product-repo changes were needed beyond this standard repo itself.

## Reversal condition

If a future case shows deterministic checks alone let a real defect through that semantic review would have caught, re-introduce review as strictly advisory (never a required or blocking status check) and measure false-positive/negative rates before ever considering blocking again.
