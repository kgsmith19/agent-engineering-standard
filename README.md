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
→ Ready PR (`draft: false`)
→ `Gate: Deterministic CI`
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

## Merge authority

The deterministic `PR Gate` is the only merge authority (ADR 0004). Inline AI code review was removed from the blocking merge path entirely — `scripts/codex-review.ps1` remains available as an optional local manual second opinion, never a CI check.

## Existing portfolio setup

After the approved standard commit is on `main`:

```powershell
pwsh -NoProfile -File .\scripts\upgrade-repos.ps1 -StandardSha <full-merged-sha>
pwsh -NoProfile -File .\scripts\setup-portfolio.ps1
```

`setup-portfolio.ps1` applies settings, Actions defaults, labels, and the one canonical ruleset, then runs `doctor.ps1 -Remote`. Do not claim readiness until it reports `REMOTE: READY`. The same lane runs CI-natively via the `Ops: Portfolio Bootstrap` workflow (manual dispatch + weekly), which fails closed until `AUTOMATION_TOKEN` is provisioned.

## New repository

```powershell
pwsh -NoProfile -File .\scripts\bootstrap-repo.ps1 -Name my-app
```

Bootstrap creates the lean repository contract, the exact-SHA-pinned `Orchestrator:` callers, a bootstrap `Gate: Deterministic CI` (with the transitional `PR Gate` bridge job), settings/ruleset, and one Issue to replace the bootstrap gate with the repository's real stack-specific checks.

## Core commands

```powershell
# Verify local structure and PowerShell syntax.
pwsh -NoProfile -File .\scripts\doctor.ps1

# Verify all managed repositories and live settings.
pwsh -NoProfile -File .\scripts\doctor.ps1 -Remote

# Validate policy and arm GitHub auto-merge.
pwsh -NoProfile -File .\scripts\auto-merge.ps1 -Repo kgsmith19/my-app -Pr 12 -Risk R2

# Dry-run conservative branch/worktree cleanup.
pwsh -NoProfile -File .\scripts\prune-portfolio.ps1
```

## Default GitHub behavior

Managed repositories use:

- GitHub Issues as durable work items
- Ready PRs at creation; API/SDK/connector calls set `draft: false`, and `gh pr create` omits `--draft`
- fail-closed workflow enforcement if a PR is ever opened or converted to draft
- deterministic gate `Gate: Deterministic CI` as the sole merge authority; the ruleset-required context is migrating from `PR Gate` via a fail-closed bridge job ([runbook](docs/notes/2026-08-09-context-rename-runbook.md))
- zero required human approvals
- no native `CODEOWNERS`
- `kgsmith19` forbidden from requested-reviewer state
- stale reviews dismissed after a push
- squash-only auto-merge
- automatic branch deletion
- no ruleset bypass actors
- one low-frequency watchdog as the general missed-webhook/CI-gate convergence net

Copilot-owned PRs remain blocked from the unattended lane because GitHub requires them to be reviewed and merged by a human; Copilot may still repair an existing non-Copilot PR's CI failures or merge conflicts when repair dispatch is enabled (`pr_automation.repair_dispatch_enabled`, off by default).

R0–R2 may auto-merge after a current-head gate success. R4 and self-modifying control-plane changes retain explicitly justified authority gates — Kyle is tagged, never assigned as reviewer.

## Shared versus repository-specific truth

Central policy, orchestration, review evaluation, bootstrap, rollout, and doctor logic live here. Product repositories keep their own PRD, specs, ADRs, source, tests, deployment, and stack-specific gate commands.

Thin product workflows pin this repository by full SHA. They never follow moving `@main`.
