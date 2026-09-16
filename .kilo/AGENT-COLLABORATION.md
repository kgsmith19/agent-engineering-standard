# Agent Collaboration Framework

**Status:** Design Phase
**Date:** 2026-09-16T16:47Z
**Scope:** Dev-agent and Reviewer-agent PR discussion patterns

---

## Overview

A structured collaboration workflow where:
- **Dev-agent** (`@hyperbolic-core-dev`) initiates code changes based on reviewer feedback
- **Reviewer-agent** (`@hyperbolic-core-reviewer`) provides suggestions and seeks agreement
- **Neither agent blocks unilaterally** — collaboration goal is objective agreement
- **Escalation at 10 iterations** — only then tag owner (`@kgsmith19`) for manual decision

---

## Collaboration Loop

### Phase 1: Initial Review

**Reviewer posts initial findings:**
```
<!-- agent-collaboration:review-v1 -->
## Review Round 1

### Finding: [Name]
- **Severity:** [suggestion/concern/blocker-candidate]
- **Location:** [File:Line]
- **Current:** [Code quote]
- **Suggestion:** [Recommended change]
- **Rationale:** [Why this matters per AGENTS.md section X]
- **Objective criteria:** [Testable outcome or standard reference]

---

**Status:** Awaiting dev-agent response
**Iteration:** 1/10
```

### Phase 2: Dev Response & Action

**Dev-agent can:**
- ✅ Implement the suggested change if it's objective and justified
- ✅ Implement a different solution if it achieves the same objective
- ✅ Ask clarifying questions with `<!-- agent-collaboration:question -->`
- ✅ Request objective evidence (failing test, spec quote, reference)
- ✅ Propose compromise solutions

**Dev-agent cannot:**
- ❌ Dismiss feedback without engagement
- ❌ Claim completion without re-testing
- ❌ Ignore objective findings from standards

**Dev posts response:**
```
<!-- agent-collaboration:dev-response:v1 -->

### Response to Finding 1: [Name]

**Proposed Solution:** [Implementation or counter-argument]

**Why this achieves the objective:**
- [Justification 1]
- [Justification 2]

**Evidence:** [Test output, spec section, or reference]

**Next step:** Pushing commit [SHA] for re-review
```

Then dev pushes a commit to the branch → triggers re-run of reviewer.

### Phase 3: Reviewer Reassessment

**Reviewer examines dev's response:**
- ✅ Accepts if objective criteria met
- ✅ Provides alternative suggestion if not satisfied
- ✅ Asks clarifying questions
- ✅ Notes areas of disagreement for escalation

**Reviewer posts:**
```
<!-- agent-collaboration:review-round:2 -->

### Review Round 2 - Reassessment

**Finding 1: [Name]**

**Developer's solution:** [Quote dev response]

**Assessment:**
- [Evaluate against objective criteria]
- [Verify test evidence]
- [Check spec/standard alignment]

**Outcome:**
- [ ] ✅ **Accepted** — Objective criteria met
- [ ] 🔄 **Revision requested** — [Specific gap]
- [ ] ❓ **Clarification needed** — [Question]

---

**Status:** [Awaiting dev-agent] [Resolved] [Escalating]
**Iteration:** 2/10
```

### Phase 4: Iteration & Re-test

After each dev response:
1. **Re-run relevant tests** → Verify the change doesn't break anything
2. **Re-run reviewer** → Reviewer examines updated code
3. **Loop repeats** unless agreement reached or iteration limit hit

---

## Escalation at Iteration 10

**If after 10 rounds of discussion:**
- Developer and reviewer cannot reach objective agreement
- **Reviewer posts escalation comment:**

```
<!-- agent-collaboration:escalation -->

## Escalation to Owner

**Issue:** Reviewer and dev-agent could not reach agreement after 10 iterations.

**Points of disagreement:**
1. [Finding X: Dev proposes Y, Reviewer prefers Z for reason A]
2. [Finding Y: Disagreement about standard interpretation]

**Evidence submitted:**
- [Dev's best case with test/spec evidence]
- [Reviewer's best case with test/spec evidence]

**Request:** @kgsmith19 — Please decide the way forward:
1. Approve dev's solution (commit [SHA])
2. Require reviewer's alternative (commit to branch)
3. Alternative direction (specify)

**Waiting for owner decision.**
```

**Owner responds:** Manual decision, applies label/comment, and work proceeds.

