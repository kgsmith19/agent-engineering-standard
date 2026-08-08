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

Require stronger authorization when uncertainty or consequences rise.

Routine low-risk work should not require human babysitting.

## 4. Protect the control plane

The implementing agent must not modify the evaluator, risk policy, required checks, deployment authority, or other controls governing its current run.

Changes to those controls use a separate authorized path.

## 5. Security baseline

Automate applicable:

- secret scanning
- dependency/vulnerability review
- static/security analysis
- workflow permission checks
- trusted/pinned automation

Use deeper threat/abuse review for higher-risk changes.
