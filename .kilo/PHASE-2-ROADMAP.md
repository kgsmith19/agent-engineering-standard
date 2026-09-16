# Phase 2 & 3 Integration Roadmap

## Status: Phase 1 ✅ COMPLETE

Both dev-agent and reviewer-agent workflows are fully operational and tested:
- ✅ `dev-agent-post-v2.yml` — Successfully posted comment as `@hyperbolic-core-dev`
- ✅ `reviewer-agent-post-v2.yml` — Successfully posted comment as `@hyperbolic-core-reviewer`
- ✅ `post-work-state.yml` — Ready to dispatch from merge-policy and pr-gate

---

## Phase 2: Workflow Integration (Next Steps)

### 2.1 Integrate `post-work-state.yml` into `merge-policy.yml`

**Current State:**
- `merge-policy.yml` computes Work State and Evidence Index
- Posts comments directly using repository token (`github.token`)
- Comments appear as owner account (`kgsmith19`)

**Target State:**
- `merge-policy.yml` computes Work State and Evidence Index (no change)
- Dispatches `post-work-state.yml` workflow to post comments
- Comments appear as `@hyperbolic-core-dev` using app token

**Implementation Steps:**

1. **Add dispatch step to merge-policy.yml:**
   ```yaml
   - name: Dispatch Work State posting to dev-agent
     uses: actions/github-workflow-run@v1  # or use gh CLI
     with:
       workflow_id: post-work-state.yml
       ref: main
       inputs: |
         pr_number: ${{ github.event.number }}
         issue_number: $LINKED_ISSUE
         body: $WORK_STATE_BODY
   ```

2. **Modify merge-policy logic:**
   - Extract Work State computation (already done)
   - Extract Evidence Index computation (already done)
   - Instead of calling `upsertComment()` directly, dispatch `post-work-state.yml`
   - Pass `pr_number`, `issue_number`, and `body` as workflow inputs

3. **Testing:**
   - Create a test PR
   - Verify Work State comment posts as `@hyperbolic-core-dev`
   - Verify Evidence Index comment posts as `@hyperbolic-core-dev`
   - Verify updates work (upsert behavior)

**Effort:** 30 minutes
**Risk:** Low (non-breaking change, post-work-state handles all logic)

---

### 2.2 Integrate `dev-agent-post-v2.yml` into `pr-gate.yml`

**Current State:**
- `pr-gate.yml` runs tests and gate checks
- Posts gate results via comments or workflow summary
- Uses repository token

**Target State:**
- `pr-gate.yml` runs tests and gate checks (no change)
- Dispatches `dev-agent-post-v2.yml` to post gate results
- Comments appear as `@hyperbolic-core-dev`

**Implementation Steps:**

1. **Identify all comment-posting locations in pr-gate.yml**
   - Gate pass/failure messages
   - Policy check results
   - Verification test results

2. **Replace with dispatch calls:**
   ```yaml
   - name: Post gate result to PR
     uses: actions/github-workflow-run@v1
     with:
       workflow_id: dev-agent-post-v2.yml
       ref: main
       inputs: |
         action: post_comment
         issue_number: ${{ github.event.number }}
         body: $GATE_RESULT_BODY
   ```

3. **Testing:**
   - Run pr-gate on a test PR
   - Verify gate comments post as `@hyperbolic-core-dev`
   - Verify pass/failure states are correctly posted

**Effort:** 1 hour
**Risk:** Medium (pr-gate is critical; need careful testing)

---

### 2.3 Test Real PR (#160 Stage 4)

**Current State:**
- PR #160 implemented Stage 4 (lean constitution router)
- Gate checks pass locally

**Target State:**
- Run PR #160 through the full workflow
- Verify all Work State and gate comments use dev-agent
- Monitor for any issues

**Steps:**

1. Push Phase 2 changes to main
2. Create a new test PR or re-open #160 if needed
3. Monitor workflow runs:
   ```bash
   gh run list --workflow=merge-policy.yml --limit=5
   gh run list --workflow=pr-gate.yml --limit=5
   ```
4. Verify comment posting:
   ```bash
   gh pr view <NUMBER> --json comments
   ```
5. Confirm all comments show `hyperbolic-core-dev` or `hyperbolic-core-reviewer`

**Effort:** 30 minutes (monitoring)
**Risk:** Low (observational only)

---

## Phase 3: Claude Code Agent Automation (Future)

### 3.1 Create Claude Code Agent Hooks

**Goal:** Have Claude Code agents automatically dispatch dev/reviewer agents for comments.

**Implementation:**
1. Create `.kilo/agent/dev-agent.md` — Claude Code agent that handles dev work
2. Create `.kilo/agent/reviewer-agent.md` — Claude Code agent for independent review
3. Add hooks to Claude Code plugin:
   - `PostToolUse` hook: Intercept when agent wants to post a comment
   - Delegate to `gh workflow run dev-agent-post-v2.yml` automatically
   - Return confirmation to agent

**Example Hook Behavior:**
```
Claude Code Agent (builder): "I'll post a status update"
Hook intercepts: POST comment request
Hook dispatches: gh workflow run dev-agent-post-v2.yml ...
Agent receives: Comment posted as @hyperbolic-core-dev
```

