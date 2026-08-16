# Agent Engineering Standard

Operational rules for humans and AI agents working in this repository and in repositories that
adopt this standard.

## Objective

Deliver small, verified, independently mergeable changes with honest evidence — under absolute
owner authority — using **GitHub Issues**, **Milestones**, **pull requests**, and a single
fail-closed **PR Gate** as the machinery of record.

## Owner authority

The **OWNER** is `kgsmith19`, or an explicit instruction authenticated as coming from the owner.
The standard governs agents by default. **The owner governs the standard.**

**Precedence order:** (1) current explicit owner instruction, (2) owner-authorized GitHub Issue
and its acceptance criteria, (3) this `AGENTS.md`, (4) `project.yaml`, (5) pinned shared standard
from `standard.lock` (consuming repositories), (6) harness and provider defaults.

The owner **may override, replace, suspend, or delete any part of this standard at any time**,
without satisfying the old version of the policy — existing policy cannot veto its authorized
replacement, and an agent must evaluate a change against the requested target state, not
superseded rules. An agent **must not** lecture, argue with, reverse, or repeatedly warn about an
explicit owner decision, or create an unsolicited Issue to restore an owner-removed policy.
Technical risks may be stated once, concretely and without obstruction. The owner retains
administrative bypass authority.

> [!IMPORTANT]
> An agent **must not** silently disregard an owner override. When a check is waived, report it
> once as: **"Not run by owner instruction."** And for merges: for every merge not using explicit
> owner bypass, the application-specific PR Gate is the **ultimate machine gate** — no agent
> review, comment, label, artifact upload, or orchestration workflow may bypass it.

Routine agents use a dedicated non-administrative identity with minimum capabilities (contents,
issues, and pull-requests write; actions and metadata read) — no administration, ruleset, secret,
or bypass permissions. Owner administrative credentials stay separate, are never stored in
repository files or workflow secrets, and are used only for explicit owner-authorized
administration or bypass. When agent work runs under the owner account, self-approval does not
protect the control plane — control-plane changes then require an explicit owner administrative
merge decision.

## Sources of truth

| Information | Source of truth |
| --- | --- |
| Product purpose and quick start | `README.md` |
| Agent and engineering rules | `AGENTS.md` |
| Claude / Gemini compatibility | `CLAUDE.md` / `GEMINI.md` (import-only) |
| Repository facts and exact commands | `project.yaml` |
| Release scope | GitHub Milestone |
| Work intent and acceptance criteria | GitHub Issue |
| Implementation evidence and handoff | Pull request |
| Execution history | GitHub Actions |
| Product behavior | Code and tests |
| Adopted standard revision | `standard.lock` (consuming repositories only) |
| Distribution map | `TEMPLATES/manifest.yaml` |
| Temporary task recovery | Gitignored runtime workspace |
| E2E and verification evidence | Actions artifact plus Evidence Index |
| Long-lived release evidence | GitHub Release assets |

**Do not add** a second tracker for anything already listed above: `TODO.md`, a `ROADMAP.md` work
tracker, test ledgers, committed implementation plans or session transcripts, permanent design
documents or ADRs, duplicate status databases, a GitHub Project requirement, or a fleet
synchronization database.

## Session bootstrap

At the start of every new, resumed, or post-compaction controller session:

1. Invoke `superpowers:using-superpowers` when the harness provides Superpowers.
2. Read `AGENTS.md`, then `project.yaml`.
3. Identify the active GitHub Issue, milestone, branch, PR, and exact head.
4. Detect whether the environment is already isolated.
5. Reconcile the local recovery ledger with Git history and remote state.
6. Run the documented clean-baseline verification before modifying code.
7. Resume the first incomplete task rather than repeating completed work.

Use the Superpowers lifecycle skills when available — worktrees, writing plans, subagent-driven
development, test-driven development, systematic debugging, code review, verification before
completion, finishing a branch.

> [!NOTE]
> When a harness cannot load Superpowers: record **"Superpowers unavailable in this harness"**
> and follow the equivalent process manually — isolated worktree, gitignored local plan, RED then
> GREEN then REFACTOR, fresh task-focused contexts, task and final review, fresh verification
> before completion. Superpowers availability is workflow evidence, not a product requirement.

Local plans, briefs, and ledgers live only in gitignored workspaces (`.superpowers/`,
`.agent-runtime/`); nothing drafted there may be committed. **The Issue is the durable artifact.**

## Provider-neutral roles

| Role | Responsibility |
| --- | --- |
| **Owner** | Controls intent and may override anything. |
| **Controller** | Coordinates the Issue, worktree, tasks, subagents, evidence, and recovery state. |
| **Builder** | Implements one bounded task or slice. |
| **Test Designer** | Challenges acceptance criteria and designs defect-sensitive evidence. |
| **Verifier** | Independently challenges intent interpretation, tests, implementation, security, structure, and exact-head evidence. |
| **Investigator** | Researches, reproduces, traces, or measures without implementation authority. |

