# Agent Communication Setup

**Status:** ✅ OPERATIONAL

Both `hyperbolic-core-dev` and `hyperbolic-core-reviewer` GitHub App identities are now fully configured to handle all communications, comments, and PR operations. They no longer use your personal account (`kgsmith19`) for automated interactions.

## Architecture

```
Your Development Agent (e.g., Claude Code)
  ↓
Dispatch dev-agent-post.yml workflow
  ↓
GitHub Actions generates app JWT
  ↓
Fetch installation token for hyperbolic-core-dev (155589222)
  ↓
Post to GitHub API as dev-agent identity
  ↓
All comments/issues attributed to @hyperbolic-core-dev [bot]
```

## GitHub Secrets

Four secrets are configured in the repository (stored locally, synced from Infisical at dispatch time):

| Secret | Value | Purpose |
|--------|-------|---------|
| `DEV_GITHUB_APP_ID` | `4656454` | Dev agent app identity |
| `DEV_GITHUB_APP_PRIVATE_KEY` | `-----BEGIN RSA PRIVATE KEY-----...` | Dev agent authentication |
| `REVIEW_GITHUB_APP_ID` | `4656330` | Reviewer agent app identity |
| `REVIEW_GITHUB_APP_PRIVATE_KEY` | `-----BEGIN RSA PRIVATE KEY-----...` | Reviewer agent authentication |

**Note:** Secrets are stored in GitHub Secrets, not committed to the repository (per AGENTS.md security policy).

## Available Workflows

### dev-agent-post.yml

**Purpose:** Post comments, create issues, manage labels as the dev-agent app

**Trigger:** `workflow_dispatch` (manual or programmatic via API)

**Actions:**

```bash
# Create a GitHub Issue
gh workflow run dev-agent-post.yml \
  -f action=create_issue \
  -f title="Issue Title" \
  -f body="Issue description and details"

# Create a comment on an Issue/PR
gh workflow run dev-agent-post.yml \
  -f action=create_comment \
  -f issue_number=102 \
  -f body="Comment text"

# Update an existing comment
gh workflow run dev-agent-post.yml \
  -f action=update_comment \
  -f comment_id=1234567890 \
  -f body="Updated comment text"

# Add labels
gh workflow run dev-agent-post.yml \
  -f action=add_label \
  -f issue_number=102 \
  -f labels="status:active,risk:R1"

# Remove a label
gh workflow run dev-agent-post.yml \
  -f action=remove_label \
  -f issue_number=102 \
  -f labels="status:ready"
```

**Identity:** Posts as `@hyperbolic-core-dev [bot]`

**Permissions:** `issues: write`, `pull_requests: write`, `contents: write`, `metadata: read`

### reviewer-agent-post.yml

**Purpose:** Post review comments and reviews as the reviewer-agent app

**Trigger:** `workflow_dispatch`

**Actions:**

```bash
# Post a comment on a PR
gh workflow run reviewer-agent-post.yml \
  -f action=create_comment \
  -f pr_number=160 \
  -f body="Review comment text"

# Update a review comment
gh workflow run reviewer-agent-post.yml \
  -f action=update_comment \
  -f comment_id=1234567890 \
  -f body="Updated review text"

# Create a review with findings
gh workflow run reviewer-agent-post.yml \
  -f action=create_review \
  -f pr_number=160 \
  -f review_state=REQUEST_CHANGES \
  -f body="Review findings..."
```

**Identity:** Posts as `@hyperbolic-core-reviewer [bot]`

**Permissions:** `pull_requests: write`

## Usage Patterns

### Pattern 1: Workflow Calls Dev Agent

When a GitHub workflow (e.g., merge-policy, pr-gate) needs to post a status update:

```yaml
jobs:
  reconcile:
    runs-on: ubuntu-latest
    steps:
      - name: Fetch Work State
        id: state
        run: |
          # Compute work state
          body="## Work State\n- Issue: #102\n- Status: ready"
          echo "body=$body" >> $GITHUB_OUTPUT

      - name: Post via Dev Agent
        uses: actions/github-script@ed597411d8f924073f98dfc5c65a23a2325f34cd
        with:
          script: |
            await github.rest.actions.createWorkflowDispatch({
              owner: context.repo.owner,
              repo: context.repo.repo,
              workflow_id: 'dev-agent-post.yml',
              ref: 'main',
              inputs: {
                action: 'create_comment',
                issue_number: '${{ github.event.number }}',
                body: `${{ steps.state.outputs.body }}`
              }
            });
```

### Pattern 2: Local CLI Trigger

From your terminal, post a comment directly:

```bash
# Post a comment as dev-agent
gh workflow run dev-agent-post.yml \
  -f action=create_comment \
  -f issue_number=102 \
  -f body="Status update: Ready for merge"
```

### Pattern 3: Claude Code Agent

When a Claude Code agent (via subagent dispatch) needs to comment:

```python
# In your Claude Code task:
# "Post a status comment to PR #160 as the dev agent"
#
# The agent will:
# 1. Use gh CLI to trigger dev-agent-post.yml
# 2. Provide the comment body
# 3. Let GitHub Actions post it as @hyperbolic-core-dev
```

## Security Model

**Credential Flow:**

1. GitHub Secrets stored in repository settings (encrypted)
2. Workflow reads secrets at dispatch time
3. Secrets injected as environment variables
4. Workflow generates RS256-signed JWT (app ID + private key)
5. JWT exchanged for installation token (valid 60 minutes)
6. Installation token used for all GitHub API calls
7. Token is ephemeral (created at dispatch, discarded after job)

**Never committed secrets to repository** — all credentials live in GitHub Secrets and are synced from Infisical on-demand.

## Migrating Existing Comments

If you have existing comments posted by your personal account that should be re-attributed:

1. Dev agent cannot delete comments (no delete permission)
2. Delete old comments manually or leave them (they remain valid)
3. New automated comments go to dev/reviewer agents automatically
4. Mix of personal and bot comments is acceptable during transition

## Testing

### Test Dev Agent Connection

```bash
# Create a test issue via dev-agent
gh workflow run dev-agent-post.yml \
  -f action=create_issue \
  -f title="Test Issue" \
  -f body="Testing dev-agent connection"

# Verify it appears as @hyperbolic-core-dev
gh issue list --label=test
```

### Test Reviewer Agent Connection

```bash
# Create a test comment on a PR via reviewer-agent
gh workflow run reviewer-agent-post.yml \
  -f action=create_comment \
  -f pr_number=160 \
  -f body="Test comment from reviewer-agent"

# Verify the comment appears as @hyperbolic-core-reviewer
```

## Troubleshooting

### "Workflow not found"

The workflow files were just added. GitHub may take 1-2 minutes to index them:

```bash
gh workflow list | grep agent-post
```

If still missing, verify files are in `.github/workflows/`:

```bash
ls -la .github/workflows/dev-agent-post.yml
```

### "Secrets not found" in workflow

GitHub Secrets are stored separately from the repository. They're accessible only at workflow runtime:

```bash
# Verify secrets exist
gh secret list

# If missing, set them
gh secret set DEV_GITHUB_APP_ID --body "4656454"
```

### "JWT generation failed"

The private key must be valid RSA format. Verify it starts with `-----BEGIN RSA PRIVATE KEY-----` and ends with `-----END RSA PRIVATE KEY-----`.

If the key has been corrupted, retrieve it from Infisical:

```bash
. ~/.config/kilo/tools/Get-InfisicalSecret.ps1 -Name DEV_GITHUB_APP_PRIVATE_KEY -Path /dev/ | \
  gh secret set DEV_GITHUB_APP_PRIVATE_KEY
```

## Integration Checklist

- ✅ Secrets configured in GitHub (`gh secret list`)
- ✅ dev-agent-post.yml committed and pushed
- ✅ reviewer-agent-post.yml committed and pushed
- ✅ Workflows visible in GitHub Actions (`gh workflow list`)
- ✅ Dev agent identity: `@hyperbolic-core-dev [bot]`
- ✅ Reviewer agent identity: `@hyperbolic-core-reviewer [bot]`
- ✅ No personal account used for automated comments
- ✅ Ready for merge-policy and pr-gate integration

## Next Steps

1. **Test workflows locally:** Run `gh workflow run dev-agent-post.yml -f action=create_issue ...`
2. **Integrate with merge-policy:** Update merge-policy.yml to call dev-agent-post for Work State comments
3. **Integrate with pr-gate:** Have pr-gate call dev-agent-post for Evidence Index updates
4. **Monitor first PR:** Watch a real PR to confirm comments appear as @hyperbolic-core-dev
5. **Document usage:** Add dev-agent communication examples to your team docs

## References

- **AGENTS.md:** Agent identities, credentials, provider separation
- **dev-agent-post.yml:** Workflow implementation and action definitions
- **reviewer-agent-post.yml:** Reviewer workflow implementation
- **GitHub App Setup:** https://docs.github.com/en/apps/using-github-apps/creating-a-github-app

---

**Configured:** 2026-09-16 15:00Z
**Provider Separation:** Dev Agent (anthropic) ↔ Reviewer Agent (openai)
**Status:** Ready for production use