**Effort:** 2-3 hours
**Risk:** Low (optional automation layer)

---

### 3.2 Create Dispatch Wrapper Script

**Goal:** Simplify agent dispatch from Claude Code.

**Script:** `.kilo/scripts/dispatch-dev-agent.sh`
```bash
#!/bin/bash
ACTION=$1
ISSUE_NUMBER=$2
BODY=$3

gh workflow run dev-agent-post-v2.yml \
  -f action=$ACTION \
  -f issue_number=$ISSUE_NUMBER \
  -f body="$BODY"

echo "Dev agent dispatched (action: $ACTION, issue #$ISSUE_NUMBER)"
```

**Usage in Claude Code Agent:**
```bash
/dispatch-dev-agent post_comment 160 "Status update..."
```

**Effort:** 30 minutes
**Risk:** Very Low

---

## Timeline & Sequencing

| Phase | Task | Effort | Risk | Target Date |
|-------|------|--------|------|-------------|
| **2.1** | Merge-policy integration | 30 min | Low | Today |
| **2.2** | PR-gate integration | 1 hr | Medium | Today |
| **2.3** | Test real PR | 30 min | Low | Today |
| **3.1** | Claude Code hooks | 2-3 hrs | Low | This week |
| **3.2** | Dispatch wrapper | 30 min | Very Low | This week |

**Total for Phase 2:** ~2 hours
**Total for Phase 3:** ~3 hours

---

## Key Files to Modify

### Phase 2

1. `.github/workflows/merge-policy.yml`
   - Add workflow dispatch step
   - Extract Work State body to JSON/base64 for passing
   - Test upsert behavior

2. `.github/workflows/pr-gate.yml`
   - Identify all comment posting
   - Replace with dispatch calls
   - Test gate behavior

### Phase 3

1. `.kilo/agent/dev-agent.md` (new)
   - Claude Code agent definition
   - System prompt for implementation work
   - Triggering conditions

2. `.kilo/agent/reviewer-agent.md` (new)
   - Claude Code agent definition
   - System prompt for independent review
   - Triggering conditions

3. `.kilo/plugins/claude-code-hooks.md` (new)
   - Hook configuration
   - Delegation logic
   - Error handling

4. `.kilo/scripts/dispatch-dev-agent.sh` (new)
   - Wrapper for easy dispatch
   - Logging/confirmation

---

## Testing Checklist

### Phase 2.1 (Merge-Policy)
- [ ] Create test PR
- [ ] Merge policy runs
- [ ] Work State comment posts as @hyperbolic-core-dev
- [ ] Evidence Index comment posts as @hyperbolic-core-dev
- [ ] Updates to same comment work (upsert)
- [ ] No errors in workflow logs

### Phase 2.2 (PR-Gate)
- [ ] Create test PR
- [ ] PR Gate runs
- [ ] Policy check comments post as @hyperbolic-core-dev
- [ ] Verification test comments post as @hyperbolic-core-dev
- [ ] Gate pass/fail messages post as @hyperbolic-core-dev
- [ ] No errors in workflow logs

### Phase 2.3 (Real PR)
- [ ] Stage 4 #160 or new test PR runs through full workflow
- [ ] All workflow comments come from @hyperbolic-core-dev
- [ ] All review comments come from @hyperbolic-core-reviewer
- [ ] No duplicate or orphaned comments

### Phase 3 (Automation)
- [ ] Claude Code agent invokes dev-agent correctly
- [ ] Comments post via dispatch, not direct API
- [ ] Reviewer agent integration works
- [ ] Wrapper script dispatch works via CLI

---

## Success Criteria

✅ **Phase 2 Success:**
- All PR and issue comments posted by `@hyperbolic-core-dev` or `@hyperbolic-core-reviewer`
- No personal account involvement in automated workflows
- Full audit trail visible on GitHub
- No failures in workflow runs

✅ **Phase 3 Success:**
- Claude Code agents automatically dispatch dev/reviewer agents
- Zero manual workflow triggers needed
- Seamless comment posting as part of agent work
- Complete automation of GitHub communications

---

## Decision Points

### If Phase 2.1/2.2 encounters issues:
1. Verify `post-work-state.yml` and `dev-agent-post-v2.yml` still work independently
2. Check workflow dispatch API call syntax
3. Test dispatch with `gh workflow run` directly
4. Fall back to manual dispatch if needed (still works, just not automated)

### If Phase 3 is not needed:
- Phase 2 alone provides full agent identity enforcement
- Manual `gh workflow run` is sufficient for exceptional cases
- Can be deferred indefinitely

---

## Next Steps

1. **Immediate (Today):**
   - Review Phase 2.1 implementation plan
   - Prepare test PR for Phase 2.3
   - Ready to proceed with dispatch integration

2. **Short-term (This week):**
   - Complete Phase 2 implementation and testing
   - Execute real PR test (Stage 4 #160)
   - Document any issues encountered

3. **Medium-term (Next week):**
   - Begin Phase 3 Claude Code integration
   - Create agent definitions
   - Build hook system

---

**Status:** Ready for Phase 2 implementation
**Last Updated:** 2026-09-16T15:13Z
**Maintainer:** Dev/Reviewer Agent Integration System
