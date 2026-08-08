# Lean Agent Engineering Standard

This repo is the authoritative shared engineering standard for Kyle's agent-driven software projects.

## Goal

Maximize:

**accepted useful outcomes per human active minute and total cost**

while protecting correctness, security, reliability, recoverability, and maintainability.

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

Every artifact, rule, gate, and CI run must do at least one:

1. Reduce meaningful uncertainty.
2. Prevent a known or high-consequence failure.
3. Provide independent evidence.

Otherwise remove it.

## Shared standards

- [Lifecycle](LIFECYCLE.md)
- [Agent Rules](AGENT_RULES.md)
- [Quality Rules](QUALITY_RULES.md)
- [Security, Risk & Autonomy](SECURITY_RISK_AUTONOMY.md)
- [Delivery & GitHub](DELIVERY_GITHUB.md)
- [Evidence & Learning](EVIDENCE_LEARNING.md)

`AGENTS.md` is the operating map for agents working on this control-plane repo.

## GitHub control plane

Machine defaults live in `policy/github-defaults.json`.

After cloning this repo and authenticating GitHub CLI with repo-admin access:

```powershell
pwsh -File scripts/apply-github-standard.ps1
pwsh -File scripts/sync-agentic-project.ps1
pwsh -File scripts/doctor.ps1 -Remote
```

These commands configure the active portfolio for the lean default: GitHub Issues as durable work, one stable required `PR Gate`, squash + auto-merge, merged-branch cleanup, protected `main`, and merge queues when GitHub supports them.

The cross-repo GitHub Project is a portfolio view only. Issues remain the work source of truth.

## Repo-specific truth

Each product repo owns only what is specific to that product:

- PRD
- active specs
- important ADRs
- source code
- tests
- commands
- deployment details

Do not copy large amounts of universal guidance into each repo.

## Bootstrap target

Today, the PowerShell scripts above apply and verify the GitHub control plane. ACC should eventually wrap the same behavior as:

```text
acc repo init <name>
acc doctor
```

The resulting repository must remain understandable and usable from a clean clone without hidden local dependencies.
