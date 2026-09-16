# Verification

## Intent and Behavioral Claims

Issues state falsifiable behavior claims, invariants that must remain true, and outcomes that
must never happen, with example and boundary cases. **Evidence maps one-to-one to claims.** For
important R2/R3 behavior, obtain independent oracle critique before implementation and record at
least one sensitivity demonstration in the PR: RED before implementation, a deliberate negative
control, a plausible targeted mutation, differential comparison, a known-bad fixture, a
historical regression reproduction, fault injection, reference-model disagreement, or an
invalid-transition example. No global mutation-score target and no global coverage target;
coverage and mutation reports are diagnostic evidence only.

## Test Quality

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

## Verification Flow

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

## Evidence and Artifacts

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

## Completion Standard

Work is complete only with **fresh evidence at the exact head:** every acceptance criterion
satisfied; local verification and tests green; the PR Gate green on the exact tested head;
required artifacts uploaded, digested, and indexed; independent verification recorded for R2/R3;
worktree and subagent state reconciled with no `UNKNOWN` writer; no silently weakened oracle; and
the Issue closed by the merged PR.

> [!IMPORTANT]
> Never report completion while any required verification, cleanup, or acceptance criterion
> remains unresolved. **Do not substitute confidence for evidence.**
