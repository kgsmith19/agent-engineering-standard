# AGENTS.md

This repository is the authoritative shared engineering standard for Kyle's agent-driven repositories.

## Read first

Use `README.md` as the map, then read only the standard file relevant to the work:

- lifecycle: `LIFECYCLE.md`
- agent behavior: `AGENT_RULES.md`
- testing/architecture quality: `QUALITY_RULES.md`
- security/risk/autonomy: `SECURITY_RISK_AUTONOMY.md`
- GitHub/CI/release: `DELIVERY_GITHUB.md`
- evidence/ROI learning: `EVIDENCE_LEARNING.md`

## Work model

GitHub Issues are the durable work-item source. Work in a short-lived branch, make the smallest coherent change, open a PR, and let the protected `PR Gate` decide merge eligibility.

This is a control-plane repository. Changes that weaken testing, risk, CI, merge, or authority policy are R3+ and require the owner's manual control-plane authority sign-off before merge — never an automated reviewer, and never self-approved by the PR that makes the change.

## Lean rule

Do not add a document, workflow, policy, or gate unless it reduces meaningful uncertainty, prevents a real/high-consequence failure, or provides useful independent evidence.

## Portfolio automation

`policy/github-defaults.json` defines the default active-repository GitHub control-plane policy. `scripts/apply-github-standard.ps1` applies repository settings and the default-branch ruleset using GitHub CLI admin access. GitHub Issues are the only durable work-item view; no cross-repo Project board is synced.
