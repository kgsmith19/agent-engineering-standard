param(
  [switch]$Remote,
  [string]$ConfigPath = (Join-Path $PSScriptRoot "..\policy\github-defaults.json")
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $PSScriptRoot 'lib/legacy-protection.ps1')
. (Join-Path $PSScriptRoot 'lib/review-policy.ps1')

function Test-CodeownersTail {
  param([Parameter(Mandatory)][string]$Content,[Parameter(Mandatory)][string[]]$ExpectedTail)
  $rules = @($Content -split "`r?`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ -and -not $_.StartsWith('#') })
  if ($rules.Count -lt $ExpectedTail.Count) { return $false }
  $start = $rules.Count - $ExpectedTail.Count
  for ($i = 0; $i -lt $ExpectedTail.Count; $i++) { if ($rules[$start + $i] -ne $ExpectedTail[$i]) { return $false } }
  return $true
}

$required = @(
  'README.md','LIFECYCLE.md','AGENT_RULES.md','QUALITY_RULES.md','SECURITY_RISK_AUTONOMY.md','DELIVERY_GITHUB.md','EVIDENCE_LEARNING.md','AGENTS.md',
  '.github/CODEOWNERS','.github/workflows/ci.yml','.github/workflows/ai-review.yml','.github/workflows/ai-review-reusable.yml','policy/github-defaults.json',
  'scripts/setup-portfolio.ps1','scripts/apply-github-standard.ps1','scripts/sync-agentic-project.ps1','scripts/codex-review.ps1','scripts/request-independent-review.ps1','scripts/auto-merge.ps1','scripts/bootstrap-repo.ps1','scripts/upgrade-repos.ps1',
  'scripts/lib/legacy-protection.ps1','scripts/lib/standard-lock.ps1','scripts/lib/review-policy.ps1',
  'tests/legacy-protection.tests.ps1','tests/standard-lock.tests.ps1','tests/review-policy.tests.ps1',
  'templates/AGENTS.md','templates/CODEOWNERS','templates/PR_GATE.yml','templates/AI_REVIEW.yml','templates/PRD.md','templates/SPEC.md','templates/ADR.md','templates/ISSUE.md','templates/PULL_REQUEST.md'
)
foreach ($relative in $required) { if (-not (Test-Path (Join-Path $root $relative))) { throw "Missing required file: $relative" } }

$config = Get-Content (Join-Path $root 'policy/github-defaults.json') -Raw | ConvertFrom-Json
if ($config.required_status_context -ne 'PR Gate') { throw "required_status_context must be 'PR Gate'" }
if ($config.required_ai_review_context -ne 'AI Review') { throw "required_ai_review_context must be 'AI Review'" }
if ($config.required_approving_review_count -ne 0) { throw 'Default human approval count must remain 0.' }
if ($config.require_code_owner_review) { throw 'Personal-account default must not require Code Owner approval.' }
if (-not [bool]$config.org_hardening.require_code_owner_review) { throw 'Organization hardening must retain Code Owner review.' }
if (-not [bool]$config.allow_auto_merge -or -not [bool]$config.allow_update_branch) { throw 'Safe automated lane requires auto-merge + update-branch enabled.' }
if ([bool]$config.allow_merge_commit -or [bool]$config.allow_rebase_merge -or -not [bool]$config.allow_squash_merge -or $config.merge_method -ne 'squash') { throw 'Repository merge policy must remain squash-only.' }
if ($config.auto_merge_max_risk -ne 'R3') { throw 'auto_merge_max_risk must remain R3; R4 requires explicit authority.' }

$review = $config.independent_review
if (-not [bool]$review.required_for_auto_merge) { throw 'Independent AI review must be required before auto-merge.' }
if ($review.preferred_provider -ne 'codex' -or $review.local_codex_model -ne 'gpt-5.4-mini') { throw 'Current low-cost default must remain Codex + gpt-5.4-mini unless evidence changes.' }
if ([int]$review.max_codex_reviews_per_pr -ne 2 -or [int]$review.max_copilot_reviews_per_pr -ne 1) { throw 'Review budgets drifted.' }
if ([bool]$review.copilot_review_on_push -or [bool]$review.copilot_review_drafts) { throw 'Unbounded Copilot draft/push review must remain off.' }
if ($review.copilot_effort -ne 'low' -or [bool]$review.same_provider_counts_as_independent) { throw 'Copilot/independence policy drifted.' }

foreach ($field in @('failure_class_prevented','why_automation_is_insufficient','decision_owner','gate_removal_condition')) {
  if (@($config.manual_gate_required_fields) -notcontains $field) { throw "manual_gate_required_fields missing '$field'." }
}
foreach ($gateName in @('control_plane','R4')) {
  $gate = $config.manual_gates.PSObject.Properties[$gateName].Value
  if (-not $gate -or -not [bool]$gate.required) { throw "Manual gate '$gateName' is not explicitly configured." }
  Assert-ManualGateJustification -Justification $gate | Out-Null
}

$ownerToken = "@$($config.owner)"
$appTail = @("/.github/workflows/ $ownerToken","/.github/CODEOWNERS $ownerToken","/.agent/ $ownerToken","/AGENTS.md $ownerToken")
$standardTail = @("/.github/workflows/ $ownerToken","/.github/CODEOWNERS $ownerToken","/policy/ $ownerToken","/scripts/ $ownerToken","/AGENTS.md $ownerToken","/AGENT_RULES.md $ownerToken","/QUALITY_RULES.md $ownerToken","/SECURITY_RISK_AUTONOMY.md $ownerToken","/DELIVERY_GITHUB.md $ownerToken")
if (-not (Test-CodeownersTail -Content (Get-Content (Join-Path $root '.github/CODEOWNERS') -Raw) -ExpectedTail $standardTail)) { throw 'Local CODEOWNERS drifted.' }
if (-not (Test-CodeownersTail -Content (Get-Content (Join-Path $root 'templates/CODEOWNERS') -Raw) -ExpectedTail $appTail)) { throw 'Template CODEOWNERS drifted.' }

$psScripts = @(
  'scripts/setup-portfolio.ps1','scripts/apply-github-standard.ps1','scripts/sync-agentic-project.ps1','scripts/codex-review.ps1','scripts/request-independent-review.ps1','scripts/auto-merge.ps1','scripts/bootstrap-repo.ps1','scripts/upgrade-repos.ps1','scripts/doctor.ps1',
  'scripts/lib/legacy-protection.ps1','scripts/lib/standard-lock.ps1','scripts/lib/review-policy.ps1','tests/legacy-protection.tests.ps1','tests/standard-lock.tests.ps1','tests/review-policy.tests.ps1'
)
foreach ($relative in $psScripts) {
  $tokens = $null; $errors = $null
  [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $root $relative), [ref]$tokens, [ref]$errors) | Out-Null
  if ($errors.Count -gt 0) { throw "PowerShell parse failed: $relative :: $($errors[0].Message)" }
}

