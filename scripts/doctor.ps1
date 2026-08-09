param(
  [switch]$Remote,
  [string]$ConfigPath = (Join-Path $PSScriptRoot '..\policy\github-defaults.json')
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $PSScriptRoot 'lib/review-policy.ps1')
. (Join-Path $PSScriptRoot 'lib/standard-lock.ps1')

function Get-Paged {
  param([string]$Endpoint)
  $raw = & gh api --paginate --slurp $Endpoint 2>&1
  if ($LASTEXITCODE -ne 0) { throw ($raw -join "`n") }
  $pages = ($raw -join "`n") | ConvertFrom-Json
  foreach ($page in @($pages)) { foreach ($item in @($page)) { $item } }
}

function Add-Problem {
  param($List,[string]$Text)
  $List.Add($Text)
}

$required = @(
  'README.md','LIFECYCLE.md','AGENT_RULES.md','QUALITY_RULES.md','SECURITY_RISK_AUTONOMY.md','DELIVERY_GITHUB.md','EVIDENCE_LEARNING.md','AGENTS.md','docs/AUTONOMOUS-PR-STATE-MACHINE.md',
  '.github/workflows/ci.yml','.github/workflows/ai-review.yml','.github/workflows/ai-review-reusable.yml','.github/workflows/pr-automation.yml','.github/workflows/pr-automation-gate-result.yml','.github/workflows/pr-automation-review-event.yml','.github/workflows/pr-automation-comment-event.yml','.github/workflows/pr-automation-watchdog.yml','.github/workflows/pr-automation-reusable.yml','.github/workflows/ops-portfolio-bootstrap.yml','policy/github-defaults.json',
  'scripts/setup-portfolio.ps1','scripts/apply-github-standard.ps1','scripts/codex-review.ps1','scripts/request-independent-review.ps1','scripts/request-machine-review.ps1','scripts/evaluate-ai-review.ps1','scripts/reconcile-machine-review-threads.ps1','scripts/auto-merge.ps1','scripts/pr-orchestrator.ps1','scripts/gate-result-router.ps1','scripts/promote-external-draft.ps1','scripts/review-metrics.ps1','scripts/lint-pr-creation.ps1','scripts/bootstrap-repo.ps1','scripts/upgrade-repos.ps1','scripts/prune-portfolio.ps1',
  'scripts/lib/standard-lock.ps1','scripts/lib/review-policy.ps1','tests/legacy-protection.tests.ps1','tests/standard-lock.tests.ps1','tests/review-policy.tests.ps1','tests/draft-prevention.tests.ps1','tests/unconditional-evaluation.tests.ps1','tests/script-smoke.tests.ps1','tests/gate-result-arming.tests.ps1','tests/standard-hygiene.tests.ps1',
  'templates/.gitignore','templates/AGENTS.md','templates/PR_GATE.yml','templates/AI_REVIEW.yml','templates/PR_AUTOMATION.yml','templates/PR_AUTOMATION_GATE_RESULT.yml','templates/PR_AUTOMATION_REVIEW_EVENT.yml','templates/PR_AUTOMATION_COMMENT_EVENT.yml','templates/PR_AUTOMATION_WATCHDOG.yml','templates/dependabot.yml','templates/PRD.md','templates/SPEC.md','templates/ADR.md','templates/ISSUE.md','templates/PULL_REQUEST.md'
)
foreach ($relative in $required) {
  if (-not (Test-Path (Join-Path $root $relative))) { throw "Missing required file: $relative" }
}
if (Test-Path (Join-Path $root '.github/CODEOWNERS')) { throw 'Native CODEOWNERS must remain absent.' }
if (Test-Path (Join-Path $root 'templates/CODEOWNERS')) { throw 'Native CODEOWNERS bootstrap template must remain absent.' }

