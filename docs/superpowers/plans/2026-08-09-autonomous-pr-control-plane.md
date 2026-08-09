# Autonomous PR Control Plane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every managed repo follow the same automatic draft → deterministic gate → machine review → fix/re-review → squash auto-merge lifecycle with zero default human review requests.

**Architecture:** Keep repo-specific deterministic `PR Gate` logic local to each product repo. Centralize AI-review evaluation/requesting, safe auto-merge arming, rollout policy, and remote verification in `agent-engineering-standard`. Existing repos receive only tiny caller workflows plus an exact shared-standard pin; new repos receive them from bootstrap.

**Tech Stack:** GitHub Actions, GitHub rulesets, PowerShell 7, GitHub CLI/API, reusable workflows.

## Global Constraints

- Required human approval count is 0 for personal repos.
- Draft PRs never auto-merge or spend AI-review budget.
- Deterministic PR Gate runs before any paid semantic review request.
- AI reviewer must be a different agent/session from the implementer; never request Kyle as a reviewer.
- One initial semantic pass + at most one post-fix re-review.
- Auto-merge requires latest-head `PR Gate` + `AI Review` and resolved review threads.
- R4 never auto-merges.
- Control-plane changes retain their justified authority gate until enforcement is external/immutable.
- Shared reusable workflows are pinned by exact standard SHA in product repos; standard upgrades fan out through one script.
- Repo-specific test/build commands remain local and are never overwritten by the shared standard.

---

### Task 1: Canonical shared PR orchestration

**Files:**
- Create: `.github/workflows/request-review-reusable.yml`
- Create: `.github/workflows/auto-merge-reusable.yml`
- Create: `.github/workflows/pr-automation.yml`
- Create: `templates/PR_AUTOMATION.yml`
- Modify: `.github/workflows/ci.yml`
- Test: `tests/standard-hygiene.tests.ps1`

**Produces:** Ready PR auto-merge arming and post-`PR Gate` machine review request without checking out PR code in privileged workflow contexts.

- [ ] Add reusable machine-review requester.
- [ ] Add reusable safe auto-merge armer using existing `auto-merge.ps1` live-policy checks.
- [ ] Add `PR Automation` caller triggered by Ready/synchronize/labels and successful workflow named `PR Gate`.
- [ ] Standardize the standard repo deterministic workflow name to `PR Gate`.
- [ ] Test caller/reusable presence, PR Gate name contract, and PowerShell parsing.
- [ ] Run `PR Gate`; expected GREEN.

### Task 2: Remove accidental human-review path

**Files:**
- Modify: `policy/github-defaults.json`
- Modify: `scripts/apply-github-standard.ps1`
- Modify: `scripts/doctor.ps1`
- Modify: `templates/CODEOWNERS` or replace with agent-only ownership metadata
- Modify: `AGENT_RULES.md`, `templates/AGENTS.md`
- Test: `tests/standard-hygiene.tests.ps1`

**Produces:** Personal repos cannot automatically request Kyle through CODEOWNERS and required approvals remain 0.

- [ ] Remove native CODEOWNERS as a required personal-repo artifact.
- [ ] Preserve control-plane ownership metadata outside GitHub reviewer assignment.
- [ ] Make doctor fail if required human approvals or code-owner-review requirements are nonzero/true.
- [ ] Document that machine semantic review is separate from GitHub human review requests.
- [ ] Run `PR Gate`; expected GREEN.

### Task 3: Existing-repo upgrade fan-out

**Files:**
- Modify: `scripts/upgrade-repos.ps1`
- Modify: `scripts/lib/standard-lock.ps1` only if required for exact caller SHA rewriting
- Test: `tests/standard-lock.tests.ps1`, `tests/standard-hygiene.tests.ps1`

**Produces:** One command upgrades all managed product repos without overwriting repo-specific PR Gate logic.

- [ ] Update exact standard pin.
- [ ] Install/update `.github/workflows/ai-review.yml` thin caller.
- [ ] Install/update `.github/workflows/pr-automation.yml` thin caller.
- [ ] Rewrite caller `uses:` refs to the exact `StandardSha`.
- [ ] Never overwrite the product repo's existing deterministic PR Gate workflow.
- [ ] Open one reviewable upgrade PR per changed repo.
- [ ] Test all current lock schemas and caller SHA rewrite behavior.

### Task 4: New-repo bootstrap

**Files:**
- Modify: `scripts/bootstrap-repo.ps1`
- Modify: `templates/AI_REVIEW.yml`
- Modify: `templates/PR_AUTOMATION.yml`
- Test: `tests/standard-hygiene.tests.ps1`

