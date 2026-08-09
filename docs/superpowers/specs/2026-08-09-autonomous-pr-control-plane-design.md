# Autonomous PR Control Plane Design

## Goal

Make ordinary repository work flow from agent implementation to merge without requiring Kyle to remember commands, request reviewers, resolve routine CI/review failures, or click merge, while keeping model/Actions spend bounded and preserving explicit authority gates only where automation cannot safely decide.

## Canonical PR state machine

1. **Implement** — one Issue/slice, isolated branch/worktree.
2. **Draft PR** — implementation may continue; no human reviewers; no AI-review spend; cheap deterministic checks may run.
3. **Ready** — agent marks the PR ready when its local slice verification is complete.
4. **Arm auto-merge** — automation validates live repo/ruleset state and arms squash auto-merge. Draft/R4/blocked/control-plane PRs are not armed.
5. **PR Gate** — repo-specific deterministic build/test/security evidence runs on the current head.
6. **If PR Gate fails** — classify root cause and invoke the bounded fix lane. Same-cause retry budget: 3. Spec/policy conflicts stop and record a blocker rather than weakening the gate.
7. **If PR Gate passes** — request the cheapest mechanically independent AI reviewer. Do not request a human.
8. **AI Review** — exact-head semantic evaluation. One pass covers correctness/security, product/ROI, systems/operations, and strict leanness.
9. **If AI Review finds material defects** — invoke the bounded fix lane, push substantive fixes, rerun PR Gate, then perform one fresh exact-head re-review.
10. **If both gates pass** — GitHub auto-merge completes the squash merge once review threads and all required ruleset conditions are satisfied.
11. **Watchdog** — periodically repairs orchestration stalls: ready/no auto-merge, green PR Gate/no reviewer request, stale exact-head review, conflict, or failed automation delivery. It never weakens gates.

## Draft policy

Keep drafts. GitHub does not merge draft PRs. Draft is the low-cost implementation state.

- No AI review while draft.
- No auto-merge while draft.
- Cheap deterministic validation may run; expensive repo-specific checks may defer until Ready.
- Agent, not a human, marks Ready after local verification.
- A stale-draft watchdog may surface/repair abandoned machine work without requesting Kyle as a reviewer.

## Human-review policy

Default required human approvals: **0**.

Native CODEOWNERS is removed from personal repos because GitHub automatically requests code owners as reviewers when matching PRs become Ready. Ownership metadata needed by agents lives in the standard/project metadata instead.

A human gate is allowed only when all four fields exist:

1. concrete failure class prevented
2. why automation cannot safely decide today
3. decision/authority owner
4. measurable gate-removal condition

R4 authority and the self-modifying control plane are current justified gates. Technical review itself remains automated.

## AI review routing and budget

- Deterministic PR Gate always precedes LLM review spend.
- Reviewer must be a different agent/session from implementation.
- Prefer Codex where independent and connected; use Copilot when Codex implemented the change or as one bounded fallback.
- Ambiguous provenance may require two independent machine reviewers rather than trusting editable PR prose.
- No review of drafts and no default review-on-every-push policy.
- Maximum normal semantic passes: initial + one post-fix re-review.
- Copilot automatic review is not the universal default because its review model is not user-selectable and code review consumes both AI credits and Actions minutes.

## Shared vs repository-specific configuration

### Central in agent-engineering-standard

- reusable AI Review evaluator
- reusable AI-review requester
- reusable safe auto-merge armer
- shared PR automation orchestration
- branch/worktree cleanup
- rollout/bootstrap/upgrade scripts
- policy, risk/manual-gate rules, reviewer budget
- remote doctor

### Thin files in every product repo

- `.github/workflows/ai-review.yml` caller
- `.github/workflows/pr-automation.yml` caller
- `.agent/standard.lock`
- repo-specific `PR Gate` workflow
- repo-specific AGENTS/product truth

The product caller workflows should reference an exact shared-standard SHA. `upgrade-repos.ps1` fans out one explicit upgrade PR per repository when the standard changes, avoiding silent runtime drift while preserving one source implementation.

## Existing-repo rollout

After the standard PR merges:

1. `upgrade-repos.ps1` installs/updates the thin AI Review and PR Automation callers and bumps the exact standard pin in all seven product repos.
2. Product repo PR Gates are preserved; only their workflow name/trigger contract is normalized when necessary.
3. `setup-portfolio.ps1` applies repo settings/rulesets after required caller workflows exist.
4. `doctor.ps1 -Remote` must report READY for every managed repo.
5. A disposable low-risk canary PR proves: draft does not merge → Ready arms auto-merge → PR Gate blocks → AI review is automatically requested → both green → GitHub squash-merges without a human action.

## New-repo flow

`bootstrap-repo.ps1` creates the repo and installs:

- standard pin
- lean AGENTS/PRD scaffolding
- bootstrap PR Gate
- AI Review caller
- PR Automation caller
- Dependabot baseline
- scratch/worktree ignore

It then applies GitHub settings/ruleset and creates one Issue to replace the bootstrap gate with the repo's real stack-specific deterministic gate before product code is added.

## GitHub settings

Personal-repo defaults:

- Issues on
- Actions on
- PR required for main
- required status contexts: PR Gate + AI Review
- required human approvals: 0
- native Code Owner review: off; CODEOWNERS removed to avoid automatic Kyle review requests
- review-thread resolution required
- auto-merge on
- update branch on
- squash only
- merge commits off
- rebase off
- delete branch after merge on
- deletion/force-push protections on
- no bypass actors
- loose required status policy unless evidence justifies strict/up-to-date rebuilding

## Failure/stall handling

Automation must detect and handle, without silently calling a human reviewer:

- draft never marked Ready
- PR Gate failure
- AI reviewer unavailable/budget exhausted
- AI Review findings
- stale AI Review after push
- merge conflict
- auto-merge not armed
- missing caller workflow
- wrong workflow name
- ruleset/repo setting drift
- unresolved review threads
- Actions outage/infrastructure failure

Every automatic retry is bounded. When machine recovery is exhausted, the PR is labeled/recorded as blocked with an exact cause. Kyle is not added as a reviewer. Only a genuinely justified authority gate may require Kyle's decision.

## Cost/latency measurement

Record per PR:

- deterministic Actions minutes
- semantic-review provider/pass count
- time from Ready → PR Gate green
- time from PR Gate green → AI Review green
- AI findings accepted vs false positives
- fix passes caused by AI review
- escaped defects/reverts
- human interventions

After enough PRs, keep AI Review as a universal required gate only if prevented defects/rework justify its cost/latency; otherwise narrow it by risk/path using measured evidence rather than intuition.
