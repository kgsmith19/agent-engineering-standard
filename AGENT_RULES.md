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

Keep a PR draft while implementation is still changing. Run the repo's local/fast verification during slices, then mark the coherent PR ready so the independent `PR Gate` runs.

**The implementing agent must request a different review agent after the final substantive push.** Do not leave reviewer selection as a human reminder. Use the shared review router when available; otherwise perform the equivalent bounded handoff and record the reviewer provider.

Every auto-merged PR needs a current-head independent AI review. Independence means the reviewer provider did not implement the PR and the reviewer did not inherit the implementation session/context.

Default routing:

- Claude implementation → Codex GitHub review
- Copilot implementation → Codex GitHub review
- Codex implementation → one Copilot review; use a fresh Claude session/model/context only if Copilot is unavailable
- human/unknown implementation → Codex by default

The default reviewer performs **one batched multi-lens pass** rather than spawning several paid reviewers:

1. software correctness/security
2. business/product outcome and ROI
3. business systems/operational optimization
4. leanness/complexity/dead-code/manual-toil review

A second semantic reviewer is justified only when the first review finds material ambiguity, the risk model requires stronger independence, or the primary reviewer is unavailable.

Cost rules:

- deterministic checks run before LLM review
- Codex is primary; local deep review defaults to `gpt-5.4-mini`
- at most 2 Codex reviews per PR: initial + one post-fix re-review
- Copilot is fallback-only, low effort, at most 1 review per PR
- do not enable Copilot review-on-push or draft review by default
- do not repeatedly pay for a reviewer because implementation was pushed in noisy micro-commits; keep active work draft and request review after the final substantive push

R0–R3 may auto-merge only after the current head has an independent AI review, required `PR Gate` is live/enforced, and review threads are resolved. Control-plane changes are at least R3; they are not forced through a human approval merely because they are important.

R4 never auto-merges. The manual gate is authorization for destructive/financial/privileged/irreversible consequence, not a substitute for technical review.

## 7. Manual gates must earn their existence

Never add or preserve a manual gate merely because work is "important", "sensitive", or traditionally reviewed by a person.

Every manual gate must state all four:

1. **failure class prevented** — the concrete bad outcome
2. **why automation is insufficient today** — the missing signal/capability, not a vague trust claim
3. **decision owner** — who has the authority the machine lacks
4. **gate removal condition** — the measurable condition that lets us automate/delete the gate

If any field is missing, the gate is unjustified and should be removed or replaced with objective automation.

Manual review is not automatically required for R3. Prefer independent AI review + deterministic controls. Use a manual gate only when a real authority/intent decision cannot yet be safely derived or bounded.

## 8. Turn manual toil into system improvement

When an agent or human performs a manual workaround, ask whether the same work could recur.

- If the automation is small, safe, and in scope: automate it now.
- Otherwise record one concise automation/research candidate with the observed problem, evidence/frequency, current human cost, research needed, smallest experiment, expected payoff, and deletion/expiry condition.
- Do not create idea landfill. A candidate without evidence, plausible ROI, or a next experiment is discarded.

Repeated manual work must not become normal merely because an agent can keep doing it.
