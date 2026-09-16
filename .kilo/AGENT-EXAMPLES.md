# Agent Communication Examples

Real-world examples of using dev-agent and reviewer-agent for GitHub communications.

## Quick Start

### Post a Comment via Dev Agent

**Scenario:** You've just pushed a fix and want to post a status update to the PR.

```bash
gh workflow run dev-agent-post.yml \
  -f action=create_comment \
  -f issue_number=160 \
  -f body="✅ Policy check fix deployed. Pushing new commits to trigger gate re-run."
```

**Result:** Comment appears on PR #160 as `@hyperbolic-core-dev [bot]`

### Create an Issue via Dev Agent

**Scenario:** You discovered a bug during implementation and need to open an Issue.

```bash
gh workflow run dev-agent-post.yml \
  -f action=create_issue \
  -f title="Bug: Policy check doesn't recognize routed modules" \
  -f body="The policy verification in standardctl.py doesn't recognize the routed-modules architecture. Need to extend check_agents_authority() to validate AGENTS/*.md files."
```

**Result:** New Issue created, attributed to @hyperbolic-core-dev

### Post a Review Comment via Reviewer Agent

**Scenario:** The LLM review found findings and you want to post them as the reviewer.

```bash
gh workflow run reviewer-agent-post.yml \
  -f action=create_comment \
  -f pr_number=160 \
  -f body="**Finding:** Missing documentation for the routed-modules architecture.

**Citation:** AGENTS.md > Documentation and handoff

**Severity:** Advisory

**Recommendation:** Add a brief explanation in AGENTS.md root about module routing."
```

**Result:** Comment posted on PR #160 as `@hyperbolic-core-reviewer [bot]`

---

## Integration with Workflows

### Merge Policy Updates Work State

**File:** `.github/workflows/merge-policy.yml`

**Current (uses repo token):**
```javascript
await github.rest.issues.createComment({
  owner, repo,
  issue_number: pr.number,
  body: workStateBody
});
```

**Future (calls dev-agent-post):**
```javascript
// Trigger dev-agent-post workflow to post comment
await github.rest.actions.createWorkflowDispatch({
  owner: context.repo.owner,
  repo: context.repo.repo,
  workflow_id: 'dev-agent-post.yml',
  ref: 'main',
  inputs: {
    action: 'create_comment',
    issue_number: String(pr.number),
    body: workStateBody
  }
});
```

**Benefit:** All Work State comments come from @hyperbolic-core-dev, not your personal account

---

## Claude Code Integration

### Pattern 1: Dev Agent Posts After Implementation

**Scenario:** A Claude Code agent finishes implementing a fix and wants to post a status comment.

**In the agent's system prompt:**

```
When you complete implementation:
1. Commit your changes with a clear message
2. Push to the branch
3. If a PR already exists, post a status update using the dev-agent:
   gh workflow run dev-agent-post.yml -f action=create_comment \
     -f issue_number=<PR_NUMBER> \
     -f body="✅ Implementation complete. Pushed <COMMIT_SHA>. Ready for review."
4. Report completion to the controller
```

### Pattern 2: Reviewer Agent Posts Findings

**Scenario:** A separate reviewer Claude Code agent runs the LLM Review and wants to post findings.

**In the reviewer's system prompt:**

```
When you complete your review:
1. Compile all findings and recommendations
2. Format them with citation, severity, and recommendation
3. Post via the reviewer-agent:
   gh workflow run reviewer-agent-post.yml -f action=create_comment \
     -f pr_number=<PR_NUMBER> \
     -f body="<FORMATTED_FINDINGS>"
4. Upload evidence artifacts (screenshots, reports)
5. Report review complete
```

### Pattern 3: Workflow State Transitions

**Scenario:** When an Issue transitions from `status:ready` to `status:active`, update the labels.

**In any workflow:**

```bash
# Remove ready label
gh workflow run dev-agent-post.yml \
  -f action=remove_label \
  -f issue_number=102 \
  -f labels=status:ready

# Add active label
gh workflow run dev-agent-post.yml \
  -f action=add_label \
  -f issue_number=102 \
  -f labels=status:active
```

**Result:** Labels updated, no personal account involvement

---

## Real Workflow: PR Gate Failure to Fix

**Scenario:** PR #160 gate check fails, dev-agent needs to post failure details and trigger re-run.

### Step 1: Detect Failure (pr-gate.yml job output)

```bash
# pr-gate.yml detects the policy check failed
export CHECK_FAILURE="Agent Engineering Standard · Policy & Structure"
export ERROR_MSG="required sections missing or out of order: Objective, Owner authority"
```

### Step 2: Dev Agent Posts Failure Comment

```bash
# Trigger dev-agent-post from pr-gate
gh workflow run dev-agent-post.yml \
  -f action=create_comment \
  -f issue_number=160 \
  -f body="❌ **Gate Check Failed**

Check: \`$CHECK_FAILURE\`
Error: \`$ERROR_MSG\`

**Action:** Pushing fix to policy validator..."
```

