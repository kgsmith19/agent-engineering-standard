# Security, Risk & Autonomy

## Goal

Maximize safe autonomy by matching permissions and human involvement to consequence.

## 1. Risk levels

Use a small risk scale:

- `R0` non-behavioral/trivial
- `R1` local, reversible behavior
- `R2` normal product/API change
- `R3` sensitive boundary: auth, PII, external actions, migrations, secrets
- `R4` high-consequence: destructive, financial, privileged, irreversible

Risk may be raised by an implementation agent, never lowered by it.

## 2. Least privilege

Grant only what the slice needs:

- file read/write
- commands/processes
- network destinations
- secrets
- databases/cloud resources
- Git/GitHub actions
- deployment authority
- destructive actions
- spend/time budget

## 3. Evidence-weighted autonomy

Prefer autonomy when the change is:

- well understood
- strongly verified
- reversible
- low blast radius

Routine low-risk work should not require human babysitting. R3 is not automatically a human gate: a reversible sensitive change may integrate automatically after deterministic verification plus a current-head independent semantic review from a provider that did not implement it.

## 4. Manual gates require written justification

A manual gate is an exception, not a default. Every manual gate must state:

1. the concrete failure/consequence it prevents
2. why deterministic checks plus independent agent review cannot safely decide it today
3. who/what owns the authorization decision
4. the exact removal condition that lets the gate be automated or deleted

Never keep a gate merely because a change is “important” or “high risk.”

Current justified defaults:

- **Control plane:** manual because a PR can modify the evaluator/merge authority judging itself. Remove this gate when enforcement is an immutable external or organization-required workflow the PR cannot edit.
- **R4 action authorization:** manual because the decision grants destructive, financial, privileged, or irreversible authority. Agent review may still be fully automated; the manual step is authorization, not code review. Remove/reclassify only when the action becomes mechanically bounded and reversible.

## 5. Protect the control plane

The implementing agent must not modify the evaluator, risk policy, required checks, deployment authority, or other controls governing its current run and then use those modified controls to approve itself.

Changes to those controls use a separate authorized path: the manual control-plane authority gate (owner sign-off), not an automated reviewer.

## 6. Independent review

Automated inline AI code review was removed from the blocking merge path entirely (ADR 0004) — the deterministic `PR Gate` is the sole required merge authority. `scripts/codex-review.ps1` remains available as an optional, local, manual second opinion when a human wants one; it is never a required or automated check.

## 7. Security baseline

Automate applicable:

- secret scanning
- dependency/vulnerability review
- static/security analysis
- workflow permission checks
- trusted/pinned automation

Use deeper threat/abuse review for higher-risk changes.
