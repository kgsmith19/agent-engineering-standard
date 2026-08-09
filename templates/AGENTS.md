# Agent Operating Instructions

This repository follows `kgsmith19/agent-engineering-standard`, pinned in `.agent/standard.lock`.

This file is the authoritative behavioral contract for all automated agents operating in this repository:
GitHub Copilot (chat, editor, coding agent), Claude Code, and ChatGPT GitHub connector.
**Every rule below is mandatory. No rule may be skipped, reordered, or weakened.**

---

## SECTION 1 — BEFORE YOU DO ANYTHING

Read in this order. Stop if a required file does not exist; create it before proceeding.

1. `PRD.md` — product purpose, outcomes, requirements, out-of-scope items.
2. `specs/` — behavioral contracts for the area you are changing (if the directory exists).
3. `docs/adr/` — consequential architecture decisions that constrain your implementation.
4. The GitHub Issue assigned to you — your exact task scope.
5. `AGENTS.md` — this file. Re-read it if you have been idle.

Do not implement anything until you have read all applicable files above.

---

## SECTION 2 — RISK CLASSIFICATION

Classify every change before you write code. Use the scale below. You may raise a classification; you may never lower it.

| Level | Definition |
|-------|-----------|
| R0 | Non-behavioral: docs, comments, formatting, renaming only |
| R1 | Local reversible behavior: internal logic, unit-tested only |
| R2 | Normal product/API change: new feature, refactor with tests |
| R3 | Sensitive boundary: auth, PII, external I/O, migrations, secrets, CI/merge policy |
| R4 | High-consequence: destructive, financial, privileged, or irreversible action |

Label the PR with `risk:R<N>` before opening it.

**R4 rule:** R4 work never auto-merges. Open the PR, complete all gates, then stop. Do not enable or request auto-merge. Human authorization is required before merge.

**Control-plane rule:** Any change to `.github/workflows/`, `policy/`, `scripts/apply-github-standard.ps1`, or `scripts/doctor.ps1` is at minimum R3 and is treated as a control-plane change. Control-plane PRs are manually merged by the repository owner. Do not enable auto-merge on control-plane PRs.

---

## SECTION 3 — BRANCH NAMING (MANDATORY)

Use the exact format below. Deviations cause AI Review provenance detection to fail, which blocks auto-merge.

| Initiator | Branch format |
|-----------|---------------|
| Claude Code agent | `agent/claude/<issue-number>-<short-description>` |
| ChatGPT / Codex agent | `agent/codex/<issue-number>-<short-description>` |
| Copilot coding agent | `agent/copilot/<issue-number>-<short-description>` |
| Human or unknown | `fix/<issue-number>-<short-description>` or `feat/<issue-number>-<short-description>` |

`<short-description>` uses lowercase kebab-case. Maximum 50 characters total for the description segment.

---

## SECTION 4 — ISSUE PROCESSING (MANDATORY BEFORE ANY CODE)

When assigned an Issue:

1. Read the Issue body in full.
2. Decompose it into Markdown checkboxes. Each checkbox is one independently verifiable action. Format: `- [ ] <verb> <object> so that <verifiable outcome>`.
3. Link each checkbox to the relevant source file, spec, or doc reference.
4. Post the decomposed checklist as a comment on the Issue before opening any branch or writing any code.
5. Work checkboxes one at a time. Check each box (`- [x]`) only after the corresponding test or verification passes in CI, not before.

---

## SECTION 5 — IMPLEMENTATION RULES

1. Work one thin slice at a time. A slice is the smallest change that produces independently verifiable value.
2. Keep the PR draft while implementation is in progress. Only mark ready when local verification is complete.
3. Never modify an evaluator, required check, or merge policy within the same PR that uses those controls to approve itself.
4. Do not add dependencies, abstractions, or features outside the Issue scope.
5. Write tests before or alongside implementation, not after. Tests must fail for the right reason before the implementation makes them pass.
6. Never weaken, skip, delete, or comment-out tests to obtain a passing CI run.
7. Do not suppress linter errors or type errors with inline ignore directives unless the Issue explicitly authorizes it and the suppression is documented in the PR body.
8. Every function, module, or service you create must be reachable by a test that would fail if you deleted it.

---

## SECTION 6 — PULL REQUEST REQUIREMENTS

Complete every field in the PR template. A PR with missing required fields must not be marked ready.

Required PR body fields:
- `Issue`: the linked Issue number(s)
- `Risk`: R0 / R1 / R2 / R3 / R4
- `Summary`: one sentence describing what changed and why
- `Verification`: exact commands or CI check names that prove correctness
- `Manual gate` (R3/R4 only): four-field justification (failure class, why automation is insufficient, decision owner, removal condition)

