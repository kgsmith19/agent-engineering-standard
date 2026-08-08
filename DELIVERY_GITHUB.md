# Delivery & GitHub

## Goal

Make GitHub the protected integration/enforcement plane while keeping feedback fast and Actions spend proportional to risk.

## 1. Work and integration

GitHub Issues are the durable work-item source. A PR is the smallest coherent integration unit, not necessarily one microscopic slice.

Prefer:

`Issue → SPEC only if needed → thin local slices → coherent PR → PR Gate → auto-merge/queue → release`

Do not make PRs artificially large to save CI minutes. Save minutes by verifying slices locally, pushing less often, canceling superseded runs, caching, and reserving expensive assurance for the changes that justify it.

## 2. Required PR Gate

Every managed repository exposes one stable required status context named **`PR Gate`**.

`PR Gate` runs the cheapest independent evidence sufficient to block a bad merge for that repository. It should normally finish in about 10 minutes or less and may contain or aggregate repo-specific checks such as:

- build/types/lint
- unit/property/regression tests
- changed-file or architecture gates
- critical integration/contract/acceptance tests
- lightweight security/dependency checks

Do not require every available test category on every PR.

The default required-status policy is **loose** (`strict_required_status_checks_policy: false`): do not force a branch update and duplicate CI merely because `main` moved. A merge queue, when available, provides the final combined-head integration check instead.

## 3. Expensive assurance

Keep expensive or environment-specific checks out of the universal PR Gate unless the change's risk makes them necessary blockers.

Examples:

- full OS/browser matrices
- mutation campaigns
- extended fuzzing
- load/performance suites
- broad security scans
- slow production-like E2E

Run them through path/risk-triggered jobs, explicit pre-merge escalation, main/release validation, or scheduled/manual workflows as appropriate.

A correctness-critical or security-critical check stays blocking even when expensive.

## 4. Actions efficiency

- Cancel superseded PR runs with workflow concurrency.
- Prefer one setup/install per required lane over duplicate jobs when parallelism does not materially shorten feedback.
- Cache dependencies when it is safe and useful.
- Avoid redundant push+PR execution for the same evidence where repo behavior permits it.
- Track expensive checks that rarely change a decision and remove/demote them when evidence shows low value.

Optimize for **fast trustworthy feedback per compute-minute**, not minimum Actions usage in isolation.

## 5. Merge and protection defaults

For the default branch:

- require a PR
- require `PR Gate`
- require 0 human approvals by default for routine work
- disallow force-push and branch deletion
- use squash merge as the normal merge method
- enable auto-merge
- automatically delete merged head branches
- no silent bypass by the implementing agent

R3/R4 work and control-plane changes still require the independent review/authority defined by the security/risk standard even though the repository-wide approval count is zero.

## 6. Merge queue

Use a merge queue when GitHub supports it and concurrent agent PR volume justifies it.

All queue-enabled workflows that provide required checks must also trigger on `merge_group`; otherwise queued PRs can deadlock waiting for checks that never run.

Default queue posture:

- squash merge
- `HEADGREEN` grouping to minimize redundant builds while testing the combined queue head
- build concurrency 3
- merge groups up to 5 PRs
- 1-minute maximum wait to opportunistically group ready PRs
- 10-minute required-check response timeout

GitHub currently limits merge queues to organization-owned repositories (public organization repositories, or private organization repositories on Enterprise Cloud). User-owned repositories remain queue-ready but cannot enable the queue until moved to a supported organization.

## 7. Release

Keep low-risk releases simple:

`merge → deploy → smoke`

For higher-risk releases:

- build once
- identify the immutable artifact/commit
- promote the same artifact
- use staging/canary/feature flags when they meaningfully reduce risk
- verify after deployment
- preserve rollback/recovery

## 8. Shared control plane

`policy/github-defaults.json` is the machine-readable portfolio default. `scripts/apply-github-standard.ps1` applies repository settings and default-branch rules through GitHub CLI admin access.

Prefer centrally maintained policy and stable check naming; keep stack-specific test commands inside each product repo.