Supported provider families: `anthropic`, `openai`, `gemini`. Any family may perform any role.
For R2/R3 work: prefer a different provider family for verifier versus builder, require
exact-head verification, and record the provider family and model. The owner may waive provider
separation.

## Releases and milestones

A GitHub Milestone defines a release (for example `v1.4.0`, `vNext`). Use an existing open
release milestone when one is clearly applicable; otherwise create `vNext`. **Do not invent a
semantic version without owner intent.**

Every release-bound Issue belongs to its release milestone. Release state reads directly from the
milestone: open Issue = not completed; `status:ready` = available; `status:active` = claimed;
linked PR = implementation or verification in progress; `status:blocked` = blocked; closed by
merged PR = completed; closed as not planned or duplicate = excluded, not delivered.

Every release milestone contains exactly one Issue titled `VERIFY: <milestone-name> release`. It
verifies: every required implementation Issue closed by merged work; final `main` passing its PR
Gate; release-level commands passing at the exact final SHA; critical E2E behavior; required
artifacts; independent verification of R2/R3 behavior; migration and rollback validation where
applicable; no known release-blocking defect; and published durable release evidence.

> [!IMPORTANT]
> A release is ready only when all required Issues, the verification Issue, and final `main`
> verification are complete — **never merely because the milestone displays 100%.**

## Thin Issues and work claiming

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

## Worktrees and parallel work

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

## Context recovery and subagent tracking

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

## Risk classification

Every Issue carries exactly one tier:

| Tier | Meaning |
| --- | --- |
| **R0** | Mechanical |
| **R1** | Local and reversible |
| **R2** | Shared, integrated, or stateful |
| **R3** | Critical, privileged, destructive, financial, security-sensitive, concurrent, or irreversible |

Verification scales with tier. **R0:** document syntax, references, formatting, structural
validation. **R1:** adds formatter, lint and static analysis, build and type checks, focused
tests, and the affected suite. **R2:** adds integration, contract, persistence, failure and
boundary behavior, property and differential tests, and independent exact-head verification.
**R3:** adds a different-provider verifier, targeted mutation testing, fuzzing, security
analysis, state-machine and concurrency exploration, fault injection, migration dry-run, rollback
verification, canary or shadow execution, and runtime invariants, as applicable. The owner may
override any tier or mechanism.

## Intent and behavioral claims

Issues state falsifiable behavior claims, invariants that must remain true, and outcomes that
must never happen, with example and boundary cases. **Evidence maps one-to-one to claims.** For
important R2/R3 behavior, obtain independent oracle critique before implementation and record at
least one sensitivity demonstration in the PR: RED before implementation, a deliberate negative
control, a plausible targeted mutation, differential comparison, a known-bad fixture, a
historical regression reproduction, fault injection, reference-model disagreement, or an
invalid-transition example. No global mutation-score target and no global coverage target;
coverage and mutation reports are diagnostic evidence only.

## Test quality

Every new or materially changed test (or cohesive group) must satisfy: behavior relevance;
failure sensitivity (a plausible incorrect implementation fails it); an independent oracle
(intent, domain rules, a reference model, or an external contract — never copied implementation
logic); the least expensive adequate level; determinism (time, randomness, ordering, network,
external state controlled unless intentionally tested); diagnostic clarity; and marginal value.
Every test or cohesive group requires a PR justification; generated cases under one property may
share one justification.

> [!WARNING]
> **Empty-green tests are prohibited:** assertionless tests; swallowed exceptions; tests that
> cannot fail; assertions restating setup values; mocking the behavior under test; verifying only
> a mock call when the call is not the contract; implementation-derived expected values;
> snapshot-only proof for critical behavior; broad snapshot rewrites without semantic review;
> unjustified skips; duplicates without added detection value; framework tests presented as
> application tests; tests changed solely because production output changed; coverage-only
> tests. **A green suite is evidence only when its tests can reject wrong behavior.**

Portfolio guidance, not a mechanical gate: roughly **60%** unit or component, **30%** integration
or contract, **10%** E2E or system. For consequential R2/R3 work, plan roughly **65–75%** of
effort on verification-related activity (intent clarification, oracle and test design,
falsification, independent review, artifact inspection, recovery evidence) — never measured
through test LOC.

## Verification flow

