# Delivery & GitHub

## Goal

Make GitHub the protected integration/enforcement plane while keeping feedback fast and Actions spend proportional to risk.

## 1. Work and integration

GitHub Issues are the durable work-item source. A PR is the smallest coherent integration unit, not necessarily one microscopic slice.

Prefer:

`Issue → SPEC only if needed → thin local slices → draft PR while iterating → ready PR → PR Gate + AI Review → auto-merge/queue → release`

Do not make PRs artificially large to save CI minutes. Save minutes by verifying slices locally, pushing less often, canceling superseded runs, caching, and reserving expensive assurance for changes that justify it.

Name ordinary short-lived branches `<type>/<issue-number>-<short-description>`. Controlled agent runs use `agent/<provider>/<issue-or-work>` so review independence can be derived mechanically rather than trusted from editable PR prose.

## 2. Required integration gates

Every managed repository exposes two stable required contexts on the latest PR head:

- **`PR Gate`** — cheapest sufficient deterministic build/test/security evidence.
- **`AI Review`** — exact-head provider-specific semantic evidence required by implementation provenance.

Both contexts are bound to the GitHub Actions App. A later push creates a new SHA, so an `AI Review` success from an earlier head cannot satisfy the latest commit.

Known provider routing is deliberately cheap: ChatGPT/Codex implementations require Copilot; Claude/Copilot implementations require Codex. Ordinary/user-authored branches are ambiguous for reviewer independence and require both connected providers before unattended merge.

Draft pushes should not spend semantic-review budget. Keep active work draft, request review when coherent, and allow only the bounded response-pass budget after substantive fixes.

`PR Gate` should normally finish in about 10 minutes or less and may contain repo-specific build/type/lint, unit/property/regression, changed-file/architecture, critical integration/contract/acceptance, and lightweight security/dependency evidence. Do not require every available test category on every change.

`AI Review` derives agent provenance from controlled provider branch/author metadata. It never trusts editable PR prose to self-attest an LLM provider. Review-thread resolution remains separately required so material inline findings cannot be ignored.

For today's single-developer, user-owned repositories, CODEOWNERS is advisory and human approval count is 0. Required Code Owner review would deadlock a solo personal-repo workflow. Organization-owned repos may harden CODEOWNERS through the shared policy.

Use loose required status checks (`strict_required_status_checks_policy: false`) by default so a PR does not rebuild merely because `main` moved. A merge queue, when available, provides final combined-head integration checking.

## 3. Expensive assurance

Keep expensive/environment-specific checks outside the universal gates unless risk makes them necessary blockers: full OS/browser matrices, mutation campaigns, extended fuzzing, load/performance, broad security scans, and slow production-like E2E.

Run them through risk/path triggers, explicit escalation, main/release validation, or scheduled/manual workflows. A correctness/security-critical check stays blocking even when expensive.

## 4. Actions and model efficiency

- Keep PRs draft during active iteration.
- Cancel superseded deterministic and `AI Review` evaluator runs per PR.
- Prefer one setup/install per required lane when parallel jobs mostly duplicate setup cost.
- Cache dependencies when useful/safe.
- Avoid redundant push+PR execution.
- Run deterministic checks before semantic LLM review.
- Prefer one batched semantic review over several specialist calls.
- Codex is the cheap default where it is cross-provider; Copilot is used when it is the required cross-provider reviewer, not as an every-push tax.
- Review budgets count actual semantic responses; exact-head request markers prevent duplicate triggers.
- Remove/demote checks or model calls that rarely change a decision.

Optimize for **fast trustworthy feedback per human minute, compute-minute, and model cost**.

## 5. Merge and protection defaults

For the default branch:

- require a PR
- require GitHub-Actions-produced `PR Gate`
- require GitHub-Actions-produced exact-head `AI Review`
- require resolution of review threads
- require 0 human approvals by default on personal repos
- disallow force-push and branch deletion
- squash only
- allow auto-merge
- automatically delete merged head branches
- no silent bypass actors

R0–R3 may use auto-merge when both required gates are green and no justified authority gate applies. R4 never auto-merges.

Control-plane changes remain manually merged **only** while the PR can modify the evaluator/merge authority judging itself. Remove that gate once governing enforcement lives in an immutable external or organization-required workflow the PR cannot edit.

## 6. Merge queue

Use a merge queue when GitHub supports it and concurrent agent PR volume justifies it. Required-check workflows must support `merge_group` before enabling the queue. User-owned repositories remain queue-ready but do not enable it until the exact-head semantic-review behavior for merge groups is explicitly implemented and verified.

## 7. Release

Keep low-risk releases simple: `merge → deploy → smoke`.

For higher-risk releases, build once, identify the immutable artifact/commit, promote that same artifact, use staging/canary/feature flags only when they materially reduce risk, verify after deployment, and preserve rollback/recovery.

## 8. Shared control plane

`policy/github-defaults.json` is the machine-readable portfolio policy.

- `scripts/apply-github-standard.ps1` applies repository settings, labels, Actions, and default-branch rules.
- `.github/workflows/ai-review-reusable.yml` is the shared exact-head semantic-review evaluator; product repos use the thin caller template.
- `scripts/request-independent-review.ps1` routes the next missing required provider within the configured response budget.
- `scripts/auto-merge.ps1` validates the live integration plane and then arms GitHub auto-merge; it does not substitute its own call-time semantic judgment for the required `AI Review` context.
- `scripts/doctor.ps1 -Remote` verifies effective remote policy, including that the AI Review workflow itself is active, and exits nonzero on drift.

Prefer centrally maintained policy and stable check naming; keep stack-specific deterministic commands inside each product repo.
