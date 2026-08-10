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
→ `PR Gate`
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

## Machine review (advisory, evaluated not obeyed)

The deterministic gate is the only merge authority. Every gated head also gets an exact-head `Advisory: AI Review` conclusion; arming auto-merge requires that evaluation to exist with current policy-version evidence, and refuses only a `failure` carrying a structured threat verdict — `BLOCK: <CLASS> <file:line> — <exploit precondition>` with CLASS `T1-INFRA-DELETION` / `T2-BACKDOOR` / `T3-HARDCODED-SECRET` / `T4-CRITICAL-VULN`. All P0–P2 prose findings are advisory and collect in one follow-up Issue per PR (ADR 0003).

Codex is currently the sole connected reviewer. Copilot's repository access is revoked; Copilot lanes in the scripts are retained but historical, pending an explicit reconnection decision.

## Existing portfolio setup

After the approved standard commit is on `main`:

```powershell
pwsh -NoProfile -File .\scripts\upgrade-repos.ps1 -StandardSha <full-merged-sha>
pwsh -NoProfile -File .\scripts\setup-portfolio.ps1
```

`setup-portfolio.ps1` applies settings, Actions defaults, labels, and the one canonical ruleset, then runs `doctor.ps1 -Remote`. Do not claim readiness until it reports `REMOTE: READY`. The same lane runs CI-natively via the `Ops: Portfolio Bootstrap` workflow (manual dispatch + weekly), which fails closed until `AUTOMATION_TOKEN` is provisioned.

The Copilot workflow-approval note that used to live here is moot while Copilot's repository access is revoked; it returns to scope only with an explicit reconnection.

## New repository

```powershell
pwsh -NoProfile -File .\scripts\bootstrap-repo.ps1 -Name my-app
```

Bootstrap creates the lean repository contract, the exact-SHA-pinned `Advisory: AI Review` and five per-event `Orchestrator:` callers, a bootstrap `PR Gate`, settings/ruleset, and one Issue to replace the bootstrap gate with the repository's real stack-specific checks.

## Core commands

```powershell
# Verify local structure and PowerShell syntax.
pwsh -NoProfile -File .\scripts\doctor.ps1

# Verify all managed repositories and live settings.
pwsh -NoProfile -File .\scripts\doctor.ps1 -Remote

# Request one exact-head machine review manually when debugging (codex only while Copilot access is revoked).
pwsh -NoProfile -File .\scripts\request-machine-review.ps1 -Repo kgsmith19/my-app -Pr 12

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
- deterministic gate `PR Gate` as the sole merge authority (the only check-producing status on the PR besides `Advisory: AI Review`), and machine review stays advisory-only per ADR 0002
- zero required human approvals
- no native `CODEOWNERS`
- `kgsmith19` forbidden from requested-reviewer state
- stale reviews dismissed after a push
- squash-only auto-merge
- automatic branch deletion
- no ruleset bypass actors
- one low-frequency watchdog plus event-driven recovery

Copilot cloud agent could repair an existing non-Copilot PR when connected; with its repository access revoked, those repair lanes are dormant. Copilot-owned PRs remain blocked from the unattended lane because GitHub requires them to be reviewed and merged by a human.

R0–R2 may auto-merge after a current-head gate success with an existing advisory evaluation. R3 waits for the review lane or a human; R4 and self-modifying control-plane changes retain explicitly justified authority gates — Kyle is tagged, never assigned as reviewer.

## Shared versus repository-specific truth

Central policy, orchestration, review evaluation, bootstrap, rollout, and doctor logic live here. Product repositories keep their own PRD, specs, ADRs, source, tests, deployment, and stack-specific gate commands.

Thin product workflows pin this repository by full SHA. They never follow moving `@main`.