### Step 3: Dev Agent Posts Fix Confirmation

```bash
# After fix is pushed
gh workflow run dev-agent-post.yml \
  -f action=create_comment \
  -f issue_number=160 \
  -f body="✅ **Policy Check Fix Deployed**

Commit: ba6e1c1
File: tools/standardctl.py

**Change:** Extended check_agents_authority() to validate routed-modules architecture

Gate should now pass. Waiting for re-run..."
```

**Result:** Full audit trail visible on PR, all attributed to @hyperbolic-core-dev

---

## Real Workflow: Evidence Indexing

**Scenario:** PR Gate produces evidence artifacts, dev-agent needs to post Evidence Index.

### Step 1: Gate Job Generates Evidence

```bash
# pr-gate completes and uploads .evidence/manifest.json artifact
export ARTIFACT_ID="12345678"
export EVIDENCE_URL="https://github.com/.../artifacts/12345678"
```

### Step 2: Dev Agent Posts Evidence Index

```bash
gh workflow run dev-agent-post.yml \
  -f action=create_comment \
  -f issue_number=160 \
  -f marker="<!-- agent-engineering-standard:evidence-index:v1 -->" \
  -f body="## Evidence Index

- **Workflow:** Agent Engineering Standard PR Gate
- **Artifact:** evidence-pr-160-ba6e1c1 (ID $ARTIFACT_ID)
- **Head:** ba6e1c1
- **Status:** [Available](${EVIDENCE_URL}) (expires in 90 days)

Contents: verification logs, coverage reports, security scan"
```

**Result:** Evidence Index comment posted by @hyperbolic-core-dev with permanent archive link

---

## Monitoring & Debugging

### Verify Dev Agent Identity

After posting a comment, verify it shows as `@hyperbolic-core-dev [bot]`:

```bash
# List recent comments on PR #160
gh pr view 160 --json comments \
  --jq '.comments[] | select(.author.login=="hyperbolic-core-dev") | {id: .databaseId, body: .body}'
```

### Check Workflow Execution

```bash
# View dev-agent-post workflow runs
gh run list --workflow=dev-agent-post.yml --limit=10

# View details of a specific run
gh run view <RUN_ID> --log
```

### Troubleshoot Failed Dispatch

```bash
# If a dispatch fails, check the job logs
gh run view <RUN_ID> --log-failed

# Common issues:
# - Secrets not found: gh secret list
# - Invalid app ID: verify DEV_GITHUB_APP_ID matches 4656454
# - JWT generation: check PRIVATE_KEY format (RSA, not PEM)
# - Token exchange: verify installation ID is 155589222
```

---

## Best Practices

✅ **DO:**
- Use dev-agent for status updates and workflow state
- Use reviewer-agent for code review and quality findings
- Include clear citations to AGENTS.md when posting policy findings
- Add markers to managed comments (e.g., `<!-- agent-engineering-standard:work-state:v1 -->`)
- Keep comments factual and actionable

❌ **DON'T:**
- Post comments as your personal account when agent identity is available
- Store secrets in workflows or commit logs
- Bypass dev-agent for UI/status updates
- Mix personal and bot identities for the same type of comment
- Delete dev-agent comments without reason

---

## API Reference

### dev-agent-post.yml Inputs

| Input | Type | Required | Example | Notes |
|-------|------|----------|---------|-------|
| `action` | choice | yes | `create_comment` | Must be one of: create_issue, create_comment, update_comment, add_label, remove_label |
| `issue_number` | string | depends | `160` | Required for all actions except create_issue |
| `comment_id` | string | for update | `1234567` | Comment database ID (not GitHub ID) |
| `title` | string | for create_issue | `Policy Check Fix` | Issue title |
| `body` | string | yes | `Status update...` | Comment or issue body |
| `marker` | string | optional | `<!-- marker -->` | Comment marker for finding existing comments |
| `labels` | string | for labels | `status:active,risk:R1` | Comma-separated list |

### reviewer-agent-post.yml Inputs

| Input | Type | Required | Example | Notes |
|-------|------|----------|---------|-------|
| `action` | choice | yes | `create_comment` | Must be one of: create_comment, update_comment, create_review |
| `pr_number` | string | yes | `160` | Pull request number |
| `comment_id` | string | for update | `1234567` | Comment database ID |
| `body` | string | yes | `Review findings...` | Comment or review body |
| `review_state` | choice | for review | `REQUEST_CHANGES` | One of: COMMENT, APPROVE, REQUEST_CHANGES |

---

## Questions?

Refer to:
- `.kilo/AGENT-COMMUNICATION.md` — Full setup and architecture guide
- `AGENTS.md` — Policy, credentials, provider separation
- `.github/workflows/dev-agent-post.yml` — Implementation details
