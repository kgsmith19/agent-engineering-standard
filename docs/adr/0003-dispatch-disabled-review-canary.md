# ADR 0003: Dispatch-disabled AI Review canary

Status: accepted (2026-08-09). Narrows ADR 0002's advisory review lane; superseded once the live no-dispatch canary proves the mechanism and `independent_review.dispatch_mode` moves off `disabled_pending_e2e`.

## Decision

While `independent_review.dispatch_mode` is `disabled_pending_e2e`, no PR requests a machine reviewer: `request-machine-review.ps1` exits without acting, `request-review-repair.ps1` skips with no comment, and `pr-orchestrator.ps1`'s CI/conflict repair lanes apply a recoverable `<lane>-dispatch-disabled` block instead of an `@copilot`/`@dependabot` tag — each clears automatically once dispatch is enabled.

`evaluate-ai-review.ps1` still runs on every current head and still posts the required-shaped `AI Review` check:

- blocking evidence — see the threat-tier amendment below, which supersedes the original P0/P1-prose threshold — still fails the check;
- advisory evidence (P0–P2 prose) is recorded once as a deduplicated advisory Issue, updated in place across later heads, and never blocks;
- otherwise the check concludes `neutral`, a passing conclusion `auto-merge.ps1` and `pr-orchestrator.ps1` accept alongside `success`.

Unreviewed auto-merge is capped at `auto_merge_max_risk: R2`; `doctor.ps1` fails if that ceiling drifts while the canary is active.

`neutral` means this head was evaluated, no blocking evidence was found, and no reviewer was solicited for it. It does **not** mean the change was semantically or security reviewed, and it does not touch the manual control-plane/R4 authority gates (ADR 0002), which are a separate mechanism unaffected by `dispatch_mode`.

## Why

Reviewer dispatch (`@codex`/`@copilot` mentions) sits in the same failure classes ADR 0002 already demoted from required to advisory. Before spending real dispatch/model calls across the full 13-repository portfolio, the state-machine exhaustiveness work (#43) needed the evaluator, repair lanes, fork denial, reviewer-independence, thread reconciliation, and merge-arming logic proven correct end-to-end — without any live agent mention able to reach a stranger's inbox or spend budget on an unproven path. A canary that is reachable and merge-gating but never dispatches gives that proof surface without the blast radius.

## The `dispatch_policy_version` invalidation mechanism

`independent_review.dispatch_policy_version` (currently `1`) is embedded in every `AI Review` check summary as `policy_version=<N>`, alongside the head and base SHA. `Test-CurrentDispatchEvidence` in `pr-orchestrator.ps1` treats a check whose recorded version does not match the live policy value as stale, exactly like missing evidence: the watchdog and gate-result paths re-invoke the evaluator instead of arming merge on it. Bumping the version is how re-enabling dispatch — the swarm-activation gate — forces every open PR to a fresh verdict instead of grandfathering old neutrals in.

## Threat-tier amendment (2026-08-09)

Blocking evidence is narrowed to an ultra-high objective bar: only a structured verdict line

    BLOCK: <CLASS> <file:line> — <concrete exploit precondition>

with CLASS one of `T1-INFRA-DELETION`, `T2-BACKDOOR`, `T3-HARDCODED-SECRET`, `T4-CRITICAL-VULN` fails the check, and the failure summary quotes the matched verdict line(s). `T4-CRITICAL-VULN` additionally requires ALL of: introduced by this diff; remotely reachable without authentication; yields RCE, full auth bypass, or cross-tenant data access; concrete input or path cited. P0/P1 prose findings are demoted to the advisory Issue path (P0/P1-classified entries are flagged prominently in the Issue body); an unclassified `CHANGES_REQUESTED` review and a structured `AI-REVIEW FAIL` without a BLOCK verdict are advisory, not blocking. A head with no accepted review concludes `neutral`, so `failure` occurs only on structured threats.

Honest limits: the regex enforces the structured format and the enumerated classes only. The T4 semantic bar is enforced by the reviewer contract (the dispatch prompt), not by the parser.

## Path to re-enabling

`dispatch_mode` leaves `disabled_pending_e2e` only after the ordered live canaries in `docs/superpowers/specs/2026-08-09-all-13-github-automation-design.md` ("Required live canaries") pass against real GitHub state — a dispatch-disabled PR reaching `PR Gate` and neutral `AI Review` first, then scoped live dispatch proving clean review, routed-finding repair, and reviewer-removal behavior. Re-enabling is a `policy/github-defaults.json` change (`dispatch_mode` plus a `dispatch_policy_version` bump) governed by this ADR and the canary amendment in `docs/AUTONOMOUS-PR-STATE-MACHINE.md`, not a code change.
