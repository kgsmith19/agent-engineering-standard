# SPEC-0043: PR State-Machine Exhaustiveness

Issue: #43

## Outcome
Every GitHub event or state transition that can materially change merge authority, deterministic evidence, semantic-review evidence, or reviewer independence is handled immediately and deterministically. Unsupported or unknown authority states fail closed instead of waiting silently.

## Required behavior

### Event lifecycle
- `PR Automation` handles PR `edited`, `auto_merge_enabled`, and `auto_merge_disabled` in addition to the existing lifecycle events.
- Formal review `submitted`, `edited`, and `dismissed` all re-evaluate semantic state.
- Inline review comment `created`, `edited`, and `deleted` all re-evaluate semantic state and merge arming.
- Structured Copilot issue comment `created`, `edited`, and `deleted` all re-evaluate semantic state.
- Events that do not affect authority or evidence remain intentionally ignored and are documented as such.

### Deterministic gate outcomes
For a current-head completed `PR Gate` workflow:
- `success` -> continue to semantic review.
- `failure`, `timed_out`, `startup_failure` -> bounded CI repair.
- `action_required` -> explicit workflow-approval block.
- `skipped` -> explicit invalid-gate block.
- `cancelled`, `stale` -> one automatic workflow rerun; a repeat becomes explicit block.
- `neutral` -> explicit block.
- any unknown conclusion -> explicit fail-closed block.
Stale-head workflow results remain ignored.

### Reviewer independence
Reviewer eligibility excludes every recognized Codex/Copilot actor appearing as author or committer on any commit currently in the PR, not only the latest commit. If both connected providers contributed, no connected independent reviewer exists and the lane fails closed.

### Repository trust boundary
Cross-repository/fork PRs cannot enter unattended auto-merge. They are explicitly blocked until re-homed into a branch in the managed repository.

### Base-branch correctness
A PR metadata edit that changes the effective base/diff must cause fresh `PR Gate` evidence. Existing gates must include the `edited` pull-request activity.

## Properties
- PROP-001: A deleted or edited semantic-review artifact cannot leave stale `AI Review` success authoritative.
- PROP-002: No documented completed workflow conclusion is silently ignored for the current head.
- PROP-003: Automatic reruns are bounded to one per cancelled/stale workflow run.
- PROP-004: No connected reviewer may review code that provider authored or committed anywhere in the current PR.
- PROP-005: A fork PR cannot arm unattended auto-merge.
- PROP-006: A base-branch change cannot reuse deterministic evidence produced for a different effective diff.
- PROP-007: Unknown authority states fail closed.

## Out of scope
- Adding a third machine-review provider.
- Automatically importing/re-homing arbitrary external fork branches.
- Changing product-specific test commands.
- Merge queue enablement.

## Verification
- Pure table-driven policy tests for every workflow conclusion and reviewer-actor combination.
- Structural workflow-trigger tests for every required event.
- Full `PR Gate` on the final exact head.
- Fresh exact-head independent machine review.