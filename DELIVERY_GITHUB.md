# Delivery & GitHub

## Goal

Make GitHub the protected integration/enforcement plane while keeping feedback fast and Actions spend proportional to risk.

## 1. Work and integration

GitHub Issues are the durable work-item source. A PR is the smallest coherent integration unit, not necessarily one microscopic slice.

Prefer:

`Issue → SPEC only if needed → thin local slices → draft PR while iterating → ready PR → PR Gate → auto-merge/queue → release`

Do not make PRs artificially large to save CI minutes. Save minutes by verifying slices locally, pushing less often, canceling superseded runs, caching, and reserving expensive assurance for changes that justify it.

Name short-lived branches `<type>/<issue-number>-<short-description>` so each branch traces directly to its Issue (for example `feat/42-optional-sections`, `fix/81-router-timeout`, `chore/105-ci-cache`).

## 2. Required PR Gate

Every managed repository exposes one stable required status context named **`PR Gate`**.

Draft pushes should not consume the full required gate. If a workflow emits a skipped job for draft events, that skipped job must use a different check name; a skipped job named `PR Gate` must never be allowed to satisfy the required context.

`PR Gate` runs the cheapest independent evidence sufficient to block a bad merge for that repository. It should normally finish in about 10 minutes or less and may contain or aggregate repo-specific build/type/lint, unit/property/regression, changed-file/architecture, critical integration/contract/acceptance, and lightweight security/dependency evidence.

Do not require every available test category on every change.

Bind the required `PR Gate` context to the GitHub Actions App integration, not only to a status name.

CODEOWNERS should map the required workflow plus the small repo-specific entrypoints that determine what it executes (for example test scripts/config, coverage-gate code, or locked acceptance evaluators). Do not CODEOWN all product tests merely to satisfy this rule.

For today's single-developer, user-owned repositories, CODEOWNERS is **advisory**, not a required approval gate: a pull-request author cannot approve their own PR, so requiring Code Owner approval would deadlock the normal solo workflow. R3/R4/control-plane changes instead require fresh external semantic review and are excluded from automatic merge. Once repositories move to an organization with an independent reviewer/team, enable required Code Owner review and prefer an organization-required workflow sourced from this standards repo.

Use **loose** required status checks (`strict_required_status_checks_policy: false`) by default so a PR does not rebuild merely because `main` moved. A merge queue, when available, provides the final combined-head integration check.

## 3. Expensive assurance

Keep expensive or environment-specific checks outside the universal PR Gate unless risk makes them necessary blockers: full OS/browser matrices, mutation campaigns, extended fuzzing, load/performance, broad security scans, and slow production-like E2E.

Run them through risk/path-triggered jobs, explicit escalation, main/release validation, or scheduled/manual workflows. A correctness-critical or security-critical check stays blocking even when expensive.

## 4. Actions efficiency

- Keep PRs draft during active iteration; run fast local evidence per slice.
- Cancel superseded ready-PR runs with workflow concurrency.
- Prefer one setup/install per required lane when extra parallel jobs mostly duplicate setup cost.
- Cache dependencies when safe/useful.
- Avoid redundant push+PR execution for the same evidence.
- Remove/demote expensive checks that rarely change a decision.

Optimize for **fast trustworthy feedback per compute-minute**, not minimum Actions usage in isolation.

## 5. Merge and protection defaults

For the default branch:

- require a PR
- require GitHub-Actions-produced `PR Gate`
- require resolution of review threads
- require 0 human approvals by default for routine work
- disallow force-push and branch deletion
- use squash merge as the normal merge method
- allow auto-merge
- automatically delete merged head branches
- define no silent bypass actors

R0–R2 may use risk-aware auto-merge after the PR is ready. R3/R4 and control-plane changes require a fresh independent semantic review after the final substantive push and must not auto-merge while a material finding is unresolved.

Today, repo-local workflow files are still editable by a control-plane PR, so this R3 review requirement is an extra trust boundary rather than a claim that the local evaluator is immutable. Organization-required workflows are the stronger future boundary.

## 6. Merge queue

Use a merge queue when GitHub supports it and concurrent agent PR volume justifies it. Required-check workflows must trigger on `merge_group` or queued PRs can deadlock.

Default queue posture:

- squash merge
- `HEADGREEN` grouping
- build concurrency 3
- merge groups up to 5 PRs
- 1-minute maximum grouping wait
- 10-minute required-check response timeout

User-owned repositories remain queue-ready but cannot enable the queue until moved to a supported organization.

## 7. Release

Keep low-risk releases simple: `merge → deploy → smoke`.

For higher-risk releases, build once, identify the immutable artifact/commit, promote that same artifact, use staging/canary/feature flags only when they materially reduce risk, verify after deployment, and preserve rollback/recovery.

## 8. Shared control plane

`policy/github-defaults.json` is the machine-readable portfolio default.

- `scripts/apply-github-standard.ps1` applies repository settings, Actions, labels, and default-branch rules.
- `scripts/auto-merge.ps1` is the risk-aware R0–R2 happy path and refuses R3/R4/control-plane PRs.
- `scripts/doctor.ps1 -Remote` verifies effective remote policy and exits nonzero on drift.

Prefer centrally maintained policy and stable check naming; keep stack-specific test commands inside each product repo.