After opening the PR:

1. Confirm the branch name matches Section 3.
2. Confirm CI (`PR Gate`) triggers immediately. If it does not trigger within 2 minutes, investigate the workflow file before continuing.
3. Do not push additional commits while CI is running unless you have identified and fixed the failing cause. Unnecessary pushes burn AI Review budget.

---

## SECTION 7 — CI FAILURE HANDLING (AUTO-FIX LOOP)

When `PR Gate` fails:

**Step 1 — Classify the failure.** Inspect the full CI log. Classify the failure as one of:

- `SPEC`: the requirement or test is wrong
- `IMPL`: your code is wrong
- `ENV`: missing dependency, infrastructure, or environment variable
- `FLAKY`: non-deterministic failure unrelated to your change
- `POLICY`: a gate or policy your change violates that you must not bypass

**Step 2 — Act based on classification:**

| Classification | Required action |
|----------------|-----------------|
| `IMPL` | Fix the code. Push. Do not disable or modify the failing test. |
| `SPEC` | Do not fix silently. Post a comment on the PR explaining the conflict. Tag the Issue. Wait for Issue owner clarification before proceeding. |
| `ENV` | Fix the environment configuration (install, secret, variable). Do not hardcode credentials. |
| `FLAKY` | Re-trigger CI once. If it fails again with the same error, treat as `IMPL`. |
| `POLICY` | Do not bypass the policy. Post a comment describing the conflict. Escalate to the repository owner. |

**Step 3 — After fixing and pushing:**

- Wait for the new CI run to complete before pushing again.
- If `PR Gate` fails on the same check three consecutive times with the same error after genuine fix attempts, stop the loop. Post a comment on the PR: `CI-BLOCK: <check name> has failed <N> times after fix attempts. Manual review required.` Then stop working on this PR until a human responds.

**Maximum auto-fix iterations: 3 per unique failing check.**

---

## SECTION 8 — AI REVIEW GATE

After `PR Gate` passes, the `AI Review` gate must pass before auto-merge is possible.

The AI Review gate is automatically triggered by the repository's `ai-review.yml` workflow. You do not need to manually request it in most cases. The workflow:

1. Detects your branch prefix to determine your provider (Section 3).
2. Routes the review request to the required cross-provider reviewer.
3. Posts the review result as a check on the exact head SHA.

**If `AI Review` fails:**

- Read the review findings in full.
- Address every finding that is a genuine defect (not a false positive).
- Push the fix. The gate re-evaluates automatically on the new head SHA.
- If you believe a finding is a false positive, post a comment explaining why. Do not push empty commits or cosmetic changes to re-trigger the gate.
- You get a maximum of 1 re-review pass after substantive fixes. After that, escalate.

**If `AI Review` is stuck in `pending` for more than 15 minutes:**

- Check that the `ai-review.yml` workflow ran on the current head SHA.
- If it did not run, post a comment: `AI-REVIEW-STALL: workflow did not trigger on SHA <sha>. Manual trigger required.`

---

## SECTION 9 — PR STATE MACHINE (ALL CASES)

### 9A — Draft PR
**Condition:** PR is marked draft.
**Action:** Continue implementation. Do not request AI review. Do not enable auto-merge. Do not push more than necessary. Mark ready only when local verification is complete.

### 9B — Ready PR, CI pending
**Condition:** PR is ready, `PR Gate` is running.
**Action:** Wait. Do not push. Do not modify the PR.

### 9C — Ready PR, CI passing, AI Review pending
**Condition:** `PR Gate` passes, `AI Review` pending or not yet triggered.
**Action:** Wait up to 15 minutes. If not triggered, see Section 8 stall handling.

### 9D — Ready PR, both gates passing
**Condition:** `PR Gate` passes and `AI Review` passes on the same head SHA, review threads resolved, risk ≤ R3, no justified manual gate.
**Action:** Auto-merge proceeds automatically. Do not take further action.

### 9E — Ready PR, CI failing
**Condition:** `PR Gate` fails.
**Action:** Execute Section 7 auto-fix loop immediately.

### 9F — Ready PR, AI Review failing
**Condition:** `PR Gate` passes, `AI Review` fails.
**Action:** Execute Section 8 failure handling.

### 9G — Open review thread blocking merge
**Condition:** Auto-merge armed but review threads unresolved.
**Action:** Read each thread. Resolve threads where the finding has been addressed by a commit. For unresolved genuine findings, implement the fix and push. Never resolve a thread without addressing the finding or explicitly documenting why it is a false positive.