**Produces:** Every new repo starts with the same automatic control-plane callers and bootstrap PR Gate.

- [ ] Install AI Review + PR Automation callers.
- [ ] Pin caller reusable workflows to the exact bootstrap standard SHA.
- [ ] Preserve/append `.gitignore` safely.
- [ ] Install only generic Dependabot defaults.
- [ ] Record `PR Gate`, `AI Review`, and `PR Automation` contracts in `.agent/project.yaml`.

### Task 5: Remote readiness doctor

**Files:**
- Modify: `scripts/doctor.ps1`

**Produces:** One objective `READY` result per repo.

- [ ] Verify repo auto-merge/update-branch/squash-only settings.
- [ ] Verify active workflow named `PR Gate`.
- [ ] Verify active `ai-review.yml` and `pr-automation.yml`.
- [ ] Verify ruleset requires `PR Gate` + `AI Review`, 0 human approvals, resolved threads, no bypass actors, deletion/non-fast-forward protection.
- [ ] Verify stale legacy required checks are absent.
- [ ] Fail closed with exact drift list.

### Task 6: Normalize seven product PR Gate triggers

**Repos:** `agentic-command-center`, `agentic-command-center-ui`, `prompt-organizer`, `toolbelt`, `lifeos`, `lifeos-ui`, `network-checker`

**Produces:** Every repo emits a stable deterministic workflow named `PR Gate` on PR events while preserving stack-specific commands.

- [ ] Inspect existing workflow names/triggers in each repo.
- [ ] Rename workflow-level `name:` to `PR Gate` where needed without renaming job/check semantics unnecessarily.
- [ ] Re-enable PR triggers where disabled, especially ACC, while preserving path/draft cost controls.
- [ ] Ensure drafts never auto-merge; allow cheap draft validation and final Ready verification.
- [ ] Run each repo's real gate before merge.

### Task 7: Roll out the shared callers and standard pin

**Produces:** All seven product repos use the same shared automation implementation.

- [ ] Merge the repaired standard control-plane PR.
- [ ] Run/replicate `upgrade-repos.ps1` fan-out against the merged standard SHA.
- [ ] Merge only green upgrade PRs.
- [ ] Confirm all seven have exact-SHA AI Review + PR Automation callers.

### Task 8: Apply live GitHub settings/rulesets

**Files/commands:**
- `scripts/setup-portfolio.ps1`
- `scripts/apply-github-standard.ps1`
- `scripts/doctor.ps1 -Remote`

**Produces:** Actual GitHub UI/API state matches repository policy.

- [ ] Run authenticated portfolio setup from a trusted local/admin session.
- [ ] Confirm ACC UI auto-merge/update-branch are enabled.
- [ ] Confirm all seven are squash-only with merge/rebase disabled.
- [ ] Confirm `PR Gate` + `AI Review` are required.
- [ ] Confirm human approval count 0 and native code-owner requirement off.
- [ ] Run remote doctor until every repo reports READY.

### Task 9: End-to-end canary proof

**Produces:** `AUTO-MERGE PROVEN` evidence, not an assumption.

- [ ] Create a tiny R0 canary PR in one product repo as Draft.
- [ ] Verify Draft cannot merge and causes no AI-review request.
- [ ] Mark Ready using the agent/API, not Kyle review assignment.
- [ ] Verify auto-merge becomes armed while `PR Gate`/`AI Review` are pending.
- [ ] Verify successful PR Gate automatically triggers machine reviewer request.
- [ ] If reviewer finds a defect, verify a fix push invalidates old exact-head review and requires fresh gate/re-review.
- [ ] Verify both required checks GREEN on the same head.
- [ ] Verify GitHub squash-merges automatically with zero human review/merge click.
- [ ] Record timestamps, Actions minutes, reviewer pass count, and any human intervention.

### Task 10: Stuck-state watchdog and ROI telemetry

**Files:**
- Create: shared reusable watchdog only after Tasks 1-9 prove the base lifecycle.
- Modify: policy/telemetry config as needed.

**Produces:** Routine orchestration stalls do not silently wait on Kyle.

- [ ] Detect Ready PR with auto-merge not armed.
- [ ] Detect PR Gate green with no machine review request/result.
- [ ] Detect stale review after head push.
- [ ] Detect merge conflict or unresolved machine-review findings.
- [ ] Detect exhausted retry/review budgets and label exact blocker without assigning Kyle as reviewer.
- [ ] Record Ready→gate, gate→review, review→merge latency, model passes, Actions minutes, accepted findings, false positives, reverts, and human interventions.
- [ ] Re-evaluate universal AI Review after measured portfolio evidence; narrow by risk/path only if ROI does not justify universal review.