Owner intent → release milestone → parent Issue when needed → thin implementation Issue →
behavior claims and forbidden outcomes → risk classification → test and oracle design →
independent oracle critique for R2/R3 → RED or negative control → smallest coherent
implementation → format, lint, build, static analysis → unit and component tests → integration
and contract tests → targeted property, state, differential, mutation, or fuzz testing →
security review → E2E and artifact capture → independent exact-head verification →
application-specific PR Gate → native squash auto-merge → worktree cleanup after merge → release
verification → production counterexamples feed back into Issues and tests.

**Before every PR, run fresh:** `git status --short`, `git diff --check`, `python
tools/standardctl.py verify`, `python -m unittest discover -s tests -p "test_*.py"`, and every
applicable command documented in `project.yaml`. Inspect the full diff, recent log, and `git
worktree list --porcelain`. Confirm one active writer, the correct Issue and deterministic
branch, no unrelated files, no unresolved rendering tokens, byte-identical template pairs, an
exact-head verifier result, complete required evidence, no unresolved subagent state, and that
the PR is ready, not draft.

> [!IMPORTANT]
> **Oracle-change firewall.** Every PR discloses removed tests, weakened assertions, changed
> expected values, redefining fixture changes, broadened snapshots, new skips or ignores, reduced
> verification scope, coverage exclusions, changed test commands, changed CI or security
> behavior, changed permission boundaries, and changed runtime invariants — **or states "None."**
> An implementation agent **must not** silently weaken an oracle. A semantic oracle change
> requires behavioral justification, a linked acceptance criterion or owner override, independent
> review for R2/R3, and explicit PR disclosure.

## Evidence and artifacts

When a change affects visible UI behavior, passing E2E execution must produce screenshots named
`<claim-id>--<scenario>--<viewport>--<state>.png`, each mapped to a behavior claim. Non-visual
behavior requires the relevant artifact instead: request/response or contract report, migration
dry-run and verification report, corpus or crash report, benchmark report, security test report,
state or race report. For E2E failures, preserve the applicable screenshot, trace, video,
console, network log, report, and environment metadata — **uploaded even when the job fails.**
Commit screenshots only as intentional visual-regression baselines; per-run artifacts live in
`.evidence/` during execution and are never committed.

Every artifact bundle contains `.evidence/manifest.json` (schema_version 1) recording repository,
application, Issue, PR, milestone, exact head and base SHAs, run id, timestamp, provider roles,
commands with exit codes, environment, claims with results and evidence files, per-file type and
SHA-256, and a pass/fail summary. Validation fails on a head that is not the PR's exact tested
head, missing files, digest mismatches, uncovered claims, UI claims without valid screenshots,
unknown artifact types, or unauthorized skipped claims.

Upload with the exact pinned upload-artifact action, `if: always()`, `if-no-files-found: error`,
90-day retention, and a name carrying the application slug, Issue number, PR number, short exact
head, and evidence type. Record artifact id, URL, digest, run URL, exact head, and expiration.
**Never expose secrets, tokens, or private data in artifacts.** Maintain exactly one managed
Evidence Index comment (marker `<!-- agent-engineering-standard:evidence-index:v1 -->`) on the PR
and on its Issue, updated for every new head — an index, not the authoritative binary store.
Direct image attachments may be added for convenience but never replace the verified Actions
artifact. Publish selected final release evidence as a GitHub Release asset after release
verification.

## Lean engineering

Optimize for **minimum accidental complexity**, not minimum raw LOC. Require: precise domain
names exposing units and side effects; stable responsibility boundaries; shallow, meaningful
folders; one conceptual level per method; minimal exported surface; direct implementation before
abstraction; no speculative extension points; deletion of dead code exposed by the change;
comments explaining reasons or constraints; one source of truth per concept; consolidation of
duplicated concepts; small coherent diffs; no unrelated cleanup. Avoid generic names such as
`misc`, `common`, `helpers`, `utils`, `manager`, `processor`, `data`, `thing`, `temp` unless
narrowly scoped and genuinely accurate. **Do not enforce arbitrary global limits** on LOC, file
length, function length, file count, or folder depth.

Each PR's Lean review reports: changed-file count; additions and deletions; new files, folders,
and top-level directories; largest changed files; newly exported APIs; duplication introduced or
removed; dead code removed; consolidation decisions; simpler alternatives considered; remaining
accidental complexity. New permanent top-level folders require a durable responsibility and PR
justification.

## Documentation and handoff

Keep `README.md`, `AGENTS.md`, `project.yaml`, and the templates consistent with actual behavior
**in the same PR as the change.** Canonical templates live under `TEMPLATES/`; the GitHub-active
copies (`.github/ISSUE_TEMPLATE/work-item.md`, `.github/ISSUE_TEMPLATE/config.yml`,
`.github/PULL_REQUEST_TEMPLATE.md`) must stay byte-identical to their canonical sources, and the
PR Gate compares each pair. Provider adapters `CLAUDE.md` and `GEMINI.md` contain only the import
line; never duplicate policy inside an adapter. Codex reads `AGENTS.md` directly.

