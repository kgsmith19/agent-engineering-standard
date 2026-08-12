# ADR 0002: Deterministic merge authority — machine review demoted to advisory

Status: superseded by ADR 0004 (2026-08-11) for the AI-review-demotion decision — AI code review was removed from the blocking path entirely, not merely demoted. This ADR's manual control-plane/R4 authority-gate decision remains in force, unaffected by ADR 0004.

## Decision

The unattended merge lane gates on exactly one required status context: the deterministic `PR Gate`. `AI Review` is no longer a required context, no longer pauses or disarms auto-merge, and by default is not solicited at all.

Two policy flags in `policy/github-defaults.json.independent_review` control the review lane:

- `required_for_auto_merge` (now `false`): when `true`, `AI Review` is restored as a second required ruleset context and review outcomes can block the lane (the pre-2026-08-09 behavior).
- `solicit_reviews` (now `false`): when `true` while review is not required, the orchestrator still requests machine reviews and posts the `AI Review` check as advisory evidence, but nothing waits on it.

With both `false`, the review machinery (`evaluate-ai-review.ps1`, `request-machine-review.ps1`, and peers) is fully inert. It is retained, not deleted, so the follow-up decision between "informational reviews" (flip `solicit_reviews`) and "full removal" (delete the machinery and supersede this ADR) stays a one-line change in either direction.

## Why

1. The portfolio owner's standing directive: merges must rely entirely on deterministic CI/CD gates, with no AI reviewer in the merge authority.
2. The required `AI Review` context had a structural trap: the check run only exists once the orchestrator solicits a review, so on any repository where the driver is missing or stalls (two portfolio repos had no `pr-automation.yml` at all), every PR is unmergeable — and with zero ruleset bypass actors, not even an admin can merge past it.
3. Review stall classes (`review-request`, `review-fallback`, `review-timeout`, `review-budget`) accounted for most of the lane's ways to park a PR without a human decision actually being needed.

## Consequences

- `apply-github-standard.ps1`, `auto-merge.ps1`, and `doctor.ps1` now derive the required-context list from `required_for_auto_merge` instead of hardcoding both names.
- `required_review_thread_resolution` is `false`: with no required reviewer, an unresolved stray comment thread must not block a merge forever with nobody assigned to resolve it.
- Repair budgets and cadence (amended 2026-08-09): the original demotion widened budgets to 7 CI / 6 conflict repairs with an hourly watchdog; the approved all-13 design re-narrowed them to `max_ci_fix_attempts` 3, `max_conflict_fix_attempts` 2, and a six-hourly watchdog (cron `17 */6 * * *`, `watchdog_interval_minutes` 360). Failures still burn through automated repair attempts before `status:blocked` asks for a human.
- A fine-grained PAT (`AUTOMATION_TOKEN`, Administration:read) backs the calls `GITHUB_TOKEN` cannot perform correctly: admin settings/ruleset reads in `auto-merge.ps1` and arming the merge so its push triggers `on: push` pipelines. Check runs stay on `GITHUB_TOKEN` for GitHub-Actions app attribution. The PAT is never exposed to PR-authored code.
- Reviewer-independence routing (ADR 0001) is dormant while `solicit_reviews` is `false`; it governs again the moment either flag is enabled.
