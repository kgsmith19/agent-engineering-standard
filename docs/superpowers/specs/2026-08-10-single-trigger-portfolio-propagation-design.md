# Single-Trigger Fleet-Wide Standard Propagation

Status: approved by Kyle on 2026-08-10
Tracks: #57

## Outcome

A merge to `agent-engineering-standard`'s `main` propagates settings, content, and drift
verification to every managed repo in one automatic run -- no manual step required, and
re-running never creates a duplicate PR.

## Problem

`ops-portfolio-bootstrap.yml` only ran on `workflow_dispatch` and a weekly `schedule`; a
merge to `main` did not trigger it. Even when it did run, `setup-portfolio.ps1` called
`apply-github-standard.ps1` (settings) then `doctor.ps1 -Remote` (verification), but never
`upgrade-repos.ps1` (the script that pins the new standard SHA into each product repo's
`.agent/standard.lock` and regenerates its thin-caller workflows). So the content half of
the standard has never actually propagated as part of any automated run -- only settings
did.

Separately, `upgrade-repos.ps1` names its rollout branch `chore/standard-<short-sha-of-the-
new-commit>` and only checks for an existing open PR on that exact branch name. Every new
standard commit therefore produced a brand-new branch and PR, leaving any prior still-open
rollout PR stale and orphaned. This is exactly what happened in practice: three real rollout
PRs went stale this way and had to be manually reconciled.

## Chosen approach

Three small, targeted changes, all in this repo:

1. **Trigger.** Add `push: branches: [main]` to `ops-portfolio-bootstrap.yml`'s `on:`
   block, alongside the existing `workflow_dispatch` and weekly `schedule`. The
   AUTOMATION_TOKEN identity check, concurrency group, and permissions are unchanged --
   the bootstrap lane still fails closed without the dedicated automation identity.

2. **Content propagation.** `setup-portfolio.ps1` now runs
   `apply-github-standard.ps1` -> `upgrade-repos.ps1` -> `doctor.ps1 -Remote`: apply
   settings, then pin the content SHA and regenerate thin-caller workflows in every
   product repo, then verify the resulting remote state matches. Each step throws with a
   clear message on nonzero exit, matching the existing style.

3. **Idempotent rollout PRs.** `upgrade-repos.ps1` now searches for ANY open PR in the
   target repo whose head branch matches the glob `chore/standard-*`, not just the exact
   new branch name. If one exists, the script fetches and checks out that existing remote
   branch (`git fetch origin <branch>` + `git checkout -B <branch> FETCH_HEAD`) so the
   regeneration commit lands as a genuine descendant of whatever is already on the branch
   -- including any manual fixup commit -- and pushes normally (a real fast-forward, no
   force). Recreating the branch from the default branch's HEAD and force-pushing over it
   was considered and rejected: it silently discards any history already on the branch. If
   no such PR exists, behavior is unchanged: create `chore/standard-<short-sha>` from the
   default branch and open a new PR. One rollout PR stays open per repo, ever, and it
   always carries the current standard.

## Auto-merge posture

Rollout PRs now relabel from `risk:R3` to `risk:R2`. The propagated content was already
reviewed once, at this repo's own PR gate; deterministically regenerating identical,
template-driven content into product repos is not new independent risk, and this design's
auto-merge ceiling (unattended auto-merge is capped at R2, per
`docs/superpowers/specs/2026-08-09-all-13-github-automation-design.md`) already anticipated
this exact class of change. `upgrade-repos.ps1` only ever writes to known, template-driven
paths (`.agent/standard.lock`, `.agent/project.yaml`, the `AI Review` / `PR Automation`
caller workflows, `.github/dependabot.yml`, and the `ci.yml` name normalization) -- never
arbitrary content.

The mechanism change in this repo (the trigger, the propagation step, and the reuse-PR
logic) is itself `risk:R3`, control-plane: it changes what governs later unattended merges
across the fleet, so it is not itself eligible for unattended auto-merge.

## Rejected alternatives

- Leaving the weekly schedule as the only propagation path: correct eventually, but leaves
  up to a week of drift between a merged standard change and every product repo picking it
  up, and does nothing about the orphaned-PR problem.
- Deleting and recreating the rollout PR on every new standard commit instead of reusing
  the branch: preserves history and review state worse than reusing the branch, and still
  produces PR churn/noise per commit.

## Verification

- `tests/standard-hygiene.tests.ps1`: workflow-structure assertions that the bootstrap
  workflow triggers on push to `main`, that `setup-portfolio.ps1` invokes
  `upgrade-repos.ps1`, and that the rollout label is `risk:R2`.
- `tests/upgrade-repos.tests.ps1`: behavioral coverage against a fake `gh` and a real local
  git remote -- an existing open `chore/standard-*` PR on a different sha's branch gets the
  regenerated content pushed onto that same branch (no new PR); a manual fixup commit
  already on that branch survives the run (regression test for the history-preservation
  fix below); no existing PR still creates `chore/standard-<short-sha>` and opens a new PR
  labeled `risk:R2`.

## Amendment (same day): history-preservation fix

Independent review caught a data-loss bug in the first version of point 3 above: the
script set `$branch` to the existing PR's branch name but still ran `git switch -c
$branch` against the freshly cloned *default* branch's HEAD, then force-pushed that
unrelated history over the existing remote branch -- silently destroying any commit
already on it (verified experimentally with a manual fixup commit). Fixed by checking out
the existing branch's actual tip before regenerating, and dropping `--force` entirely
since the resulting push is then a genuine fast-forward. See the updated point 3 text
above (already reflects the fix) and the new regression test in
`tests/upgrade-repos.tests.ps1`.