$config = Get-Content $ConfigPath -Raw | ConvertFrom-Json
# Context-rename transition: the ruleset-required context may be the legacy
# name or the new one; while it is still the legacy name, the gate workflow
# must carry the fail-closed 'PR Gate' bridge job so no PR becomes unmergeable.
if ([string]$config.required_status_context -notin @('PR Gate','Gate: Deterministic CI')) { throw 'Required deterministic context drifted.' }
if ([string]$config.required_status_context_next -ne 'Gate: Deterministic CI') { throw 'Transition target context (required_status_context_next) missing or drifted.' }
if ($config.required_ai_review_context -ne 'Advisory: AI Review') { throw 'Advisory check context drifted.' }
$gateWorkflow = Get-Content (Join-Path $root '.github/workflows/ci.yml') -Raw
if ($gateWorkflow -notmatch '(?m)^name:\s*"Gate: Deterministic CI"\s*$') { throw 'Gate workflow must carry the new taxonomy name.' }
if ([string]$config.required_status_context -eq 'PR Gate' -and ($gateWorkflow -notmatch 'pr-gate-bridge:' -or $gateWorkflow -notmatch '(?m)^\s+name:\s*PR Gate\s*$')) { throw 'PR Gate bridge job is required while the legacy context is still ruleset-required.' }
if ([int]$config.required_approving_review_count -ne 0) { throw 'Human approval count must remain zero.' }
if ([bool]$config.require_code_owner_review -or [bool]$config.native_codeowners -or [bool]$config.org_hardening.require_code_owner_review) { throw 'Native/required Code Owner review must remain disabled.' }
if (@($config.forbidden_requested_reviewers) -notcontains [string]$config.owner) { throw 'Repository owner must be forbidden from requested-reviewer state.' }
if (-not [bool]$config.allow_auto_merge -or -not [bool]$config.allow_update_branch) { throw 'Auto-merge and update-branch must remain enabled.' }
if ([bool]$config.allow_merge_commit -or [bool]$config.allow_rebase_merge -or -not [bool]$config.allow_squash_merge -or $config.merge_method -ne 'squash') { throw 'Merge policy must remain squash-only.' }
if ($config.auto_merge_max_risk -ne 'R2') { throw 'Unreviewed canary auto-merge must stop at R2; R3+ waits for the review lane or a human.' }
if ([bool]$config.merge_queue.desired) { throw 'Merge queue must remain deferred until organization ownership and merge_group AI Review are proven.' }

$review = $config.independent_review
if ([bool]$review.required_for_auto_merge) { throw 'Machine review must remain advisory: the deterministic PR Gate is the sole required merge authority.' }
if ([string]$review.dispatch_mode -notin @('disabled_pending_e2e','enabled')) { throw "Unknown review dispatch_mode '$($review.dispatch_mode)'." }
if ([string]$review.dispatch_policy_version -notmatch '^[1-9][0-9]*$') { throw 'dispatch_policy_version must be a positive integer.' }
# RC-J: Copilot's repository access is revoked; codex is the sole connected
# reviewer. The fallback lane stays in code but doctor tolerates blanking it.
if ($review.preferred_provider -ne 'codex') { throw 'Machine-review routing drifted: codex must remain primary.' }
if ([string]$review.fallback_provider -notin @('copilot','')) { throw "Unknown fallback provider '$($review.fallback_provider)'." }
if ([int]$review.max_review_heads_per_pr -ne 2 -or [int]$review.primary_wait_minutes -le 0 -or [int]$review.fallback_wait_minutes -le 0 -or [int]$review.poll_seconds -le 0) { throw 'Machine-review budgets drifted.' }
if ([int]$review.review_stall_minutes -ne 2) { throw 'Review stall window drifted from the approved 2 minutes.' }
if ([int]$review.absolute_timeout_minutes -le ([int]$review.primary_wait_minutes + [int]$review.fallback_wait_minutes)) { throw 'Absolute review timeout must exceed fast polling windows.' }
if ([bool]$review.review_drafts -or [bool]$review.review_on_every_push) { throw 'Draft/every-push AI review spend must remain off.' }

