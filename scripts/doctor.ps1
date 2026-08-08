param(
  [switch]$Remote,
  [string]$ConfigPath = (Join-Path $PSScriptRoot "..\policy\github-defaults.json")
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
. (Join-Path $PSScriptRoot 'lib/legacy-protection.ps1')

function Test-CodeownersTail {
  param(
    [Parameter(Mandatory)][string]$Content,
    [Parameter(Mandatory)][string[]]$ExpectedTail
  )

  $rules = @(
    $Content -split "`r?`n" |
      ForEach-Object { $_.Trim() } |
      Where-Object { $_ -and -not $_.StartsWith('#') }
  )
  if ($rules.Count -lt $ExpectedTail.Count) { return $false }
  $start = $rules.Count - $ExpectedTail.Count
  for ($i = 0; $i -lt $ExpectedTail.Count; $i++) {
    if ($rules[$start + $i] -ne $ExpectedTail[$i]) { return $false }
  }
  return $true
}

$required = @(
  "README.md", "LIFECYCLE.md", "AGENT_RULES.md", "QUALITY_RULES.md",
  "SECURITY_RISK_AUTONOMY.md", "DELIVERY_GITHUB.md", "EVIDENCE_LEARNING.md",
  "AGENTS.md", ".github/CODEOWNERS", "policy/github-defaults.json",
  "scripts/setup-portfolio.ps1", "scripts/apply-github-standard.ps1", "scripts/sync-agentic-project.ps1",
  "scripts/codex-review.ps1", "scripts/auto-merge.ps1",
  "scripts/bootstrap-repo.ps1", "scripts/upgrade-repos.ps1", "scripts/lib/legacy-protection.ps1",
  "tests/legacy-protection.tests.ps1",
  ".github/workflows/ci.yml", "templates/AGENTS.md", "templates/CODEOWNERS", "templates/PR_GATE.yml",
  "templates/PRD.md", "templates/SPEC.md", "templates/ADR.md",
  "templates/ISSUE.md", "templates/PULL_REQUEST.md"
)
foreach ($relative in $required) {
  if (-not (Test-Path (Join-Path $root $relative))) { throw "Missing required file: $relative" }
}

$config = Get-Content (Join-Path $root "policy/github-defaults.json") -Raw | ConvertFrom-Json
if ($config.required_status_context -ne "PR Gate") { throw "required_status_context must be 'PR Gate'" }
if ($config.required_approving_review_count -ne 0) { throw "Default approval count must remain 0; review is risk-driven." }
if ($config.require_code_owner_review) { throw "Personal-account default must not require Code Owner approval; the PR author cannot approve their own PR." }
if (-not $config.org_hardening -or -not [bool]$config.org_hardening.require_code_owner_review) { throw "Organization hardening must retain Code Owner review." }
if ($config.auto_merge_max_risk -ne 'R2') { throw "auto_merge_max_risk must remain R2 unless the risk model is explicitly redesigned." }
if (-not $config.control_plane_requires_fresh_external_review) { throw "Control-plane changes must require fresh external review." }

$ownerToken = "@$($config.owner)"
$appCodeownersTail = @(
  "/.github/workflows/ $ownerToken",
  "/.github/CODEOWNERS $ownerToken",
  "/.agent/ $ownerToken",
  "/AGENTS.md $ownerToken"
)
$standardCodeownersTail = @(
  "/.github/workflows/ $ownerToken",
  "/.github/CODEOWNERS $ownerToken",
  "/policy/ $ownerToken",
  "/scripts/ $ownerToken",
  "/AGENTS.md $ownerToken",
  "/AGENT_RULES.md $ownerToken",
  "/QUALITY_RULES.md $ownerToken",
  "/SECURITY_RISK_AUTONOMY.md $ownerToken",
  "/DELIVERY_GITHUB.md $ownerToken"
)

$localStandardCodeowners = Get-Content (Join-Path $root '.github/CODEOWNERS') -Raw
if (-not (Test-CodeownersTail -Content $localStandardCodeowners -ExpectedTail $standardCodeownersTail)) {
  throw "Local .github/CODEOWNERS does not end with the canonical standards ownership map."
}
$localTemplateCodeowners = Get-Content (Join-Path $root 'templates/CODEOWNERS') -Raw
if (-not (Test-CodeownersTail -Content $localTemplateCodeowners -ExpectedTail $appCodeownersTail)) {
  throw "templates/CODEOWNERS does not end with the canonical app ownership map."
}

$psScripts = @(
  "scripts/setup-portfolio.ps1", "scripts/apply-github-standard.ps1", "scripts/sync-agentic-project.ps1",
  "scripts/codex-review.ps1", "scripts/auto-merge.ps1",
  "scripts/bootstrap-repo.ps1", "scripts/upgrade-repos.ps1", "scripts/doctor.ps1",
  "scripts/lib/legacy-protection.ps1", "tests/legacy-protection.tests.ps1"
)
foreach ($relative in $psScripts) {
  $tokens = $null
  $errors = $null
  [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $root $relative), [ref]$tokens, [ref]$errors) | Out-Null
  if ($errors.Count -gt 0) { throw "PowerShell parse failed: $relative :: $($errors[0].Message)" }
}

