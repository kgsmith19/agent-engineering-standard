# Work

## Thin Issues and Work Claiming

One Issue represents **one observable outcome**: one cohesive behavioral boundary, independently
testable, independently mergeable, reversible or recoverable, with one branch, one worktree, and
one PR.

Split an Issue when it contains multiple independently valuable outcomes, crosses unrelated
domains, needs multiple writers in the same files, could be part-approved, can partly ship
independently, exceeds roughly five behavior claims, defeats one cohesive evidence strategy,
mixes unrelated cleanup, or cannot be reviewed in one focused pass. Prefer vertical behavior
slices over layer-only Issues. Broad ideas get one parent Issue plus native GitHub sub-Issues,
each assigned to the milestone; the parent owns no implementation commits and closes only after
every required sub-Issue and final integration verification. Use the Issue template (canonical
`TEMPLATES/ISSUE.md`, active `.github/ISSUE_TEMPLATE/work-item.md`).

Standard labels (the only set): `status:ready`, `status:active`, `status:blocked`; `risk:R0`
through `risk:R3`; `owner:allow-draft`, `owner:hold-merge`, `owner:policy-change`. Owner-prefixed
labels are trusted only when applied by the owner; an unauthorized owner-prefixed label changes no
policy, is removed when permissions permit, is recorded in the workflow summary, and generates no
public comment.

**Claim protocol** (labels are not an atomic lock):

1. Confirm the Issue is open, `status:ready`, not `status:blocked`, and has no open PR
   implementing it.
2. Resolve the exact current default-branch SHA.
3. Construct branch `issue/<issue-number>-<short-slug>` and worktree
   `.worktrees/issue-<issue-number>-<short-slug>`.
4. Atomically create the remote branch via the GitHub ref-creation API. "Reference already
   exists" is a failed claim — never overwrite or force-update an existing claim branch.
5. Add `status:active`, remove `status:ready`, and assign the agent identity when appropriate.
6. Create or update exactly one managed Work State comment (marker
   `<!-- agent-engineering-standard:work-state:v1 -->`) covering Issue, milestone, branch, base
   SHA, current head, providers, active task, last checkpoint, PR, status, and blocker. Update it
   instead of posting progress comments. Never include local absolute filesystem paths in
   comments.

## Worktrees and Parallel Work

Every implementation Issue uses an isolated worktree unless the harness already provides an
isolated workspace. Preference order: harness-native isolation → existing `.worktrees/` → manual
`git worktree`. The repository `.gitignore` **must** contain `.worktrees/`, `.superpowers/`,
`.agent-runtime/`, and `.evidence/`.

Baseline before implementing: install dependencies with documented commands; run the relevant
formatter, build, static checks, and tests; record the exact baseline SHA; distinguish
pre-existing failures from change-caused failures; never silently inherit a dirty tree.

Exactly one implementation writer per worktree at a time; read-only agents may inspect
concurrently when the harness guarantees no mutation. **Safe to parallelize:** independent Issues
in separate worktrees, unrelated subsystems, or read-only research, critique, and verification.
**Never parallelize** writers that touch the same files, share mutable external state, depend on
each other's output, or alter the same schema, API contract, or migration sequence. When
uncertain, execute sequentially. The controller reviews each subagent report, verifies commit
ranges and overlapping files, reruns the complete affected suite after integration, performs
whole-branch review, and **never trusts subagent success claims without independent evidence.**

**Cleanup:** preserve worktrees with open PRs. After a merged PR, remove the worktree only when
the PR is merged, the tree is clean, nothing is unpushed, the head is represented in merged
history, and no active subagent is recorded. Preserve closed-unmerged work unless the owner
explicitly says otherwise. Report ambiguous or orphaned worktrees; never delete them
automatically. `python tools/standardctl.py worktrees reconcile` reports; `worktrees prune-safe`
removes only conclusively safe worktrees. When a cloud harness owns the workspace, use its native
cleanup and record the disposition.

## Context Recovery and Subagent Tracking

Do not rely on one ever-growing controller context. Use fresh task subagents with focused briefs,
report files instead of pasted history, checkpoints at task boundaries, fresh independent
reviewers, restart-safe Issue/PR/branch state, a local ledger, and Git history as the durable
record.

Each Issue keeps a gitignored ledger (`.superpowers/sdd/<identity>/` or
`.agent-runtime/issues/<n>/`) holding progress, task briefs, reports, and reviews. Task states:
`DISPATCHING`, `ACTIVE`, `COMPLETE`, `BLOCKED`, `UNKNOWN`.

> [!CAUTION]
> **Never convert `UNKNOWN` to `COMPLETE` by assumption.** Never dispatch a second writer into a
> worktree while an earlier writer may still be active; when the harness cannot enumerate active
> subagents, mark the state `UNKNOWN`, terminate the previous session when possible, and use a
> read-only investigator until exclusivity is re-established.

Every implementation task gets implementer self-review, task-scope specification and quality
review against the actual diff (never prose summaries alone), fresh verification, and a ledger
checkpoint recording Issue, branch, exact head, commands, results, findings, next command, and
writer status — mirrored concisely into the Work State comment.

**Recovery after restart or compaction:** bootstrap per Session bootstrap; read the Issue, its
PR, the Work State comment, and the ledger; run `git worktree list --porcelain`, `git status`,
and `git log`; compare local and remote heads; verify reported commits exist; resume the first
task without a valid `COMPLETE` record. **Trust Git and verified GitHub state over model
recollection.**
