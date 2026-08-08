# Lean Agent Engineering Standard

This repo is the authoritative shared engineering standard for Kyle's agent-driven software projects.

## Goal

Maximize **accepted useful outcomes per human active minute and total cost** while protecting correctness, security, reliability, recoverability, and maintainability.

## Lifecycle

Idea
→ Shape / Research
→ Outcome / Bet
→ Product Truth
→ GitHub Issue
→ Spec if needed
→ Thin Slice
→ Evidence
→ Risk / Authority
→ RED → Minimum GREEN
→ Verification
→ PR / PR Gate
→ Auto-merge / merge queue when supported
→ Release / Runtime Proof
→ Observe / Learn
→ next idea or slice

## Governing rule

Every artifact, rule, gate, and CI run must reduce meaningful uncertainty, prevent a real/high-consequence failure, or provide useful independent evidence. Otherwise remove it.

## Shared standards

- [Lifecycle](LIFECYCLE.md)
- [Agent Rules](AGENT_RULES.md)
- [Quality Rules](QUALITY_RULES.md)
- [Security, Risk & Autonomy](SECURITY_RISK_AUTONOMY.md)
- [Delivery & GitHub](DELIVERY_GITHUB.md)
- [Evidence & Learning](EVIDENCE_LEARNING.md)

`AGENTS.md` is the operating map for agents working on this control-plane repo.

## One-time portfolio setup

After cloning this repo and authenticating GitHub CLI:

```powershell
pwsh -File scripts/setup-portfolio.ps1
```

That applies repo settings/rules, enables Actions, creates the risk/status labels, syncs the optional `Agentic Portfolio` GitHub Project, and runs the remote doctor. If GitHub CLI lacks Project scope, run `gh auth refresh -s project` once and rerun.

## Other automation

```powershell
# Bootstrap a brand-new GitHub repo with an immediately safe bootstrap gate.
pwsh -File scripts/bootstrap-repo.ps1 -Name my-app

# Fan a newly approved standards commit out as reviewable pin-bump PRs.
pwsh -File scripts/upgrade-repos.ps1

# Fresh independent semantic review of the current branch.
pwsh -File scripts/codex-review.ps1

# Enable auto-merge only for an eligible R0-R2 PR.
pwsh -File scripts/auto-merge.ps1 -Repo kgsmith19/my-app -Pr 12 -Risk R2

# Direct lower-level maintenance when needed.
pwsh -File scripts/apply-github-standard.ps1
pwsh -File scripts/sync-agentic-project.ps1
pwsh -File scripts/doctor.ps1 -Remote
```

`policy/github-defaults.json` is the machine-readable portfolio policy.

## GitHub default

Managed repos use GitHub Issues for durable work, one stable GitHub-Actions-produced required `PR Gate`, draft PRs while agents iterate, squash merge, risk-aware auto-merge, merged-branch cleanup, protected `main`, and resolved review threads.

Current user-owned repos keep CODEOWNERS advisory so a solo PR author is not deadlocked by self-approval rules. R3/R4 and control-plane changes instead require fresh independent semantic review and do not use the R0-R2 auto-merge helper. Organization-owned repos can automatically harden to required Code Owner review and merge queues where the GitHub plan supports them.

The optional cross-repo GitHub Project is a portfolio view only; it is never a competing task database.

## Repo-specific truth

Each product repo owns only what is specific to that product: PRD, active specs, important ADRs, source code, tests, commands, and deployment details. Do not copy the universal standard into every repo.

## ACC target

ACC should eventually wrap these proven scripts as:

```text
acc repo init <name>
acc standard upgrade
acc doctor
acc review
acc merge
```

Until then, the PowerShell scripts are the executable reference implementation.