Write-Host "LOCAL: READY" -ForegroundColor Green
if (-not $Remote) { exit 0 }
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw "gh is required for -Remote." }

$actionsAppRaw = & gh api /apps/github-actions 2>&1
if ($LASTEXITCODE -ne 0) { throw "Could not resolve GitHub Actions App identity." }
$actionsAppId = [int]((($actionsAppRaw -join "`n") | ConvertFrom-Json).id)
$remoteFailures = New-Object System.Collections.Generic.List[string]

foreach ($name in $config.repositories) {
  $repo = "$($config.owner)/$name"
  $problems = New-Object System.Collections.Generic.List[string]

  $metaRaw = & gh api "repos/$repo" 2>&1
  if ($LASTEXITCODE -ne 0) { $remoteFailures.Add("${repo}: cannot read repository"); continue }
  $meta = ($metaRaw -join "`n") | ConvertFrom-Json
  $isOrgOwned = $meta.owner.type -eq 'Organization'
  $expectedCodeOwnerReview = [bool]$config.require_code_owner_review
  if ($isOrgOwned -and $config.org_hardening -and [bool]$config.org_hardening.require_code_owner_review) {
    $expectedCodeOwnerReview = $true
  }

  if (-not $meta.has_issues) { $problems.Add("Issues disabled") }
  if (-not $meta.allow_auto_merge) { $problems.Add("auto-merge off") }
  if (-not $meta.delete_branch_on_merge) { $problems.Add("delete-branch off") }
  if (-not $meta.allow_squash_merge) { $problems.Add("squash off") }
  if ($meta.allow_merge_commit) { $problems.Add("merge commits enabled") }
  if ($meta.allow_rebase_merge) { $problems.Add("rebase enabled") }

  $actionsRaw = & gh api "repos/$repo/actions/permissions" 2>&1
  if ($LASTEXITCODE -ne 0) { $problems.Add("cannot read Actions permissions") }
  else {
    $actions = ($actionsRaw -join "`n") | ConvertFrom-Json
    if (-not $actions.enabled) { $problems.Add("Actions disabled") }
  }

  $codeownersRaw = & gh api -H "Accept: application/vnd.github.raw+json" "repos/$repo/contents/.github/CODEOWNERS?ref=$($meta.default_branch)" 2>&1
  if ($LASTEXITCODE -ne 0) {
    $problems.Add("CODEOWNERS missing on default branch")
  }
  else {
    $codeowners = $codeownersRaw -join "`n"
    $expectedTail = if ($name -eq 'agent-engineering-standard') { $standardCodeownersTail } else { $appCodeownersTail }
    if (-not (Test-CodeownersTail -Content $codeowners -ExpectedTail $expectedTail)) {
      $problems.Add("CODEOWNERS effective tail does not match canonical ownership map")
    }
  }

  $rulesetsRaw = & gh api "repos/$repo/rulesets" 2>&1
  if ($LASTEXITCODE -ne 0) { $problems.Add("cannot read rulesets") }
  else {
    $rulesets = ($rulesetsRaw -join "`n") | ConvertFrom-Json
    $summary = $rulesets | Where-Object { $_.name -eq $config.ruleset_name } | Select-Object -First 1
    if (-not $summary) { $problems.Add("ruleset missing") }
    else {
      $detailRaw = & gh api "repos/$repo/rulesets/$($summary.id)" 2>&1
      if ($LASTEXITCODE -ne 0) { $problems.Add("cannot read ruleset details") }
      else {
        $detail = ($detailRaw -join "`n") | ConvertFrom-Json
        if ($detail.enforcement -ne 'active') { $problems.Add("ruleset not active") }
        if ($detail.bypass_actors -and @($detail.bypass_actors).Count -gt 0) { $problems.Add("ruleset has bypass actors") }
        if (-not (@($detail.conditions.ref_name.include) -contains '~DEFAULT_BRANCH')) { $problems.Add("ruleset does not target default branch") }

        $types = @($detail.rules | ForEach-Object { $_.type })
        foreach ($requiredType in @('deletion','non_fast_forward','pull_request','required_status_checks')) {
          if ($types -notcontains $requiredType) { $problems.Add("missing rule: $requiredType") }
        }

        $prRule = $detail.rules | Where-Object { $_.type -eq 'pull_request' } | Select-Object -First 1
        if ($prRule) {
          if ([int]$prRule.parameters.required_approving_review_count -ne [int]$config.required_approving_review_count) { $problems.Add("approval-count drift") }
          if ([bool]$prRule.parameters.require_code_owner_review -ne $expectedCodeOwnerReview) { $problems.Add("CODEOWNERS review policy drift") }
          if (-not $prRule.parameters.required_review_thread_resolution) { $problems.Add("review-thread resolution not required") }
          if (@($prRule.parameters.allowed_merge_methods) -notcontains 'squash') { $problems.Add("squash not allowed by PR rule") }
        }

        $statusRule = $detail.rules | Where-Object { $_.type -eq 'required_status_checks' } | Select-Object -First 1
        if ($statusRule) {
          if ([bool]$statusRule.parameters.strict_required_status_checks_policy -ne [bool]$config.strict_required_status_checks_policy) { $problems.Add("strict-status policy drift") }
          $requiredCheck = @($statusRule.parameters.required_status_checks) | Where-Object { $_.context -eq $config.required_status_context } | Select-Object -First 1
          if (-not $requiredCheck) { $problems.Add("required PR Gate context missing") }
          elseif ([int]$requiredCheck.integration_id -ne $actionsAppId) { $problems.Add("PR Gate not bound to GitHub Actions") }
        }

        if ($config.merge_queue.desired -and $isOrgOwned -and $types -notcontains 'merge_queue') { $problems.Add("merge queue missing on eligible repo") }
      }
    }
  }

  $legacyRaw = & gh api "repos/$repo/branches/$($meta.default_branch)/protection" 2>&1
  if ($LASTEXITCODE -eq 0) {
    $legacy = ($legacyRaw -join "`n") | ConvertFrom-Json
    foreach ($context in @(Get-StaleLegacyRequiredCheckContexts -Protection $legacy -RequiredContext $config.required_status_context)) {
      $problems.Add("stale legacy required check: $context")
    }
  }
  else {
    $legacyError = $legacyRaw -join "`n"
    if (-not (Test-GitHubBranchProtectionAbsent -ErrorText $legacyError)) {
      $problems.Add("cannot read legacy branch protection")
    }
  }

  if ($problems.Count -eq 0) { Write-Host "${repo} : READY" -ForegroundColor Green }
  else {
    Write-Host "${repo} : $($problems -join ', ')" -ForegroundColor Yellow
    foreach ($problem in $problems) { $remoteFailures.Add("${repo}: $problem") }
  }

  if ($config.merge_queue.desired -and -not $isOrgOwned) {
    Write-Host "  merge queue: waiting on transfer to a supported GitHub organization" -ForegroundColor DarkYellow
  }
}

if ($remoteFailures.Count -gt 0) { throw "REMOTE: DRIFT DETECTED`n$($remoteFailures -join "`n")" }
Write-Host "REMOTE: READY" -ForegroundColor Green
