# Agent Collaboration Comment Templates

Templates for structured dev-agent and reviewer-agent collaboration.

## Reviewer: Initial Review

```markdown
<!-- agent-collaboration:review-round:1 -->

## Code Review — Round 1

**Reviewer:** @hyperbolic-core-reviewer
**PR:** #{{PR_NUMBER}}
**Commit:** {{HEAD_SHA}}

### Finding 1: {{FINDING_NAME}}

- **Severity:** {{suggestion|concern|blocker-candidate}}
- **Location:** `{{FILE}}:{{LINE}}`
- **Current:**
  ```{{LANGUAGE}}
  {{CODE_QUOTE}}
  ```
- **Suggestion:** {{RECOMMENDED_CHANGE}}
- **Rationale:** {{WHY_THIS_MATTERS}} (per `AGENTS.md` §{{SECTION}})
- **Objective criteria:** {{TESTABLE_OUTCOME}}

---

### Finding 2: ...

---

**Summary:** {{TOTAL_FINDINGS}} findings ({{SEVERITY_BREAKDOWN}})
**Status:** ⏳ Awaiting dev-agent response
**Iteration:** 1/10
**Next:** Dev-agent to respond or implement changes
```

## Dev: Response

```markdown
<!-- agent-collaboration:dev-response:round:1 -->

## Developer Response — Round 1

**Developer:** @hyperbolic-core-dev
**PR:** #{{PR_NUMBER}}
**Responding to:** Review Round 1

### Response to Finding 1: {{FINDING_NAME}}

**Decision:** {{implemented|alternative-solution|question|disagree}}

**Proposed Solution:**
{{IMPLEMENTATION_OR_COUNTER_ARGUMENT}}

**Why this achieves the objective:**
- {{JUSTIFICATION_1}}
- {{JUSTIFICATION_2}}

**Evidence:**
- {{TEST_OUTPUT_OR_SPEC_REFERENCE}}
- Commit: {{NEW_SHA}}

---

### Response to Finding 2: ...

---

**Summary:** {{IMPLEMENTED_COUNT}} implemented, {{QUESTION_COUNT}} questions, {{DISAGREE_COUNT}} disagreements
**Status:** ⏳ Awaiting reviewer reassessment
**Iteration:** 1/10
**Next:** Push commit {{NEW_SHA}}, re-trigger reviewer
```

## Reviewer: Reassessment

```markdown
<!-- agent-collaboration:review-round:2 -->

## Code Review — Round 2 (Reassessment)

**Reviewer:** @hyperbolic-core-reviewer
**PR:** #{{PR_NUMBER}}
**Commit:** {{NEW_HEAD_SHA}}

### Finding 1: {{FINDING_NAME}} — **{{ACCEPTED|REVISION_NEEDED|CLARIFICATION}}**

**Developer's solution:** {{QUOTE_DEV_RESPONSE}}

**Assessment:**
- {{EVALUATION_AGAINST_CRITERIA}}
- {{VERIFICATION_OF_TESTS}}
- {{CHECK_SPEC_ALIGNMENT}}

**Outcome:**
- [x] ✅ **Accepted** — Objective criteria met
- [ ] 🔄 **Revision requested** — {{SPECIFIC_GAP}}
- [ ] ❓ **Clarification needed** — {{QUESTION}}

---

**Summary:** {{ACCEPTED}} accepted, {{REVISION}} need revision, {{QUESTIONS}} questions
**Status:** {{awaiting-dev|resolved|escalating}}
**Iteration:** 2/10
**Next:** {{NEXT_ACTION}}
```

## Escalation (Round 10+)

```markdown
<!-- agent-collaboration:escalation -->

## 🚨 Escalation to Owner

**Issue:** Reviewer and dev-agent could not reach agreement after 10 iterations.

**PR:** #{{PR_NUMBER}}
**Commit:** {{HEAD_SHA}}
**Iterations:** 10

### Points of Disagreement

1. **Finding: {{NAME}}**
   - Dev proposes: {{DEV_SOLUTION}}
   - Reviewer prefers: {{REVIEWER_ALTERNATIVE}}
   - Rationale for disagreement: {{REASON}}

2. **Finding: {{NAME}}** ...

### Evidence Submitted

**Developer's case:**
- {{DEV_BEST_EVIDENCE}}
- Test output: {{TEST_LINK}}
- Spec reference: {{SPEC_QUOTE}}

**Reviewer's case:**
- {{REVIEWER_BEST_EVIDENCE}}
- Standard reference: `AGENTS.md` §{{SECTION}}
- Counter-example: {{EXAMPLE}}

### Request for Owner Decision

@{{OWNER}} — Please decide the way forward:

1. ✅ **Approve dev's solution** (commit {{DEV_SHA}})
2. 🔄 **Require reviewer's alternative** (specify changes)
3. 🆕 **Alternative direction** (provide guidance)

**Waiting for owner manual decision.**

---

**Status:** ⏸️ BLOCKED — Awaiting owner
**Escalated:** {{TIMESTAMP}}
```

## Agreement Confirmation

```markdown
<!-- agent-collaboration:acceptance -->

## ✅ Agreement Reached

**PR:** #{{PR_NUMBER}}
**Iteration:** {{N}}/10
**All findings:** RESOLVED

### Summary

All {{TOTAL_FINDINGS}} findings from initial review have been addressed:
- {{IMPLEMENTED}} implemented by dev
- {{ACCEPTED_ALT}} alternative solutions accepted
- {{CLARIFIED}} clarifications resolved

**Verification:**
- ✅ All tests passing: {{TEST_RUN_URL}}
- ✅ No regressions in suite
- ✅ Spec references verified
- ✅ Objective criteria met

**Reviewer recommendation:** ✅ **Approve PR for merge**

---

**Status:** ✅ COMPLETE
**Ready for:** Merge after gate passes
```

## Question/Clarification

```markdown
<!-- agent-collaboration:question -->

**Question for {{reviewer|dev}}:**

{{QUESTION_TEXT}}

**Context:**
{{WHY_THIS_MATTERS}}

**Our disagreement stems from:**
{{INTERPRETATION_A}} vs. {{INTERPRETATION_B}}

**Need:**
{{WHAT_INFO_WOULD_RESOLVE_THIS}}
```
