param(
  [switch]$Remote,
  [string]$ConfigPath = (Join-Path $PSScriptRoot "..\policy\github-defaults.json")
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $PSScriptRoot 'lib/legacy-protection.ps1')
. (Join-Path $PSScriptRoot 'lib/review-policy.ps1')
. (Join-Path $PSScriptRoot 'lib/standard-lock.ps1')

$required = @(
  'README.md','LIFECYCLE.md','AGENT_RULES.md','QUALITY_RULES.md','SECURITY_RISK_AUTONOMY.md','DELIVERY_GITHUB.md','EVIDENCE_LEARNING.md','AGENTS.md',
  '.github/workflows/ci.yml','.github/workflows/ai-review.yml','.github/workflows/ai-review-reusable.yml','.github/workflows/pr-automation.yml','.github/workflows/pr-automation-reusable.yml','policy/github-defaults.json',
  'scripts/setup-portfolio.ps1','scripts/apply-github-standard.ps1','scripts/sync-agentic-project.ps1','scripts/codex-review.ps1','scripts/request-machine-review.ps1','scripts/auto-merge.ps1','scripts/pr-orchestrator.ps1','scripts/bootstrap-repo.ps1','scripts/upgrade-repos.ps1','scripts/prune-portfolio.ps1',
  'scripts/lib/legacy-protection.ps1','scripts/lib/standard-lock.ps1','scripts/lib/review-policy.ps1',
  'tests/legacy-protection.tests.ps1','tests/standard-lock.tests.ps1','tests/review-policy.tests.ps1','tests/standard-hygiene.tests.ps1',
  'templates/.gitignore','templates/AGENTS.md','templates/PR_GATE.yml','templates/AI_REVIEW.yml','templates/PR_AUTOMATION.yml','templates/dependabot.yml','templates/PRD.md','templates/SPEC.md','templates/ADR.md','templates/ISSUE.md','templates/PULL_REQUEST.md'
)
foreach ($relative in $required) {
  if (-not (Test-Path (Join-Path $root $relative))) { throw "Missing required file: $relative" }
}
if (Test-Path (Join-Path $root '.github/CODEOWNERS')) { throw 'Native CODEOWNERS must remain absent: normal automation must never request a human reviewer.' }
if (Test-Path (Join-Path $root 'templates/CODEOWNERS')) { throw 'Native CODEOWNERS bootstrap template must remain absent.' }

$config = Get-Content $ConfigPath -Raw | ConvertFrom-Json
if ($config.required_status_context -ne 'PR Gate') { throw "required_status_context must be 'PR Gate'" }
if ($config.required_ai_review_context -ne 'AI Review') { throw "required_ai_review_context must be 'AI Review'" }
if ([int]$config.required_approving_review_count -ne 0) { throw 'Default human approval count must remain 0.' }
if ([bool]$config.require_code_owner_review -or [bool]$config.native_codeowners) { throw 'Normal lane must not use native CODEOWNERS or Code Owner approval.' }
if ([bool]$config.org_hardening.require_code_owner_review) { throw 'Organization hardening must not silently reintroduce human Code Owner review.' }
if (-not [bool]$config.allow_auto_merge -or -not [bool]$config.allow_update_branch) { throw 'Safe automated lane requires auto-merge + update-branch enabled.' }
if ([bool]$config.allow_merge_commit -or [bool]$config.allow_rebase_merge -or -not [bool]$config.allow_squash_merge -or $config.merge_method -ne 'squash') { throw 'Repository merge policy must remain squash-only.' }
if ($config.auto_merge_max_risk -ne 'R3') { throw 'auto_merge_max_risk must remain R3; R4 requires explicit authority.' }

$review = $config.independent_review
if (-not [bool]$review.required_for_auto_merge) { throw 'Machine AI review must be required before auto-merge.' }
if ($review.preferred_provider -ne 'codex' -or $review.fallback_provider -ne 'copilot' -or $review.local_codex_model -ne 'gpt-5.4-mini') { throw 'Machine-review provider/cost policy drifted.' }
if ([int]$review.max_review_heads_per_pr -ne 2) { throw 'Normal semantic-review budget must remain initial head + one post-fix head.' }
if ([bool]$review.review_drafts -or [bool]$review.review_on_every_push) { throw 'Draft/every-push AI review spend must remain off.' }

$automation = $config.pr_automation
if ($automation.draft_ready_label -ne 'status:ready' -or $automation.blocked_label -ne 'status:blocked') { throw 'PR automation labels drifted.' }
foreach ($pair in @(@('max_ci_fix_attempts',3),@('max_review_fix_attempts',2),@('max_conflict_fix_attempts',2))) {
  if ([int]$automation.PSObject.Properties[$pair[0]].Value -ne [int]$pair[1]) { throw "PR automation budget drifted: $($pair[0])." }
}

foreach ($field in @('failure_class_prevented','why_automation_is_insufficient','decision_owner','gate_removal_condition')) {
  if (@($config.manual_gate_required_fields) -notcontains $field) { throw "manual_gate_required_fields missing '$field'." }
}
foreach ($gateName in @('control_plane','R4')) {
  $gate = $config.manual_gates.PSObject.Properties[$gateName].Value
  if (-not $gate -or -not [bool]$gate.required) { throw "Manual gate '$gateName' is not explicitly configured." }
  Assert-ManualGateJustification -Justification $gate | Out-Null
}