$automation = $config.pr_automation
if ($automation.PSObject.Properties.Name -contains 'draft_ready_label') { throw 'Draft promotion must not exist in strict ready-at-creation policy.' }
$externalPromotion = $automation.PSObject.Properties['external_draft_promotion']
if (-not $externalPromotion -or $externalPromotion.Value -isnot [bool]) { throw 'external_draft_promotion must be a boolean.' }
if ($automation.blocked_label -ne 'status:blocked') { throw 'PR blocked-state label drifted.' }
foreach ($pair in @(@('max_ci_fix_attempts',3),@('max_review_fix_attempts',1),@('max_conflict_fix_attempts',2))) {
  if ([int]$automation.PSObject.Properties[$pair[0]].Value -ne [int]$pair[1]) { throw "Repair budget drifted: $($pair[0])." }
}
if ([int]$automation.watchdog_interval_minutes -ne 360) { throw 'Watchdog cadence drifted from the approved six-hourly (360-minute) reconciliation.' }
if ([int]$automation.watchdog_interval_minutes -ge [int]$review.absolute_timeout_minutes) { throw 'Watchdog cadence must be shorter than the configured absolute timeout.' }

foreach ($gateName in @('control_plane','R4')) {
  $gate = $config.manual_gates.PSObject.Properties[$gateName].Value
  if (-not $gate -or -not [bool]$gate.required) { throw "Manual authority gate '$gateName' is not configured." }
  Assert-ManualGateJustification $gate | Out-Null
}

# The approved all-13 design note is the source of truth for the managed set;
# policy must list exactly those repositories, in the note's order.
$designNotePath = Join-Path $root 'docs/superpowers/specs/2026-08-09-all-13-github-automation-design.md'
if (-not (Test-Path $designNotePath)) { throw 'Approved all-13 design note is missing.' }
$notedRepos = @([regex]::Matches((Get-Content $designNotePath -Raw),'(?m)^\d+\.\s+`([^`]+)`\s*$') | ForEach-Object { [string]$_.Groups[1].Value })
if ($notedRepos.Count -ne 13) { throw "Design note must name exactly 13 repositories; found $($notedRepos.Count)." }
if ((@($config.repositories) -join ',') -ne ($notedRepos -join ',')) { throw 'Policy repositories drifted from the approved all-13 design note.' }

