param(
  [Parameter(Mandatory)][string]$Repo,
  [Parameter(Mandatory)][int]$Pr,
  [ValidateSet('R0','R1','R2','R3','R4')][string]$Risk = 'R2',
  [ValidateSet('claude','copilot','codex','human','unknown')][string]$Implementer = 'unknown'
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib/review-policy.ps1')

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw 'GitHub CLI (gh) is required.' }
& gh auth status | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'gh is not authenticated.' }

$config = Get-Content (Join-Path $PSScriptRoot '..\policy\github-defaults.json') -Raw | ConvertFrom-Json

$prRaw = & gh pr view $Pr --repo $Repo --json isDraft,state,headRefOid,body 2>&1
if ($LASTEXITCODE -ne 0) { throw ($prRaw -join "`n") }
$prInfo = ($prRaw -join "`n") | ConvertFrom-Json
if ($prInfo.state -ne 'OPEN') { throw "PR #$Pr is not open." }
if ($prInfo.isDraft) { throw "PR #$Pr is still draft. Finish implementation and mark it ready first." }

if ($Implementer -eq 'unknown' -and $prInfo.body -match '(?im)^\s*Implementer:\s*(claude|copilot|codex|human)\s*$') {
  $Implementer = $Matches[1].ToLowerInvariant()
}
if ($Implementer -eq 'unknown') {
  throw "Auto-merge requires an Implementer: claude|copilot|codex|human line in the PR body (or -Implementer explicitly) so reviewer independence can be proven."
}

$riskNumber = [int]$Risk.Substring(1)
$maxRisk = [int]([string]$config.auto_merge_max_risk).Substring(1)
if ($riskNumber -gt $maxRisk) {
  throw "Auto-merge refused: $Risk exceeds configured auto_merge_max_risk $($config.auto_merge_max_risk)."
}
if ($Risk -eq 'R4') {
  throw "Auto-merge refused: R4 is destructive/financial/privileged/irreversible. The manual authorization gate exists to prove intentional authority, not to compensate for weak review. Record failure class, why automation is insufficient, decision owner, and the condition that will eliminate the gate."
}

$filesRaw = & gh api --paginate "repos/$Repo/pulls/$Pr/files?per_page=100" --jq '.[].filename' 2>&1
if ($LASTEXITCODE -ne 0) { throw ($filesRaw -join "`n") }
$files = @($filesRaw)
$controlPlanePatterns = @(
  '^\.github/workflows/',
  '^\.agent/',
  '^AGENTS\.md$',
  '^policy/',
  '^scripts/(apply-github-standard|doctor|auto-merge|request-independent-review|upgrade-repos|bootstrap-repo|codex-review|sync-agentic-project)\.ps1$',
  '^scripts/lib/',
  '^(AGENT_RULES|QUALITY_RULES|SECURITY_RISK_AUTONOMY|DELIVERY_GITHUB|EVIDENCE_LEARNING)\.md$'
)
$controlPlane = $Repo -match '/agent-engineering-standard$'
foreach ($file in $files) {
  if ($controlPlanePatterns | Where-Object { $file -match $_ }) { $controlPlane = $true; break }
}
if ($controlPlane -and $riskNumber -lt 3) {
  throw "Auto-merge refused: control-plane changes must declare at least R3. Risk may be raised, never lowered to enter a cheaper lane."
}

# Fail closed unless the live GitHub integration plane is actually enforcing the policy.
$metaRaw = & gh api "repos/$Repo" 2>&1
if ($LASTEXITCODE -ne 0) { throw "Cannot inspect live repository settings for $Repo." }
$meta = ($metaRaw -join "`n") | ConvertFrom-Json
if (-not $meta.allow_auto_merge) { throw "Live GitHub setting drift: auto-merge is off. Run setup-portfolio.ps1." }
if (-not $meta.allow_squash_merge -or $meta.allow_merge_commit -or $meta.allow_rebase_merge) {
  throw "Live GitHub merge-method drift: repository is not squash-only. Run setup-portfolio.ps1."
}