$psScripts = @(
  'scripts/setup-portfolio.ps1','scripts/apply-github-standard.ps1','scripts/sync-agentic-project.ps1','scripts/codex-review.ps1','scripts/request-machine-review.ps1','scripts/auto-merge.ps1','scripts/pr-orchestrator.ps1','scripts/bootstrap-repo.ps1','scripts/upgrade-repos.ps1','scripts/prune-portfolio.ps1','scripts/doctor.ps1',
  'scripts/lib/legacy-protection.ps1','scripts/lib/standard-lock.ps1','scripts/lib/review-policy.ps1','tests/legacy-protection.tests.ps1','tests/standard-lock.tests.ps1','tests/review-policy.tests.ps1','tests/standard-hygiene.tests.ps1'
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
  $repo = "$($config.owner)/$name"
  $problems = New-Object System.Collections.Generic.List[string]

  $metaRaw = & gh api "repos/$repo" 2>&1
  if ($LASTEXITCODE -ne 0) { $remoteFailures.Add("${repo}: cannot read repository"); continue }
  $meta = ($metaRaw -join "`n") | ConvertFrom-Json

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

  # Copilot cloud-agent PRs otherwise stop at "Approve and run workflows" and
  # require a maintainer. This setting is currently documented as UI-writable
  # but API-readable, so doctor fails until the one-time repo setting is OFF.
  $copilotRaw = & gh api -H 'X-GitHub-Api-Version: 2026-03-10' "repos/$repo/copilot/cloud-agent/configuration" 2>&1
  if ($LASTEXITCODE -ne 0) { $problems.Add('cannot read Copilot cloud-agent workflow-approval setting') }
  else {
    $copilot = ($copilotRaw -join "`n") | ConvertFrom-Json
    if ([bool]$copilot.require_actions_workflow_approval) { $problems.Add('Copilot cloud-agent Actions still require maintainer approval') }
  }

  $codeownersRaw = & gh api "repos/$repo/contents/.github/CODEOWNERS?ref=$($meta.default_branch)" 2>&1
  if ($LASTEXITCODE -eq 0) { $problems.Add('native CODEOWNERS present and can auto-request a human reviewer') }
  elseif (-not (($codeownersRaw -join "`n") -match '(?i)404|not found')) { $problems.Add('cannot determine whether native CODEOWNERS exists') }

  $workflowsRaw = & gh api "repos/$repo/actions/workflows?per_page=100" 2>&1
  if ($LASTEXITCODE -ne 0) { $problems.Add('cannot list Actions workflows') }
  else {
    $workflows = @(($workflowsRaw -join "`n") | ConvertFrom-Json | Select-Object -ExpandProperty workflows)
    if (@($workflows | Where-Object { $_.name -eq 'PR Gate' -and $_.state -eq 'active' }).Count -eq 0) { $problems.Add('active workflow named PR Gate missing') }
    if (@($workflows | Where-Object { $_.name -eq 'AI Review Gate' -and $_.state -eq 'active' }).Count -eq 0) { $problems.Add('active AI Review Gate workflow missing') }
    if (@($workflows | Where-Object { $_.name -eq 'PR Automation' -and $_.state -eq 'active' }).Count -eq 0) { $problems.Add('active PR Automation workflow missing') }
  }

  if ($name -ne 'agent-engineering-standard') {
    $lockRaw = & gh api -H 'Accept: application/vnd.github.raw+json' "repos/$repo/contents/.agent/standard.lock?ref=$($meta.default_branch)" 2>&1
    if ($LASTEXITCODE -ne 0) { $problems.Add('standard.lock missing') }
    else {
      try { $pinnedSha = Get-StandardLockRevision -Content ($lockRaw -join "`n") }
      catch { $pinnedSha = $null; $problems.Add('standard.lock revision unreadable') }
      foreach ($caller in @('ai-review.yml','pr-automation.yml')) {
        $callerRaw = & gh api -H 'Accept: application/vnd.github.raw+json' "repos/$repo/contents/.github/workflows/$caller?ref=$($meta.default_branch)" 2>&1
        if ($LASTEXITCODE -ne 0) { $problems.Add("$caller missing"); continue }
        $callerText = $callerRaw -join "`n"
        if ($callerText -match '@main\b|__STANDARD_SHA__') { $problems.Add("$caller follows moving/unresolved standard ref") }
        if ($pinnedSha -and $callerText -notmatch [regex]::Escape("@$pinnedSha")) { $problems.Add("$caller is not pinned to standard.lock revision") }
      }
    }
  }

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
        if (-not $prRule) { $problems.Add('pull-request rule missing') }
        else {
          if ([int]$prRule.parameters.required_approving_review_count -ne 0) { $problems.Add('human approval requirement is not zero') }
          if ([bool]$prRule.parameters.require_code_owner_review) { $problems.Add('Code Owner review requirement is on') }
          if (-not $prRule.parameters.required_review_thread_resolution) { $problems.Add('review-thread resolution not required') }
          $allowed = @($prRule.parameters.allowed_merge_methods)
          if ($allowed.Count -ne 1 -or $allowed[0] -ne 'squash') { $problems.Add('ruleset not squash-only') }
        }
        $statusRule = $detail.rules | Where-Object { $_.type -eq 'required_status_checks' } | Select-Object -First 1
        if (-not $statusRule) { $problems.Add('required-status rule missing') }
        else {
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
