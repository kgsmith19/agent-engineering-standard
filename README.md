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

## Automation today

```powershell
# Configure active repos: Actions, squash/auto-merge, default-branch rules.
pwsh -File scripts/apply-github-standard.ps1

# Create/sync the optional cross-repo Project view. Issues remain truth.
pwsh -File scripts/sync-agentic-project.ps1

# Verify local + remote control-plane state.
pwsh -File scripts/doctor.ps1 -Remote

# Bootstrap a brand-new GitHub repo with the universal baseline.
pwsh -File scripts/bootstrap-repo.ps1 -Name my-app

# Fan a newly approved standards commit out as reviewable pin-bump PRs.
pwsh -File scripts/upgrade-repos.ps1

# Fresh independent semantic review of the current branch.
pwsh -File scripts/codex-review.ps1
```

`policy/github-defaults.json` is the machine-readable portfolio policy.

## GitHub default

Managed repos use GitHub Issues for durable work, one stable required `PR Gate`, draft PRs while agents iterate, squash + auto-merge, merged-branch cleanup, protected `main`, and merge queues when GitHub supports them.

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
```

Until then, the PowerShell scripts are the executable reference implementation.
