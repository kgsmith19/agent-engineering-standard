# PR State-Machine Exhaustiveness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close every material GitHub PR event/state gap that can leave stale authority, stale evidence, a silent hang, or a non-independent machine review.

**Architecture:** Keep GitHub as the durable state/evidence plane and extend the existing thin PowerShell policy/state machine. Add pure decision helpers for conclusion/reviewer combinations, minimal event-trigger expansion, and bounded recovery rather than new services or agents.

**Tech Stack:** GitHub Actions YAML, PowerShell 7, GitHub CLI/API, existing repository tests. No new dependencies.

## Global Constraints
- Issue #43 and `specs/active/SPEC-0043-state-machine-exhaustiveness.md` are the correctness contract.
- Tests fail first for each behavior change.
- No new service/dependency.
- Semantic review remains bounded and does not run on ordinary pushes/draft chatter.
- Unknown authority states fail closed.
- Keep permissions least-privileged per job.

---

### Task 1: Event coverage

**Files:**
- Modify: `tests/standard-hygiene.tests.ps1`
- Modify: `templates/PR_AUTOMATION.yml`
- Modify: `templates/AI_REVIEW.yml`
- Modify: `templates/PR_GATE.yml`
- Modify: `.github/workflows/pr-automation.yml`
- Modify: `.github/workflows/ai-review.yml`

**Produces:** Immediate reevaluation for material PR/review/comment mutations and fresh deterministic evidence on PR edits.

- [ ] Add failing assertions for PR `edited`, auto-merge enable/disable, review `edited`, inline comment lifecycle, issue-comment deletion, and PR Gate `edited`.
- [ ] Run `PR Gate`; confirm standard-hygiene fails on missing event coverage.
- [ ] Add only the required event types/jobs.
- [ ] Run `PR Gate`; confirm green.

### Task 2: Exhaustive gate conclusions

**Files:**
- Modify: `tests/review-policy.tests.ps1`
- Modify: `scripts/lib/review-policy.ps1`
- Modify: `scripts/pr-orchestrator.ps1`
- Modify: `policy/github-defaults.json`
- Modify: `templates/PR_AUTOMATION.yml`
- Modify: `.github/workflows/pr-automation.yml`

**Produces:** `Get-GateConclusionDecision` and one bounded rerun for current-head `cancelled`/`stale` runs.

- [ ] Add table-driven failing tests for `success`, `failure`, `timed_out`, `startup_failure`, `action_required`, `skipped`, `cancelled`, `stale`, `neutral`, and unknown.
- [ ] Confirm RED.
- [ ] Implement pure decision helper.
- [ ] Add one trusted `auto-rerun:gate:<head>:<run-id>` attempt using Actions write only in `gate-result`; repeat cancellation/stale blocks.
- [ ] Confirm GREEN and permission assertions.

### Task 3: Reviewer independence across the full PR

**Files:**
- Modify: `tests/review-policy.tests.ps1`
- Modify: `scripts/lib/review-policy.ps1`
- Modify: `scripts/evaluate-ai-review.ps1`
- Modify: `scripts/request-machine-review.ps1`

**Produces:** Reviewer eligibility based on every recognized author/committer across all current PR commits.

- [ ] Add failing actor-set tests: none, Codex only, Copilot only, both, and earlier-provider-plus-human-latest.
- [ ] Confirm RED for earlier-provider-plus-human-latest.
- [ ] Implement actor-set policy helper and paginate PR commits in evaluator/requester.
- [ ] Confirm GREEN.

### Task 4: External-fork boundary and authoritative matrix

**Files:**
- Modify: `tests/standard-hygiene.tests.ps1`
- Modify: `scripts/pr-orchestrator.ps1`
- Modify: `scripts/auto-merge.ps1`
- Modify: `docs/AUTONOMOUS-PR-STATE-MACHINE.md`
- Modify: `scripts/upgrade-repos.ps1`

**Produces:** Fork PR fail-closed behavior, documented ignored events, and rollout support for PR Gate `edited` triggers.

- [ ] Add failing assertions for cross-repository block and rollout PR Gate `edited` normalization.
- [ ] Confirm RED.
- [ ] Block cross-repository PRs before unattended arming and in runtime validator.
- [ ] Update upgrade logic so existing managed PR gates gain `edited` without changing test commands.
- [ ] Update decision matrix with handled and intentionally ignored GitHub events.
- [ ] Run full `PR Gate` and local doctor.
- [ ] Request a fresh exact-head independent machine review.