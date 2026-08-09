# Agent Rules

## Goal

Produce correct, useful software with minimum human attention, rework, cost, and unnecessary code.

## 1. Work small

Work one thin slice at a time.

Before coding:

1. read only relevant product/work context
2. define what proves the slice correct
3. keep the change inside that scope

Do not implement a whole large feature when a smaller valuable slice exists.

## 2. Prefer minimum correct implementation

Priority:

**Correct → Simple → Deterministic → Observable → Maintainable → Clever**

Avoid speculative abstractions, unrelated refactors, unnecessary dependencies, future features, and scope expansion without evidence.

## 3. Do not game the system

Never obtain GREEN by weakening/deleting tests, skipping required checks, lowering thresholds, hiding errors, or changing the evaluator/policy judging the current run.

If the specification/evaluator appears wrong, report the conflict instead of bypassing it.

## 4. Verify completion

Writing code is not completion. Claim completion only when applicable independent evidence passes. State exactly what remains unverified when full verification is impossible.

## 5. Retry intelligently

Before retrying, classify the failure as specification/oracle, implementation, environment/dependency, flaky test, missing context, permissions/policy, or tool/infrastructure.

Do not repeat the same failing strategy indefinitely. Escalate consequential ambiguity rather than forcing a result.

## 6. Independent review and merge

Keep a PR draft while implementation is changing. Run fast local verification during slices, then mark the coherent PR ready.

<<<<<<< HEAD
Every automated merge requires two independent GitHub integration gates on the **latest head SHA**:

1. `PR Gate` — deterministic repo-specific evidence
2. `AI Review` — current-head semantic review from a different implementation provider

A later push creates a new head SHA and therefore invalidates the prior `AI Review` result. Auto-merge may remain armed, but GitHub cannot merge until the new head receives a successful `AI Review` check.

Implementation provenance is attested by GitHub Actions, not trusted from an editable PR-body claim:

- controlled local agents use `agent/<provider>/<work>` branches
- legacy Claude/Copilot cloud branches may use their recognized provider prefix/author
- human work may declare `Implementer: human`
- unknown provenance fails closed

Default connected reviewer routing:

- Claude implementation → Codex review
- Copilot implementation → Codex review
- Codex implementation → one Copilot review
- human implementation → Codex by default
=======
Every automated merge requires two GitHub integration gates on the **latest head SHA**:

1. `PR Gate` — deterministic repo-specific evidence
2. `AI Review` — required provider-specific semantic evidence for the exact head

A later push creates a new head SHA and invalidates the prior semantic authorization. Auto-merge may remain armed, but GitHub cannot merge until the new head receives a successful `AI Review` check.

Agent provenance is mechanical, not trusted from editable PR prose:

- ChatGPT work: `agent/chatgpt/<work>`
- Codex work: `agent/codex/<work>`
- Claude work: `agent/claude/<work>` or recognized legacy Claude cloud branch
- Copilot work: `agent/copilot/<work>` or recognized Copilot branch/author
- ordinary/user-authored branches are ambiguous for independence and therefore need both connected reviewer providers for unattended merge

Default required reviewer routing:

- ChatGPT implementation → Copilot
- Claude implementation → Codex
- Copilot implementation → Codex
- Codex implementation → Copilot
- ambiguous/user-authored provenance → Codex + Copilot
>>>>>>> origin/main

Do not claim a fresh-Claude fallback until a mechanical Claude review adapter exists.

The default semantic reviewer performs **one batched multi-lens pass**:

1. software correctness/security
2. business/product outcome and ROI
3. business systems/operational optimization
4. leanness/complexity/dead-code/manual-toil review

<<<<<<< HEAD
A second semantic pass is justified only after substantive fixes, unresolved ambiguity, or provider fallback.
=======
A second semantic pass is justified only after substantive fixes, unresolved ambiguity, or when ambiguous provenance requires the second connected provider.
>>>>>>> origin/main

Cost rules:

- deterministic checks before LLM review
<<<<<<< HEAD
- Codex primary; local deep review defaults to `gpt-5.4-mini`
- max 2 Codex passes per PR: initial + one post-fix re-review
- Copilot fallback max 1 review per PR, low effort
- no default draft review or unlimited review-on-push spending
=======
- Codex primary for Claude/Copilot/ambiguous work; local deep review defaults to `gpt-5.4-mini`
- max 2 Codex response passes per PR: initial + one post-fix re-review
- max 1 Copilot response pass per PR, low effort
- no default draft review or unlimited review-on-push spending
- per-head request markers prevent duplicate requests
>>>>>>> origin/main
- active implementation stays draft so noisy micro-pushes do not consume semantic review budget

R0–R3 may auto-merge only when both required gates are enforced, review threads are resolved, and no justified manual authority gate applies. Control-plane changes remain manually merged while they can alter the evaluator that judges themselves.

R4 never auto-merges. Its manual step authorizes destructive/financial/privileged/irreversible consequence; it is not a substitute for technical review.

## 7. Manual gates must earn their existence

Never add or preserve a manual gate merely because work is "important", "sensitive", or traditionally reviewed by a person.

Every manual gate must state all four:

1. **failure class prevented** — concrete bad outcome
2. **why automation is insufficient today** — missing signal/capability, not vague trust
3. **decision owner** — who has authority the machine lacks
4. **gate removal condition** — measurable condition that lets us automate/delete it

If any field is missing, the gate is unjustified and should be removed or replaced with objective automation.

## 8. Turn manual toil into system improvement

When an agent or human performs a manual workaround, ask whether it can recur.

- If automation is small, safe, and in scope: automate it now.
- Otherwise record one concise automation/research candidate with problem, evidence/frequency, human cost, research needed, smallest experiment, expected payoff, and deletion/expiry condition.
- Discard candidates without evidence, plausible ROI, or a next experiment.

Repeated manual work must not become normal merely because an agent can keep doing it.

## 9. Isolated worktrees and parallel subagents

### Isolation

Every write-capable task runs in one isolated worktree tied to its Issue or slice.

- Prefer the harness-native worktree when the execution environment provides one.
- Fall back to `.worktrees/<branch>` only when no harness-native worktree is available.
- Never share a worktree or working directory between concurrent write agents.

### Parallel subagents

- **Read-only** investigations and reviews may fan out to parallel subagents with isolated context; no worktree coordination needed.
- **Parallel write agents** are allowed only when file scopes are provably disjoint and each agent has its own worktree and branch.
- One coordinator integrates results and runs the final full verification.
- Default parallelism bound is **3**. The coordinator must provide evidence of benefit before exceeding it.

### Cleanup

- Worktrees and branches created by an agent must be removed after the work is merged or abandoned.
- The portfolio cleanup script (`scripts/prune-portfolio.ps1`) prunes stale worktree metadata and deletes merged branches; dirty or unique worktrees/branches are reported, never destroyed.
- Open PR branches and Dependabot branches are never touched by automated cleanup.

### Scratch state

`.worktrees/` and `.superpowers/` are local scratch directories and must not be committed. Every repo bootstrapped from this standard excludes them via `.gitignore`.
