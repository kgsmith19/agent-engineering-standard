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
→ PR
→ required `PR Gate` + exact-head `AI Review`
→ auto-merge / merge queue when supported
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

After product repos contain the thin `AI Review` caller and GitHub CLI is authenticated:

```powershell
pwsh -File scripts/setup-portfolio.ps1
```

That applies repository settings/rules, enables Actions, creates the lean risk/status labels, syncs the optional `Agentic Portfolio` Project, and runs the remote doctor. Do not call the portfolio ready until the remote doctor reports READY.

## Other automation

```powershell
# Bootstrap a new repo with the shared engineering contract.
pwsh -File scripts/bootstrap-repo.ps1 -Name my-app

# Fan an approved standards commit out as reviewable pin PRs.
pwsh -File scripts/upgrade-repos.ps1

# One cheap batched local semantic review.
pwsh -File scripts/codex-review.ps1

# Request a bounded cross-provider review using GitHub-Actions-attested provenance.
pwsh -File scripts/request-independent-review.ps1 -Repo kgsmith19/my-app -Pr 12

# Arm GitHub auto-merge only after live policy requires exact-head PR Gate + AI Review.
pwsh -File scripts/auto-merge.ps1 -Repo kgsmith19/my-app -Pr 12 -Risk R2

# Lower-level maintenance.
pwsh -File scripts/apply-github-standard.ps1
pwsh -File scripts/sync-agentic-project.ps1
pwsh -File scripts/doctor.ps1 -Remote
```

`upgrade-repos.ps1` preserves each existing `.agent/standard.lock` revision key and supports `sha`, `commit`, and `standard_commit` without guessing.

`policy/github-defaults.json` is the machine-readable portfolio policy.

## GitHub default

Managed repos use GitHub Issues for durable work, draft PRs while agents iterate, squash merge, branch cleanup, protected `main`, and resolved review threads. Integration requires two GitHub-Actions-bound contexts on the latest head:

- `PR Gate` for deterministic evidence
- `AI Review` for cross-provider semantic review freshness

A new push invalidates the previous head's semantic authorization automatically. Human approval count stays 0 on personal repos. R0-R3 may auto-merge after both required gates and review-thread resolution when no justified authority gate applies. R4 never auto-merges.

Control-plane PRs remain manually merged only while they can modify the evaluator/merge authority that judges them. That gate is removed when enforcement becomes immutable/external to the PR.

The optional cross-repo GitHub Project is a portfolio view only; it is never a competing task database.

## Repo-specific truth

Each product repo owns only product-specific PRD, active specs, important ADRs, source, tests, commands, and deployment details. Do not copy the universal standard into every repo.

## ACC target

ACC should eventually wrap the proven scripts and run the recurring portfolio loops automatically:

```text
acc repo init <name>
acc standard upgrade
acc doctor
acc review
acc resolve-ready
acc cleanup
acc merge
```

Until those adapters are proven, the scripts are the executable reference implementation.
