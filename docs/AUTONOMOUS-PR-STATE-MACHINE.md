# Autonomous PR State Machine

This is the authoritative decision map for routine pull-request integration across the managed portfolio.

> **Amendment (2026-08-09, ADR 0002):** the deterministic `PR Gate` is now the sole required status context. Machine review is advisory-only and off by default (`independent_review.required_for_auto_merge: false`, `solicit_reviews: false`); every review state, event, and invariant below that references `AI Review` applies only when those policy flags re-enable the review lane. Required review-thread resolution is off, repair budgets are 3 (CI) / 2 (conflict) / 1 (same-head gate rerun), and the watchdog runs six-hourly.
>
> **Canary amendment (#42, ADR 0003):** while `independent_review.dispatch_mode` is `disabled_pending_e2e`, no reviewer is dispatched and the evaluator publishes a `neutral` `AI Review` check outcome — a passing conclusion for the lane. Blocking P0/P1 evidence still fails the check; P2-only findings are recorded once as an advisory Issue mapped to the exact head (updated in place on later heads, never re-created); unreviewed auto-merge stops at `R2`. `REVIEW_REQUESTED`/`REVIEW_FALLBACK` are unreachable in this mode: a successful `PR Gate` goes straight to evaluation, landing on `MERGE_PENDING` (neutral or clean) or `BLOCKED` (blocking evidence) without ever requesting a reviewer. The CI/review/conflict repair lanes post no `@codex`/`@copilot`/`@dependabot` tag either; each applies a recoverable `<lane>-dispatch-disabled` block instead that clears automatically once dispatch is enabled. Block and authority comments name the owner as `(owner: kgsmith19)` rather than `@kgsmith19` for the same reason. The live E2E canary drill is the removal condition for this mode (ADR 0003).

## Invariants

1. `main` changes through a pull request.
2. Routine human approval count is `0`.
3. Native `.github/CODEOWNERS` is absent.
4. `kgsmith19` is removed from requested-reviewer state whenever detected.
5. Kyle may be tagged only for a justified authority decision.
6. `PR Gate` is the sole required status context (ADR 0002). `AI Review`, also produced by GitHub Actions, is advisory: it never gates the branch ruleset, and while dispatch is disabled it evaluates every head without ever requesting a reviewer.
7. Both checks apply to the current head SHA.
8. A push invalidates prior semantic evidence.
9. The reviewer must differ from every detected machine implementer on the latest head commit.
10. Auto-merge is squash-only and never applies to R4 or self-modifying control-plane changes.
11. Repairs are bounded; exhaustion becomes explicit `status:blocked`, never an infinite loop.
12. Copilot may repair an existing non-Copilot PR, but a Copilot-owned PR is outside the unattended lane because GitHub requires human review and merge.
13. A material finding cannot be bypassed by reviewer-shopping on the same head.
14. Temporary reviewer latency remains recoverable; pending review pauses auto-merge and the 12-hour safety timeout is checked by a six-hourly watchdog.
15. Automation state/budget/request markers are authoritative only when posted by a trusted automation author.
16. If a trusted base predates the evaluator/orchestrator during the one-time bootstrap, reusable workflows execute no proposed PR scripts and remain on the explicit external authority path.
17. Every PR is Ready at creation. Draft state is a policy violation, not an implementation state.
18. A PR whose head repository is not the target repository (a fork) is denied before any privileged automation runs. No check run, comment, or Issue is ever written for a fork head; automation blocks the target-repo record only, `fork-pr`, and re-homing is the only exit.

## States

| State | Meaning | Exit condition |
|---|---|---|
| `PR_CONTRACT_BLOCKED` | A PR was opened or converted to draft | explicit Ready state followed by fresh evaluation |
| `READY_UNVERIFIED` | Merge intent exists; current head is unproven | `PR Gate` starts |
| `GATE_RUNNING` | Deterministic evidence is running | pass, failure, timeout, skip, approval block, newer head |
| `CI_REPAIR` | Copilot is repairing deterministic failure on the existing PR | new head or retry exhaustion |
| `REVIEW_REQUESTED` | Independent exact-head review was requested | pass, finding, stall, newer head |
| `REVIEW_FALLBACK` | Primary reviewer stalled; one independent fallback was requested | pass, finding, safety timeout, newer head |
| `REVIEW_REPAIR` | Copilot is repairing blocking P0/P1 findings | new head or retry exhaustion |
| `MERGE_PENDING` | Auto-merge is armed and gates are waiting/green | GitHub merges or a blocker appears |
| `CONFLICT_REPAIR` | Dependabot/Copilot is resolving a conflict | new head or retry exhaustion |
| `AUTHORITY_REQUIRED` | Machine evidence may finish, but intent/authority cannot be inferred | Kyle explicitly decides; no reviewer assignment |
| `BLOCKED` | A true bounded/configuration failure exists | evidence proves recovery or the blocker is deliberately cleared |
| `MERGED` | GitHub completed squash merge | release/deploy/observe |
| `CLOSED` | Rejected, superseded, or abandoned | explicit reopen |

## Primary flow

```mermaid
flowchart TD
    A[PR opened or synchronized] --> B[Remove forbidden reviewer requests]
    B --> C{Copilot-owned PR?}
    C -- Yes --> C1[BLOCKED: re-home into non-Copilot PR]
    C -- No --> D{Draft?}
    D -- Yes --> E[BLOCKED: fail ready-at-creation contract]
    D -- No --> H[Classify risk and changed paths]
    H --> I{Conflict?}
    I -- Yes --> J[Dependabot rebase or Copilot conflict repair]
    J --> A
    I -- No --> K{R4 or self-modifying control plane?}
    K -- Yes --> L[Tag Kyle for justified authority; never request review]
    K -- No --> M[Validate live ruleset and arm squash auto-merge]
    M --> N[Run PR Gate]
    N --> O{Gate result}
    O -- Failure or timeout --> P[Copilot root-cause repair, max 3]
    P --> A
    O -- Approval required --> Q[BLOCKED: disable Copilot workflow approval]
    O -- Skipped or missing --> R[BLOCKED: repair workflow trigger]
    O -- Success --> S[Detect latest-head implementers]
    S --> T[Request reviewer independent of all detected implementers]
    T --> U{Review result}
    U -- Clean or P2-only --> V[AI Review success/neutral; P2 recorded as advisory Issue]
    U -- P0/P1 finding --> W[One batched Copilot review repair]
    W --> A
    U -- Primary stalled --> X{Independent fallback available?}
    X -- Yes --> Y[Request one fallback]
    Y --> U
    X -- No --> Z[Pause auto-merge; await evidence or safety timeout]
    V --> AA[Resolve only stale machine-only threads]
    AA --> AB{Human/current-head thread remains?}
    AB -- Yes --> AC[GitHub thread rule keeps merge pending]
    AB -- No --> AD[GitHub automatically squash-merges]
    AD --> AE[Delete branch and continue release flow]
```

## Event and decision matrix

| Event or condition | Detection | Automated action | Result |
|---|---|---|---|
| Draft opened | `pull_request_target.opened` | Disable auto-merge; apply `status:blocked`; post one diagnostic; fail workflow | `PR_CONTRACT_BLOCKED` |
| Ready opened | PR event | Classify risk/path and arm auto-merge if eligible | `READY_UNVERIFIED` |
| Fork PR (head repository differs from target repository) | `head.repo.full_name` / head-repository-owner mismatch | Deny before any privileged mutation in every entry point (workflow `if:` guards plus each script's own check); no check run, comment, or Issue is ever written for the fork head | `BLOCKED` (`fork-pr`; re-home into the managed repository) |
| Converted to draft | `converted_to_draft` | Disable auto-merge; apply block; fail workflow; never auto-convert | `PR_CONTRACT_BLOCKED` |
| Legacy draft explicitly made Ready | `ready_for_review` | Resolve the draft block and re-evaluate all current facts | `READY_UNVERIFIED` |
| Push while draft | `synchronize` | Repeat the visible contract failure; never spend semantic-review budget | `PR_CONTRACT_BLOCKED` |
| Push while Ready | new SHA | Old evidence becomes irrelevant; state restarts | `READY_UNVERIFIED` |
| `kgsmith19` requested as reviewer | `review_requested` | Immediately remove requested reviewer; tag only later if authority is truly required | routine lane |
| Stale workflow result | event SHA != current SHA | Ignore | unchanged |
| PR Gate passes | `workflow_run.success` | Recover prior gate blocks; request independent exact-head reviewer | `REVIEW_REQUESTED` |
| PR Gate fails/times out/startup fails | workflow conclusion | Copilot root-cause repair, max 3 | `CI_REPAIR` |
| PR Gate cancelled by newer push | `cancelled`, stale head | Ignore old run | unchanged |
| PR Gate cancelled or stale on the current head | `cancelled`/`stale`, current head | `gate-result-router.ps1` reruns the same Actions run once; a repeat becomes an explicit block | rerun once, then `BLOCKED` (`gate-rerun-exhausted`) |
| PR Gate concludes `neutral` | workflow conclusion | Block: a required deterministic gate must produce `success` or an actionable failure — unlike `AI Review`'s advisory `neutral` | `BLOCKED` (`gate-neutral`) |
| PR Gate returns an unrecognized conclusion | workflow conclusion | Fail closed instead of ignoring it | `BLOCKED` (`gate-unknown`) |
| Workflow approval required | `action_required` | Disable auto-merge; block with exact UI setting | `BLOCKED` |
| Ready PR Gate skipped | `skipped` | Block as invalid workflow trigger/job condition | `BLOCKED` |
| No PR Gate check | watchdog | Block with missing-check reason | `BLOCKED` |
| Latest head authored/committed by Copilot | commit actor | Exclude Copilot; Codex is accepted if independent | review lane |
| Latest head authored/committed by Codex | commit actor | Exclude Codex; Copilot is accepted if independent | review lane |
| Latest head contains both Codex and Copilot machine actors | commit actor set | No connected independent reviewer; fail closed | `BLOCKED`/new independent provider required |
| Latest head human/unknown | no machine actor | Codex primary; Copilot fallback | review lane |
| Clean formal review | exact commit ID, no blocking P0/P1 | Set `AI Review` success | `MERGE_PENDING` |
| Codex thumbs-up | reaction on trusted exact-head request | Set `AI Review` success | `MERGE_PENDING` |
| Structured Copilot PASS | trusted exact-head request exists and response follows it | Set `AI Review` success | `MERGE_PENDING` |
| P0/P1 finding | exact-head formal/inline review/comment | Set failure; one batched Copilot repair | `REVIEW_REPAIR` |
| P2-only finding, no P0/P1 | exact-head formal/inline review/comment | Set `AI Review` success/neutral; record or update one deduplicated advisory Issue for the PR | `MERGE_PENDING` |
| Dispatch disabled, no blocking evidence on current head | `dispatch_mode: disabled_pending_e2e` | Set `AI Review` neutral without requesting a reviewer; evidence embeds `dispatch_policy_version` | `MERGE_PENDING` (capped at `auto_merge_max_risk: R2`) |
| `dispatch_policy_version` bumped past the version recorded on current-head `AI Review` evidence | stale version in check summary | Treat as no evidence; watchdog/gate-result re-invoke the evaluator (the swarm re-enable invalidation gate) | re-evaluates |
| Dispatch disabled and a bounded repair lane would otherwise fire | CI/review/conflict repair trigger | Post no `@codex`/`@copilot`/`@dependabot` tag; apply a recoverable `<lane>-dispatch-disabled` block instead | `BLOCKED`, clears automatically once dispatch is enabled |
| Same-head repair comment retriggers workflows | trusted repair marker for current SHA | Treat as pending; do not consume another repair attempt | `REVIEW_REPAIR` |
| Primary reviewer stalls for fast window | trusted request timestamp | Request one independent fallback when available | `REVIEW_FALLBACK` |
| Fast primary+fallback windows expire | bounded polling | Pause auto-merge; late review events can still recover | review waiting |
| Review reaches 12-hour safety timeout | six-hourly watchdog sees age >= 720 min | Disable auto-merge; add `status:blocked` | `BLOCKED` |
| Late valid review after timeout block | review/comment event | Set success, resolve automation block, re-arm auto-merge | `MERGE_PENDING` |
| Review dismissed | review event | Re-evaluate; withdraw success when proof disappears | review waiting/blocking |
| New push after clean review | new SHA | Prior review cannot authorize it; repeat full cycle | `READY_UNVERIFIED` |
| Old (non-current-head) machine-only thread remains | successful new-head review + GraphQL audit | Resolve: all participants are recognized machines and no comment belongs to current head | thread cleared |
| Human participated in thread | thread audit | Never auto-resolve | merge pending |
| Current-head machine thread, not entirely P2-only advisory | thread audit | Never auto-resolve | review/fix required |
| Current-head machine thread, every comment P2-only advisory | thread audit | Resolve: P2-only current-head findings do not block merge either | thread cleared |
| Ordinary merge conflict | mergeability | Copilot semantic resolution, max 2 | `CONFLICT_REPAIR` |
| Dependabot conflict | author identity | `@dependabot rebase`, max 2 | `CONFLICT_REPAIR` |
| Conflict disappears after update | PR event | Resolve automation conflict block | normal lane resumes |
| Auto-merge disabled by contributor push | PR event/live state | Revalidate and re-arm | `MERGE_PENDING` |
| Base branch not default | auto-merge validator | Refuse auto-merge | blocked/correct target |
| Additional active ruleset governs default branch | effective branch-rules audit in setup, doctor, and runtime arming | Refuse READY/auto-merge until authority is reconciled | blocked/configuration repair |
| Multiple risk labels | risk parser | Fail closed | `BLOCKED` |
| Risk labels corrected | PR event | Resolve risk block automatically | normal lane resumes |
| No risk label | risk parser | Default R2 | routine lane |
| R0-R3 product change | risk/path | Eligible after gates | routine lane |
| R4 | label | Tag Kyle with four authority fields; never assign reviewer | `AUTHORITY_REQUIRED` |
| Product PR changes control files | path classifier | Treat as control plane | `AUTHORITY_REQUIRED` |
| Any standard-repo PR | repository identity | Self-modifying control plane | `AUTHORITY_REQUIRED` |
| Trusted base predates automation scripts | reusable checkout plus explicit file guard | Execute no proposed scripts; publish a clear bootstrap warning | `AUTHORITY_REQUIRED` |
| Copilot-owned PR | PR author/branch | Disable auto-merge; require re-home | `BLOCKED` |
| Copilot edits existing non-Copilot PR | latest commit actor | Full gates repeat; independent reviewer excludes Copilot | routine lane |
| External-agent draft (not owner, not `github-actions[bot]`), `pr_automation.external_draft_promotion` on | draft PR author | Identity-gated `promote-external-draft.ps1` marks it Ready via GraphQL (`GH_TOKEN_ADMIN`) and re-verifies | `READY_UNVERIFIED`, or `BLOCKED` (`automation-identity-missing`) without the identity |
| Dependabot patch/minor PR | dependency PR | Full gates; eligible if risk is appropriate | routine lane |
| Dependabot major PR | dependency scope | Must be separately risk-classified | R2/R3/block |
| CI repair reaches 3 | trusted markers | Disable auto-merge and block | `BLOCKED` |
| Post-fix reviewed head still has blocking P0/P1 | reviewed-head budget | Disable auto-merge and block | `BLOCKED` |
| Conflict repair reaches 2 | trusted markers | Disable auto-merge and block | `BLOCKED` |
| Untrusted commenter forges automation marker | marker author check | Ignore marker for state, budgets, evidence, and duplicate suppression | unchanged |
| Automation evidence later proves recovery | success event/current facts | Post trusted recovery marker; remove label when no active automation block remains | normal lane resumes |
| Manually applied `status:blocked` with no trusted automation marker | label | Treat as authoritative; never auto-clear | `BLOCKED` |
| Checks green but unresolved thread | ruleset | GitHub refuses merge | merge pending |
| Checks and threads clear | GitHub auto-merge | Squash merge; delete branch | `MERGED` |
| Closed/superseded | PR state | Ignore | `CLOSED` |
| Reopened | PR event | Re-evaluate all current facts | appropriate state |

## Retry and cost bounds

| Lane | Bound | Reason |
|---|---:|---|
| CI repair | 3 | autonomous repair loop before a human is asked |
| Review repair | 1 batched repair | two reviewed heads total: initial plus post-fix |
| Conflict repair | 2 | autonomous resolution loop before a human is asked |
| Gate rerun (cancelled/stale, current head) | 1 | recover a transient Actions hiccup before blocking |
| Reviewed head SHAs | 2 | coherent head plus one post-fix head |
| Fallback reviewer | 1 per head when independent | fallback, not a default second review |
| Fast review polling | 2 + 2 minutes | catch reaction-only review without indefinite runner use |
| Reviewer safety timeout | 12 hours | service-stall boundary |
| Watchdog | six-hourly | fast stall recovery; normal operation is event-driven |
| AI Review workflow | review/review-comment/structured-review-comment events only | no runner on ordinary PR pushes or implementation chatter |

## `status:blocked`

This is not a generic waiting state. It means a concrete fact exists:

- bounded repair budget exhausted
- required settings/ruleset invalid
- workflow approval remains manual
- required workflow/check missing or skipped
- reviewer safety timeout exceeded
- risk labels contradictory
- PR is draft or was converted to draft
- no connected reviewer remains independent of all detected latest-head machine actors
- PR is Copilot-owned and therefore platform-human-merge-only
- PR head repository is not the target repository (fork)
- a bounded repair lane would need an outbound agent tag while dispatch is disabled (self-clears once dispatch is enabled)

Automation posts a machine-readable block marker and exact reason. When later objective evidence proves a recoverable automation block is fixed, it posts a trusted resolution marker and removes the label only when no active trusted automation block remains. A manually applied block has no trusted automation marker and is never auto-cleared.

## Authority versus review

Kyle is never a routine reviewer. When authority is genuinely required, automation posts an `@kgsmith19` comment with:

1. failure class prevented
2. why automation cannot decide
3. decision owner
4. measurable removal condition

That is intentionally different from GitHub requested-reviewer state. While `independent_review.dispatch_mode` is `disabled_pending_e2e`, this comment names the owner as `(owner: kgsmith19)` instead of `@kgsmith19` — the four fields are unchanged; only the mention is withheld, so an intentionally quiet automated system never pages a human.

## Live proof plan

The implementation is incomplete until these canaries succeed:

1. Ready-at-creation: a Ready canary enters `PR Gate` immediately.
2. Draft rejection: a deliberate draft receives `status:blocked`, a failing contract diagnostic, no `gh pr ready`, and no auto-merge attempt.
3. Happy path: gate passes, independent machine reviewer passes, GitHub auto-merges with no human action.
4. Finding: deliberate formal or inline finding blocks; Copilot repairs existing PR; new head is independently reviewed; merge completes.
5. CI failure: deliberate failure creates one bounded repair task and never weakens the gate.
6. Conflict: controlled conflict enters repair lane and cannot merge stale code.
7. Dependabot: safe dependency PR follows the same gates.
8. Reviewer: a `kgsmith19` request is removed automatically.
9. Marker trust: a forged automation marker from an untrusted commenter has no effect on state, budgets, evidence, or duplicate suppression.
10. Settings: workflow-approval or auto-merge drift causes doctor/canary failure.
11. Portfolio: `doctor.ps1 -Remote` reports every managed repository `READY`.

Only a real PR merging itself earns the claim **auto-merge proven**. Other canaries prove recovery and fail-closed behavior.