Write-Host 'LOCAL: READY' -ForegroundColor Green
if (-not $Remote) { exit 0 }
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw 'gh is required for -Remote.' }

$actionsAppRaw = & gh api /apps/github-actions 2>&1
if ($LASTEXITCODE -ne 0) { throw 'Could not resolve GitHub Actions App identity.' }
$actionsAppId = [int]((($actionsAppRaw -join "`n") | ConvertFrom-Json).id)
$remoteFailures = New-Object System.Collections.Generic.List[string]

foreach ($name in $config.repositories) {
  $repo = "$($config.owner)/$name"; $problems = New-Object System.Collections.Generic.List[string]
  $metaRaw = & gh api "repos/$repo" 2>&1
  if ($LASTEXITCODE -ne 0) { $remoteFailures.Add("${repo}: cannot read repository"); continue }
  $meta = ($metaRaw -join "`n") | ConvertFrom-Json
  $isOrgOwned = $meta.owner.type -eq 'Organization'
  $expectedCodeOwnerReview = [bool]$config.require_code_owner_review
  if ($isOrgOwned -and [bool]$config.org_hardening.require_code_owner_review) { $expectedCodeOwnerReview = $true }

  if (-not $meta.has_issues) { $problems.Add('Issues disabled') }
  if (-not $meta.allow_auto_merge) { $problems.Add('auto-merge off') }
  if (-not $meta.allow_update_branch) { $problems.Add('update-branch off') }
  if (-not $meta.delete_branch_on_merge) { $problems.Add('delete-branch off') }
  if (-not $meta.allow_squash_merge) { $problems.Add('squash off') }
  if ($meta.allow_merge_commit) { $problems.Add('merge commits enabled') }
  if ($meta.allow_rebase_merge) { $problems.Add('rebase enabled') }

  $actionsRaw = & gh api "repos/$repo/actions/permissions" 2>&1
  if ($LASTEXITCODE -ne 0) { $problems.Add('cannot read Actions permissions') }
  else {
    $actions = ($actionsRaw -join "`n") | ConvertFrom-Json
    if (-not [bool]$actions.enabled) { $problems.Add('Actions disabled') }
  }

  $codeownersRaw = & gh api -H 'Accept: application/vnd.github.raw+json' "repos/$repo/contents/.github/CODEOWNERS?ref=$($meta.default_branch)" 2>&1
  if ($LASTEXITCODE -ne 0) { $problems.Add('CODEOWNERS missing') } else {
    $expectedTail = if ($name -eq 'agent-engineering-standard') { $standardTail } else { $appTail }
    if (-not (Test-CodeownersTail -Content ($codeownersRaw -join "`n") -ExpectedTail $expectedTail)) { $problems.Add('CODEOWNERS ownership map drift') }
  }

  $aiWorkflowRaw = & gh api "repos/$repo/contents/.github/workflows/ai-review.yml?ref=$($meta.default_branch)" 2>&1
  if ($LASTEXITCODE -ne 0) { $problems.Add('AI Review caller workflow missing') }
  else {
    $workflowStateRaw = & gh api "repos/$repo/actions/workflows/ai-review.yml" 2>&1
    if ($LASTEXITCODE -ne 0) { $problems.Add('cannot read AI Review workflow state') }
    else {
      $workflowState = ($workflowStateRaw -join "`n") | ConvertFrom-Json
      if ($workflowState.state -ne 'active') { $problems.Add("AI Review workflow not active: $($workflowState.state)") }
    }
  }

  $aiWorkflowRaw = & gh api "repos/$repo/contents/.github/workflows/ai-review.yml?ref=$($meta.default_branch)" 2>&1
  if ($LASTEXITCODE -ne 0) { $problems.Add('AI Review caller workflow missing') }

  $rulesetsRaw = & gh api "repos/$repo/rulesets" 2>&1
  if ($LASTEXITCODE -ne 0) { $problems.Add('cannot read rulesets') } else {
    $summary = ((($rulesetsRaw -join "`n") | ConvertFrom-Json) | Where-Object { $_.name -eq $config.ruleset_name } | Select-Object -First 1)
    if (-not $summary) { $problems.Add('ruleset missing') } else {
      $detailRaw = & gh api "repos/$repo/rulesets/$($summary.id)" 2>&1
      if ($LASTEXITCODE -ne 0) { $problems.Add('cannot read ruleset details') } else {
        $detail = ($detailRaw -join "`n") | ConvertFrom-Json
        if ($detail.enforcement -ne 'active') { $problems.Add('ruleset not active') }
        if ($detail.bypass_actors -and @($detail.bypass_actors).Count -gt 0) { $problems.Add('ruleset has bypass actors') }
        if (-not (@($detail.conditions.ref_name.include) -contains '~DEFAULT_BRANCH')) { $problems.Add('ruleset does not target default branch') }
        $types = @($detail.rules | ForEach-Object { $_.type })
        foreach ($requiredType in @('deletion','non_fast_forward','pull_request','required_status_checks')) {
          if ($types -notcontains $requiredType) { $problems.Add("missing rule: $requiredType") }
        }
        $prRule = $detail.rules | Where-Object { $_.type -eq 'pull_request' } | Select-Object -First 1
        if ($prRule) {
          if ([int]$prRule.parameters.required_approving_review_count -ne 0) { $problems.Add('human approval requirement is not zero') }
          if ([bool]$prRule.parameters.require_code_owner_review -ne $expectedCodeOwnerReview) { $problems.Add('CODEOWNERS review policy drift') }
          if (-not $prRule.parameters.required_review_thread_resolution) { $problems.Add('review-thread resolution not required') }
          $allowed = @($prRule.parameters.allowed_merge_methods)
          if ($allowed.Count -ne 1 -or $allowed[0] -ne 'squash') { $problems.Add('ruleset not squash-only') }
        }
        $statusRule = $detail.rules | Where-Object { $_.type -eq 'required_status_checks' } | Select-Object -First 1
        if ($statusRule) {
          foreach ($context in @($config.required_status_context,$config.required_ai_review_context)) {
            $check = @($statusRule.parameters.required_status_checks) | Where-Object { $_.context -eq $context } | Select-Object -First 1
            if (-not $check) { $problems.Add("required context missing: $context") }
            elseif ([int]$check.integration_id -ne $actionsAppId) { $problems.Add("$context not bound to GitHub Actions") }
          }
        }
      }
    }
  }

  $legacyRaw = & gh api "repos/$repo/branches/$($meta.default_branch)/protection" 2>&1
  if ($LASTEXITCODE -eq 0) {
    foreach ($context in @(Get-StaleLegacyRequiredCheckContexts -Protection (($legacyRaw -join "`n") | ConvertFrom-Json) -RequiredContext $config.required_status_context)) { $problems.Add("stale legacy required check: $context") }
  } elseif (-not (Test-GitHubBranchProtectionAbsent -ErrorText ($legacyRaw -join "`n"))) { $problems.Add('cannot read legacy branch protection') }

  if ($problems.Count -eq 0) { Write-Host "${repo} : READY" -ForegroundColor Green }
  else {
    Write-Host "${repo} : $($problems -join ', ')" -ForegroundColor Yellow
    foreach ($problem in $problems) { $remoteFailures.Add("${repo}: $problem") }
  }
}

if ($remoteFailures.Count -gt 0) { throw "REMOTE: DRIFT DETECTED`n$($remoteFailures -join "`n")" }
Write-Host 'REMOTE: READY' -ForegroundColor Green