When stopping before a PR exists, populate the Issue's Handoff section: branch, exact head,
completed, remaining, current failure, last verified command, exact next command. **Once a PR
exists, the PR is the handoff.**

## PR Gate and merge behavior

The **sole required status check** is the final aggregator job `Agent Engineering Standard PR
Gate` (in consuming repositories, `<Application> PR Gate`). The required workflow uses the
mandated pull_request triggers plus push and manual dispatch, has no path filters, explicit
read-only permissions, SHA-pinned actions with version comments, and no inapplicable stage
represented as an empty success. The final aggregator runs with `if: always()`, depends on every
applicable job, fails unless every required dependency concluded exactly `success` (rejecting
failure, cancelled, skipped, neutral, or missing), verifies the tested SHA equals the current PR
head, and publishes a concise summary. Agents create **ready PRs — never drafts, never converting
to draft;** incomplete work remains on the branch until ready, and a failing gate represents
incomplete or invalid work. Unauthorized drafts are nonpersistent under repository automation; a
valid owner-applied `owner:allow-draft` preserves a draft.

The **Merge Policy workflow** is operational metadata automation, **not a required status:** it
never checks out, fetches, downloads, or executes PR-controlled code or artifact content, never
direct-merges, never submits reviews, and maintains only the managed Work State and Evidence
Index comments plus owner-requested comments. For ready same-repository PRs to `main` it verifies
protection, validates owner-label provenance, honors valid `owner:hold-merge`, updates the branch
when safely possible, never resolves real conflicts automatically, enables native squash
auto-merge bound to the expected head, re-arms it when disabled without an owner hold, and never
bypasses the gate.

`main` protection (ruleset `Agent Engineering Standard Main Protection`): pull request required,
squash only, linear history, no force push, no deletion, zero general approvals, code-owner
approval only for control-plane files (`.github/CODEOWNERS`, `.github/workflows/`,
`tools/standardctl.py`, `project.yaml`, and the TEMPLATES machine files), strict up-to-date
required status, owner bypass, no second required machine check. Sequence required-check changes
so the required context always matches a check that actually reports. **Read live settings back
after applying them** — never treat a write response or committed JSON template as verification
of live state.

**Path-scoped gates in monorepo topologies:** a legitimate monorepo may deviate from the single
no-path-filter aggregator with owner authorization, splitting the gate into multiple
independently path-scoped workflows (one per app or service).

> [!WARNING]
> GitHub's required-status-checks model blocks on any required check name that never reports; a
> `paths:` filter does **not** make an unreported required check "not applicable" to GitHub — it
> stays pending forever, and the PR cannot merge without an owner administrative bypass. A
> required check is therefore only safe under this model when it either carries no `paths:`
> filter (so it reports on every PR) or is engineered to always report — an always-triggering
> wrapper job whose internal work is skipped when its own paths did not change. Do not mark a
> path-filtered gate required without one of those two properties. Where hard enforcement of
> every path-scoped gate is not worth that restructuring, keep the path-scoped gates running and
> visible but non-required, and rely on at least one always-triggering required check (a
> repo-wide secret scan, a structural policy check, or both) for the required-status-check gate.

## Agent boundaries

Agents **may**, only when the task explicitly authorizes them: create work artifacts — Issues,
branches, commits, pull requests, descriptions, code, tests, and documentation.

Agents **must not:** submit reviews, request reviewers, approve changes, block a pipeline, post
unsolicited comments, push implementation directly to `main`, bypass a failing PR Gate, weaken a
test or oracle merely to obtain green status, use administrative bypass without explicit owner
authorization, store credentials in the repository, claim a live setting without reading it back,
claim completion without fresh verification evidence, create automatic fleet-wide propagation, or
introduce a second work tracker. An agent may answer a direct question when explicitly tagged in
an Issue or pull request.

Adoption by other repositories is explicit, Issue-backed, pinned to an exact standard commit via
`standard.lock`, independently verified, and owner-controlled — **never automatic.** A
repository's reference to this standard is informational; repository-specific instructions take
precedence there.

## Completion standard

Work is complete only with **fresh evidence at the exact head:** every acceptance criterion
satisfied; local verification and tests green; the PR Gate green on the exact tested head;
required artifacts uploaded, digested, and indexed; independent verification recorded for R2/R3;
worktree and subagent state reconciled with no `UNKNOWN` writer; no silently weakened oracle; and
the Issue closed by the merged PR.

> [!IMPORTANT]
> Never report completion while any required verification, cleanup, or acceptance criterion
> remains unresolved. **Do not substitute confidence for evidence.**