$parseFailures = New-Object System.Collections.Generic.List[string]
foreach ($file in @(Get-ChildItem (Join-Path $root 'scripts') -Recurse -Filter '*.ps1') + @(Get-ChildItem (Join-Path $root 'tests') -Recurse -Filter '*.ps1')) {
  $tokens = $null; $errors = $null
  [System.Management.Automation.Language.Parser]::ParseFile($file.FullName,[ref]$tokens,[ref]$errors) | Out-Null
  foreach ($error in @($errors)) { $parseFailures.Add("$($file.FullName): $($error.Message)") }
}
if ($parseFailures.Count -gt 0) { throw "PowerShell parse failures:`n$($parseFailures -join "`n")" }

Write-Host 'LOCAL: READY' -ForegroundColor Green
if (-not $Remote) { exit 0 }
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw 'gh is required for -Remote.' }

$actionsAppRaw = & gh api /apps/github-actions 2>&1
if ($LASTEXITCODE -ne 0) { throw 'Could not resolve GitHub Actions App identity.' }
$actionsAppId = [int]((($actionsAppRaw -join "`n") | ConvertFrom-Json).id)
$remoteFailures = New-Object System.Collections.Generic.List[string]

foreach ($name in $config.repositories) {
  $repo = "$($config.owner)/$name"
  $problems = New-Object System.Collections.Generic.List[string]

  $metaRaw = & gh api "repos/$repo" 2>&1
  if ($LASTEXITCODE -ne 0) { $remoteFailures.Add("${repo}: cannot read repository"); continue }
  $meta = ($metaRaw -join "`n") | ConvertFrom-Json

  if (-not $meta.has_issues) { Add-Problem $problems 'Issues disabled' }
  if (-not $meta.allow_auto_merge) { Add-Problem $problems 'auto-merge off' }
  if (-not $meta.allow_update_branch) { Add-Problem $problems 'update-branch off' }
  if (-not $meta.delete_branch_on_merge) { Add-Problem $problems 'delete-branch off' }
  if (-not $meta.allow_squash_merge) { Add-Problem $problems 'squash off' }
  if ($meta.allow_merge_commit) { Add-Problem $problems 'merge commits enabled' }
  if ($meta.allow_rebase_merge) { Add-Problem $problems 'rebase enabled' }

  $actionsRaw = & gh api "repos/$repo/actions/permissions" 2>&1
  if ($LASTEXITCODE -ne 0) { Add-Problem $problems 'cannot read Actions permissions' }
  elseif (-not [bool](($actionsRaw -join "`n") | ConvertFrom-Json).enabled) { Add-Problem $problems 'Actions disabled' }

  $workflowPermissionsRaw = & gh api "repos/$repo/actions/permissions/workflow" 2>&1
  if ($LASTEXITCODE -ne 0) { Add-Problem $problems 'cannot read workflow-token defaults' }
  else {
    $workflowPermissions = ($workflowPermissionsRaw -join "`n") | ConvertFrom-Json
    if ($workflowPermissions.default_workflow_permissions -ne 'read') { Add-Problem $problems 'workflow token default is not read-only' }
    if ([bool]$workflowPermissions.can_approve_pull_request_reviews) { Add-Problem $problems 'workflow token can approve PR reviews' }
  }

  $copilotRaw = & gh api -H 'X-GitHub-Api-Version: 2026-03-10' "repos/$repo/copilot/cloud-agent/configuration" 2>&1
  if ($LASTEXITCODE -ne 0) { Add-Problem $problems 'cannot read Copilot cloud-agent settings' }
  elseif ([bool](($copilotRaw -join "`n") | ConvertFrom-Json).require_actions_workflow_approval) { Add-Problem $problems 'Copilot Actions still require maintainer approval' }

  $codeownersRaw = & gh api "repos/$repo/contents/.github/CODEOWNERS?ref=$($meta.default_branch)" 2>&1
  if ($LASTEXITCODE -eq 0) { Add-Problem $problems 'native CODEOWNERS present' }
  elseif (-not (($codeownersRaw -join "`n") -match '(?i)404|not found')) { Add-Problem $problems 'cannot determine CODEOWNERS absence' }

  $workflowsRaw = & gh api "repos/$repo/actions/workflows?per_page=100" 2>&1
  if ($LASTEXITCODE -ne 0) { Add-Problem $problems 'cannot list workflows' }
  else {
    $workflows = @(($workflowsRaw -join "`n") | ConvertFrom-Json | Select-Object -ExpandProperty workflows)
    $requiredWorkflows = @('Gate: Deterministic CI','Orchestrator: PR Lifecycle','Orchestrator: Gate Result','Orchestrator: Review Event','Orchestrator: Comment Event','Orchestrator: Watchdog')
    if ([bool]$review.required_for_auto_merge -or [bool]$review.solicit_reviews) { $requiredWorkflows += 'Advisory: AI Review' }
    foreach ($workflowName in $requiredWorkflows) {
      $matches = @($workflows | Where-Object { $_.name -eq $workflowName -and $_.state -eq 'active' })
      if ($matches.Count -eq 0) { Add-Problem $problems "active workflow missing: $workflowName" }
      elseif ($matches.Count -gt 1) { Add-Problem $problems "duplicate active workflow: $workflowName" }
    }
  }

  if ($name -ne 'agent-engineering-standard') {
    $lockRaw = & gh api -H 'Accept: application/vnd.github.raw+json' "repos/$repo/contents/.agent/standard.lock?ref=$($meta.default_branch)" 2>&1
    if ($LASTEXITCODE -ne 0) { Add-Problem $problems 'standard.lock missing' }
    else {
      try { $pinnedSha = Get-StandardLockRevision ($lockRaw -join "`n") }
      catch { $pinnedSha = $null; Add-Problem $problems 'standard.lock revision unreadable' }
      foreach ($caller in @('ai-review.yml','pr-automation.yml','pr-automation-gate-result.yml','pr-automation-review-event.yml','pr-automation-comment-event.yml','pr-automation-watchdog.yml')) {
        $callerRaw = & gh api -H 'Accept: application/vnd.github.raw+json' "repos/$repo/contents/.github/workflows/$caller?ref=$($meta.default_branch)" 2>&1
        if ($LASTEXITCODE -ne 0) { Add-Problem $problems "$caller missing"; continue }
        $callerText = $callerRaw -join "`n"
        if ($callerText -match '@main\b|__STANDARD_SHA__') { Add-Problem $problems "$caller follows moving or unresolved standard ref" }
        if ($pinnedSha) {
          $standardRepo = [regex]::Escape("$($config.owner)/agent-engineering-standard")
          $usesRefs = @([regex]::Matches($callerText,"(?m)^\s*uses:\s*$standardRepo/[^@\s]+@(.*?)\s*$") | ForEach-Object { [string]$_.Groups[1].Value })
          if ($usesRefs.Count -eq 0 -or @($usesRefs | Where-Object {
            $_ -notmatch '^[0-9a-fA-F]{40}$' -or $_.ToLowerInvariant() -ne $pinnedSha.ToLowerInvariant()
          }).Count -gt 0) {
            Add-Problem $problems "$caller reusable-workflow ref not pinned to standard.lock"
          }
          $standardShaInputs = @([regex]::Matches($callerText,'(?m)^\s*standard_sha:\s*(.*?)\s*$'))
          if ($standardShaInputs.Count -eq 0 -or @($standardShaInputs | Where-Object {
            $value = [string]$_.Groups[1].Value
            $value -notmatch '^[0-9a-fA-F]{40}$' -or $value.ToLowerInvariant() -ne $pinnedSha.ToLowerInvariant()
          }).Count -gt 0) {
            Add-Problem $problems "$caller standard_sha input not pinned to standard.lock"
          }
        }
      }
    }
  }

  $rulesetSummaries = $null
  try { $rulesetSummaries = @(Get-Paged "repos/$repo/rulesets?per_page=100") }
  catch { Add-Problem $problems 'cannot read rulesets' }
  if ($null -ne $rulesetSummaries) {
    $summary = ($rulesetSummaries | Where-Object { $_.name -eq $config.ruleset_name } | Select-Object -First 1)

    $defaultBranchEncoded = [uri]::EscapeDataString([string]$meta.default_branch)
    try { $effectiveRules = @(Get-Paged "repos/$repo/rules/branches/${defaultBranchEncoded}?per_page=100") }
    catch { $effectiveRules = $null; Add-Problem $problems 'cannot verify effective default-branch rulesets' }
    if ($null -ne $effectiveRules) {
      $canonicalId = if ($summary) { [long]$summary.id } else { [long]-1 }
      $conflictingIds = @($effectiveRules |
        ForEach-Object { [long]$_.ruleset_id } |
        Where-Object { $_ -gt 0 -and $_ -ne $canonicalId } |
        Select-Object -Unique)
      foreach ($id in $conflictingIds) {
        $match = $rulesetSummaries | Where-Object { [long]$_.id -eq $id } | Select-Object -First 1
        $description = if ($match) { "$($match.name) (#$id)" } else { "ruleset #$id" }
        Add-Problem $problems "conflicting active default-branch ruleset: $description"
      }
    }

    if (-not $summary) { Add-Problem $problems 'canonical ruleset missing' }
    else {
      $detailRaw = & gh api "repos/$repo/rulesets/$($summary.id)" 2>&1
      if ($LASTEXITCODE -ne 0) { Add-Problem $problems 'cannot read canonical ruleset' }
      else {
        $detail = ($detailRaw -join "`n") | ConvertFrom-Json
        if ($detail.enforcement -ne 'active') { Add-Problem $problems 'ruleset not active' }
        if ($detail.bypass_actors -and @($detail.bypass_actors).Count -gt 0) { Add-Problem $problems 'ruleset has bypass actors' }
        if (-not (@($detail.conditions.ref_name.include) -contains '~DEFAULT_BRANCH')) { Add-Problem $problems 'ruleset misses default branch' }
        $types = @($detail.rules | ForEach-Object { $_.type })
        foreach ($requiredType in @('deletion','non_fast_forward','pull_request','required_status_checks')) {
          if ($types -notcontains $requiredType) { Add-Problem $problems "missing rule: $requiredType" }
        }

        $prRule = $detail.rules | Where-Object { $_.type -eq 'pull_request' } | Select-Object -First 1
        if (-not $prRule) { Add-Problem $problems 'pull-request rule missing' }
        else {
          if ([int]$prRule.parameters.required_approving_review_count -ne 0) { Add-Problem $problems 'human approvals not zero' }
          if ([bool]$prRule.parameters.require_code_owner_review) { Add-Problem $problems 'Code Owner review required' }
          if ([bool]$prRule.parameters.require_last_push_approval) { Add-Problem $problems 'last-push approval required' }
          if (-not [bool]$prRule.parameters.dismiss_stale_reviews_on_push) { Add-Problem $problems 'stale reviews not dismissed' }
          if ([bool]$prRule.parameters.required_review_thread_resolution -ne [bool]$config.required_review_thread_resolution) { Add-Problem $problems 'thread-resolution requirement drifted from policy' }
          $methods = @($prRule.parameters.allowed_merge_methods)
          if ($methods.Count -ne 1 -or $methods[0] -ne 'squash') { Add-Problem $problems 'ruleset not squash-only' }
        }

        $statusRule = $detail.rules | Where-Object { $_.type -eq 'required_status_checks' } | Select-Object -First 1
        if (-not $statusRule) { Add-Problem $problems 'required-status rule missing' }
        else {
          $checks = @($statusRule.parameters.required_status_checks)
          $expected = @($config.required_status_context)
          if ([bool]$config.independent_review.required_for_auto_merge) { $expected += $config.required_ai_review_context }
          if ($checks.Count -ne $expected.Count) { Add-Problem $problems 'extra or missing required status checks' }
          foreach ($context in $expected) {
            $check = @($checks | Where-Object { $_.context -eq $context } | Select-Object -First 1)
            if ($check.Count -eq 0) { Add-Problem $problems "required context missing: $context" }
            elseif ([int]$check[0].integration_id -ne $actionsAppId) { Add-Problem $problems "$context not bound to GitHub Actions" }
          }
        }
      }
    }
  }

  $legacyRaw = & gh api "repos/$repo/branches/$($meta.default_branch)/protection" 2>&1
  if ($LASTEXITCODE -eq 0) { Add-Problem $problems 'legacy branch protection still present' }
  elseif (-not (($legacyRaw -join "`n") -match '(?i)branch not protected|\b404\b|not found')) { Add-Problem $problems 'cannot verify legacy protection absence' }

  try { $openPrs = @(Get-Paged "repos/$repo/pulls?state=open&per_page=100") }
  catch { $openPrs = @(); Add-Problem $problems 'cannot inspect open PR blockers' }
  foreach ($openPr in $openPrs) {
    $forbidden = @($openPr.requested_reviewers | ForEach-Object { [string]$_.login } | Where-Object { @($config.forbidden_requested_reviewers) -contains $_ })
    if ($forbidden.Count -gt 0) { Add-Problem $problems "PR #$($openPr.number) requests forbidden reviewer: $($forbidden -join ', ')" }
    if ([string]$openPr.user.login -eq 'Copilot' -or [string]$openPr.head.ref -like 'copilot/*') { Add-Problem $problems "PR #$($openPr.number) is Copilot-owned and cannot be unattended" }
  }

  if ($problems.Count -eq 0) { Write-Host "${repo} : READY" -ForegroundColor Green }
  else {
    Write-Host "${repo} : $($problems -join ', ')" -ForegroundColor Yellow
    foreach ($problem in $problems) { $remoteFailures.Add("${repo}: $problem") }
  }
}

if ($remoteFailures.Count -gt 0) { throw "REMOTE: DRIFT DETECTED`n$($remoteFailures -join "`n")" }
Write-Host 'REMOTE: READY' -ForegroundColor Green
