# ADR 0002: Deterministic merge authority — machine review demoted to advisory

Status: proposed (2026-08-09). Amends ADR 0001, which remains the record for how a machine reviewer is routed *when one is used*.

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
- Repair budgets widened (`max_ci_fix_attempts` 3→7, `max_conflict_fix_attempts` 2→6) and the watchdog runs hourly (cron `17 * * * *`, `watchdog_interval_minutes` 60): failures burn through automated repair attempts before `status:blocked` asks for a human.
- A fine-grained PAT (`AUTOMATION_TOKEN`, Administration:read) backs the calls `GITHUB_TOKEN` cannot perform correctly: admin settings/ruleset reads in `auto-merge.ps1` and arming the merge so its push triggers `on: push` pipelines. Check runs stay on `GITHUB_TOKEN` for GitHub-Actions app attribution. The PAT is never exposed to PR-authored code.
- Reviewer-independence routing (ADR 0001) is dormant while `solicit_reviews` is `false`; it governs again the moment either flag is enabled.
