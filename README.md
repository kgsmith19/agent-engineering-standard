# Lean Agent Engineering Standard

This repository is the shared engineering control plane for Kyle's agent-driven software projects.

## Goal

Maximize **accepted useful outcomes per human active minute and total cost** while protecting correctness, security, reliability, recoverability, and maintainability.

## Lifecycle

Idea
→ Shape / Research
→ Outcome / Bet
→ Product Truth
→ GitHub Issue
→ Spec only if needed
→ Thin Slice
→ RED → Minimum GREEN
→ Local Verification
→ Draft PR
→ `status:ready`
→ `PR Gate`
→ exact-head `AI Review`
→ automatic squash merge
→ Release / Runtime Proof
→ Observe / Learn

## Governing rule

Every artifact, gate, model call, and CI run must reduce meaningful uncertainty, prevent a real failure, or provide useful evidence. Otherwise remove it.

## Shared standards

- [Lifecycle](LIFECYCLE.md)
- [Agent Rules](AGENT_RULES.md)
- [Quality Rules](QUALITY_RULES.md)
- [Security, Risk and Autonomy](SECURITY_RISK_AUTONOMY.md)
- [Delivery and GitHub](DELIVERY_GITHUB.md)
- [Evidence and Learning](EVIDENCE_LEARNING.md)
- [Autonomous PR state machine](docs/AUTONOMOUS-PR-STATE-MACHINE.md)

## Existing portfolio setup

After the approved standard commit is on `main`:

```powershell
pwsh -NoProfile -File .\scripts\upgrade-repos.ps1 -StandardSha <full-merged-sha>
pwsh -NoProfile -File .\scripts\setup-portfolio.ps1
```

`setup-portfolio.ps1` applies settings, Actions defaults, labels, and the one canonical ruleset, then runs `doctor.ps1 -Remote`. Do not claim readiness until it reports `REMOTE: READY`.

GitHub currently exposes the Copilot workflow-approval setting as read-only through REST. In each repository, disable **Require approval for workflows** in Copilot coding-agent settings. The remote doctor fails while it is enabled.

## New repository

```powershell
pwsh -NoProfile -File .\scripts\bootstrap-repo.ps1 -Name my-app
```

Bootstrap creates the lean repository contract, exact-SHA-pinned `AI Review` and `PR Automation` callers, a bootstrap `PR Gate`, settings/ruleset, and one Issue to replace the bootstrap gate with the repository's real stack-specific checks.

## Core commands

```powershell
# Verify local structure and PowerShell syntax.
pwsh -NoProfile -File .\scripts\doctor.ps1

# Verify all managed repositories and live settings.
pwsh -NoProfile -File .\scripts\doctor.ps1 -Remote

# Request one exact-head machine review manually when debugging.
pwsh -NoProfile -File .\scripts\request-machine-review.ps1 -Repo kgsmith19/my-app -Pr 12

# Validate policy and arm GitHub auto-merge.
pwsh -NoProfile -File .\scripts\auto-merge.ps1 -Repo kgsmith19/my-app -Pr 12 -Risk R2

# Dry-run conservative branch/worktree cleanup.
pwsh -NoProfile -File .\scripts\prune-portfolio.ps1
```

## Default GitHub behavior

Managed repositories use:

- GitHub Issues as durable work items
- draft PRs during implementation
- `status:ready` for automatic promotion to Ready
- exact workflow and status names `PR Gate` and `AI Review`
- zero required human approvals
- no native `CODEOWNERS`
- `kgsmith19` forbidden from requested-reviewer state
- required review-thread resolution
- stale reviews dismissed after a push
- squash-only auto-merge
- automatic branch deletion
- no ruleset bypass actors
- one low-frequency watchdog plus event-driven recovery

Copilot cloud agent may repair an existing non-Copilot PR. Copilot-owned PRs are blocked from the unattended lane because GitHub requires them to be reviewed and merged by a human.

R0–R3 may auto-merge after current-head `PR Gate` + `AI Review` and thread resolution. R4 and self-modifying control-plane changes retain explicitly justified authority gates; Kyle is tagged, never assigned as reviewer.

## Shared versus repository-specific truth

Central policy, orchestration, review evaluation, bootstrap, rollout, and doctor logic live here. Product repositories keep their own PRD, specs, ADRs, source, tests, deployment, and stack-specific `PR Gate` commands.

Thin product workflows pin this repository by full SHA. They never follow moving `@main`.