$rulesetsRaw = & gh api "repos/$Repo/rulesets" 2>&1
if ($LASTEXITCODE -ne 0) { throw "Cannot inspect live rulesets for $Repo." }
$rulesets = ($rulesetsRaw -join "`n") | ConvertFrom-Json
$summary = $rulesets | Where-Object { $_.name -eq $config.ruleset_name } | Select-Object -First 1
if (-not $summary) { throw "Live ruleset '$($config.ruleset_name)' is missing. Run setup-portfolio.ps1." }
$detailRaw = & gh api "repos/$Repo/rulesets/$($summary.id)" 2>&1
if ($LASTEXITCODE -ne 0) { throw "Cannot inspect live ruleset '$($config.ruleset_name)'." }
$detail = ($detailRaw -join "`n") | ConvertFrom-Json
if ($detail.enforcement -ne 'active') { throw "Live ruleset is not active." }
if ($detail.bypass_actors -and @($detail.bypass_actors).Count -gt 0) { throw "Live ruleset has bypass actors; refusing auto-merge." }

$prRule = $detail.rules | Where-Object { $_.type -eq 'pull_request' } | Select-Object -First 1
if (-not $prRule) { throw 'Live ruleset does not require pull requests.' }
if ([int]$prRule.parameters.required_approving_review_count -ne 0) { throw 'Human approval requirement detected; portfolio default must be 0.' }
if ([bool]$prRule.parameters.require_code_owner_review) { throw 'Required Code Owner review detected on a personal-repo lane; this would deadlock solo automation.' }
if (-not [bool]$prRule.parameters.required_review_thread_resolution) { throw 'Review-thread resolution is not required; refusing auto-merge.' }
$methods = @($prRule.parameters.allowed_merge_methods)
if ($methods.Count -ne 1 -or $methods[0] -ne 'squash') { throw 'Ruleset is not squash-only.' }

$statusRule = $detail.rules | Where-Object { $_.type -eq 'required_status_checks' } | Select-Object -First 1
if (-not $statusRule) { throw 'Live ruleset has no required-status-check rule.' }
$requiredCheck = @($statusRule.parameters.required_status_checks) | Where-Object { $_.context -eq $config.required_status_context } | Select-Object -First 1
if (-not $requiredCheck) { throw "Live ruleset does not require '$($config.required_status_context)'." }

# An agent review is required, but it is a status/semantic gate rather than a required human approval.
$reviewsRaw = & gh api --paginate --slurp "repos/$Repo/pulls/$Pr/reviews?per_page=100" 2>&1
if ($LASTEXITCODE -ne 0) { throw ($reviewsRaw -join "`n") }
$reviewPages = ($reviewsRaw -join "`n") | ConvertFrom-Json
$reviews = @($reviewPages | ForEach-Object { $_ })
$currentIndependent = @(
  $reviews | Where-Object {
    $provider = Get-ReviewProviderFromLogin -Login $_.user.login
    $_.commit_id -eq $prInfo.headRefOid -and
    $provider -and
    (Test-IndependentReview -Implementer $Implementer -ReviewerProvider $provider)
  }
)
if ($currentIndependent.Count -eq 0) {
  throw "No independent AI review exists on current head $($prInfo.headRefOid). Run request-independent-review.ps1 after the final substantive push."
}

$reviewer = $currentIndependent[-1].user.login
& gh pr merge $Pr --repo $Repo --auto --squash
if ($LASTEXITCODE -ne 0) { throw "Could not enable auto-merge for $Repo PR #$Pr." }
Write-Host "AUTO-MERGE ARMED: $Repo PR #$Pr ($Risk), independent reviewer $reviewer. GitHub remains the authority: required PR Gate + resolved threads must pass before merge." -ForegroundColor Green