### 9H — R4 PR
**Condition:** Risk classification is R4.
**Action:** Complete all CI and AI Review gates. Then stop. Post comment: `R4-GATE: All automated gates pass. Manual authorization required before merge.` Do not enable auto-merge. Do not merge.

### 9I — Control-plane PR
**Condition:** PR modifies `.github/workflows/`, `policy/`, or gate-enforcement scripts.
**Action:** Complete all CI and AI Review gates. Then stop. Post comment: `CONTROL-PLANE-GATE: All automated gates pass. Manual merge required by repository owner.` Do not enable auto-merge. Do not merge.

### 9J — Closed PR (not merged)
**Condition:** PR is closed without merge.
**Action:** Read the closing comment or reason. If the Issue is still open and the work is still valid, open a new branch following Section 3 naming. Do not reopen the closed PR. Do not re-use the old branch.

### 9K — Dependabot PR
**Condition:** PR is authored by `dependabot[bot]`.
**Action:** Do not modify Dependabot PRs. They follow their own update schedule. If a Dependabot PR blocks your work due to a conflict, update your branch from main and resolve the conflict in your branch. If a Dependabot PR introduces a vulnerability, post a comment on it tagging the Issue owner. Do not merge Dependabot PRs manually.

### 9L — Stale PR (no activity for 7 or more days)
**Condition:** PR has had no commits, comments, or CI activity for 7 or more days.
**Action:** Update the branch from main. Re-trigger CI. If the Issue is still valid, continue work. If the Issue has been closed or superseded, close the PR with a comment explaining why.

### 9M — Merge conflict
**Condition:** GitHub reports a merge conflict on the PR.
**Action:** Fetch the latest main. Resolve all conflicts in your branch. Do not force-push to main. Do not accept "ours" blindly — read each conflicting hunk and apply the semantically correct resolution. Push the resolved branch. CI re-runs automatically.

### 9N — Ambiguous branch (human or unknown initiator)
**Condition:** Branch prefix does not match any agent prefix in Section 3.
**Action:** The AI Review gate requires both Codex and Copilot to pass (dual-provider policy for ambiguous provenance). Both reviews must complete on the exact head SHA before auto-merge is eligible.

---

## SECTION 10 — ESCALATION (WHEN TO STOP AND WAIT)

Stop work and post an escalation comment on the Issue or PR when:

1. `PR Gate` fails on the same check 3 or more times after genuine fix attempts.
2. A failure classification is `SPEC` or `POLICY`.
3. Risk is R4 and all automated gates have passed.
4. The PR is a control-plane change and all automated gates have passed.
5. `AI Review` fails with a finding you cannot resolve without changing scope.
6. A Dependabot PR introduces a vulnerability that blocks your work.
7. A required secret, environment variable, or permission is missing and you cannot add it within least-privilege scope.

Escalation comment format:

```
ESCALATION: <one-sentence problem statement>
Blocker type: <CI-FAIL | SPEC-CONFLICT | POLICY-CONFLICT | R4-GATE | CONTROL-PLANE-GATE | MISSING-PERMISSION | AI-REVIEW-UNRESOLVABLE>
Last action taken: <what you did last>
Required human action: <exactly what you need the human to do>
```

Do not continue working on blocked items. Move to another Issue if available. Do not fabricate progress.

---

## SECTION 11 — WHAT YOU MUST NEVER DO

1. Modify a test, evaluator, required check, or CI configuration to make a failing check pass.
2. Enable or request auto-merge on R4 or control-plane PRs.
3. Resolve a review thread without addressing or documenting the finding.
4. Use `--force` or `--force-with-lease` on the default branch.
5. Merge a PR without both `PR Gate` and `AI Review` passing on the same head SHA.
6. Submit a review from the same provider that implemented the code (self-review does not satisfy the AI Review gate).
7. Push credentials, secrets, tokens, or API keys to any file.
8. Claim completion before CI is green and the AI Review gate has passed.
9. Reuse a branch after its PR is closed.
10. Loop indefinitely on a failing check. Maximum 3 auto-fix attempts per unique failure, then escalate.

---

## Code review rules (for reviewer agents)

- Flag requirement/spec mismatches even when tests pass.
- Flag tests that can pass without proving the behavior they claim to prove.
- Flag weakened authority/security/evaluator boundaries and unnecessary scope/complexity.
- For UI changes, confirm important user-visible behavior is covered by an appropriate Playwright journey or explicitly justified stronger evidence.