---

## Key Patterns

### Pattern: Question/Clarification

When either agent needs more info before deciding:

```
<!-- agent-collaboration:question -->

**Question for [reviewer/dev]:**

What is your interpretation of [Standard.Section] regarding [scenario]?

Our disagreement stems from whether [interpretation A] or [interpretation B] applies here.

[Context needed]
```

### Pattern: Agreement Confirmation

When reviewer accepts dev's solution:

```
<!-- agent-collaboration:acceptance -->

✅ **Finding X: Accepted**

Dev's solution meets the objective. Approved to proceed.

**Verification:**
- [Test X passes](link)
- [Spec reference](link)
- [No regressions in suite](link)
```

### Pattern: Re-test Evidence

Dev posts test output after implementing a fix:

```
<!-- agent-collaboration:test-evidence -->

## Test Results for Commit [SHA]

**Relevant test suite:** `npm run test -- --grep "pattern"`

```
✓ Test A: PASS
✓ Test B: PASS
✓ Test C: PASS (previously failing)
✓ No new failures
```

**Confidence:** All existing passing tests still pass. New fix resolves the issue.
```

---

## Rules for Both Agents

### Dev-Agent Constraints

1. **Cannot merge without reviewer agreement** on critical findings
2. **Must respond to every objective finding** (can challenge, implement, or ask clarification)
3. **Must provide test evidence** when claiming fix
4. **Cannot claim "LGTM" itself** — only reviewer can accept

### Reviewer-Agent Constraints

1. **Cannot directly block** — must seek dev agreement on each finding
2. **Cannot demand changes based on preference alone** — must cite AGENTS.md, spec, or test evidence
3. **Cannot ignore dev's evidence** — must address why test/spec doesn't resolve the finding
4. **Must be specific** — no vague "this doesn't feel right" comments

### Both Agents

1. **Comment format:** Always use `<!-- agent-collaboration:* -->` markers for machine-readable structure
2. **Iteration tracking:** Each round increments the counter
3. **Evidence culture:** Back every decision with testable outcomes or standard references
4. **No unilateral escalation:** Only happens at round 10

---

## Workflow Implementation

### Step 1: Dev-Agent Change Flow

```
Developer implements feature
    ↓
Push to branch (triggers gate)
    ↓
Gate runs tests
    ↓
Gate dispatches reviewer-agent for review
    ↓
Reviewer posts findings as <!-- agent-collaboration:review-v1 -->
    ↓
Developer reads findings (agent can consume PR comments)
    ↓
Developer implements changes
    ↓
Push updated commit → Loop to "Gate runs tests"
```

### Step 2: Reviewer-Agent Review Flow

```
Reviewer triggered by gate completion
    ↓
Review code against AGENTS.md, tests, specs
    ↓
Build findings list with objective criteria
    ↓
Post comment with <!-- agent-collaboration:review-round:N -->
    ↓
Wait for developer response (indicated by new commit)
    ↓
Detect new commit → Re-run review
```

### Step 3: Iteration Loop

Both agents monitor:
- **New commits** → Reviewer re-triggers
- **PR comments from peer** → Agent reads and responds
- **Iteration count** → After round 10, escalate

---

## Integration Points

### With Dev-Agent-Post Workflow

The existing `dev-agent-post-v2.yml` workflow can post review findings and dev responses directly to PRs.

### With PR Gate

After PR Gate completes, dispatch reviewer-agent for first review. On each commit, trigger re-review.

### With Owner

On iteration 10, post escalation comment tagging `@kgsmith19` with evidence and asking for decision.

---

## Success Criteria

✅ Agents can post structured comments to PRs/Issues
✅ Dev can read reviewer findings and respond with commits
✅ Reviewer can post findings and track iteration count
✅ At iteration 10, automatic escalation to owner
✅ No silent blocks — reviewer must always explain reasoning
✅ Collaboration goal is agreement, not fighting

---

## Next Steps

1. **Create agent-collaboration-comment template** (.github/COLLABORATION_TEMPLATE.md)
2. **Add reviewer findings dispatch** to pr-gate.yml
3. **Build iteration counter** in comment markers
4. **Create escalation detection** in reviewer-agent logic
5. **Test end-to-end** with small PR

---

**Owner:** @kgsmith19
**Framework Version:** 1.0
**Last Updated:** 2026-09-16T16:47Z
