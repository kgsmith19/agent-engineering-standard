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

$prRaw = & gh pr view $Pr --repo $Repo --json isDraft,state,headRefOid,body,labels 2>&1
if ($LASTEXITCODE -ne 0) { throw ($prRaw -join "`n") }
$prInfo = ($prRaw -join "`n") | ConvertFrom-Json
if ($prInfo.state -ne 'OPEN') { throw "PR #$Pr is not open." }
if ($prInfo.isDraft) { throw "PR #$Pr is still draft. Finish implementation and mark it ready first." }
if (@($prInfo.labels | ForEach-Object { $_.name }) -contains 'status:blocked') { throw "Auto-merge refused: PR #$Pr is status:blocked." }

if ($Implementer -eq 'unknown' -and $prInfo.body -match '(?im)^\s*Implementer:\s*(claude|copilot|codex|human)\s*$') { $Implementer = $Matches[1].ToLowerInvariant() }
if ($Implementer -eq 'unknown') { throw "Auto-merge requires an Implementer: claude|copilot|codex|human line in the PR body (or -Implementer explicitly)." }

$riskNumber = [int]$Risk.Substring(1)
$maxRisk = [int]([string]$config.auto_merge_max_risk).Substring(1)
if ($riskNumber -gt $maxRisk) { throw "Auto-merge refused: $Risk exceeds configured auto_merge_max_risk $($config.auto_merge_max_risk)." }
if ($Risk -eq 'R4') { throw "Auto-merge refused: R4 requires explicit authority for destructive/financial/privileged/irreversible consequence." }

$filesRaw = & gh api --paginate "repos/$Repo/pulls/$Pr/files?per_page=100" --jq '.[].filename' 2>&1
if ($LASTEXITCODE -ne 0) { throw ($filesRaw -join "`n") }
$files = @($filesRaw)
$controlPlanePatterns = @(
  '^\.github/workflows/', '^\.agent/', '^AGENTS\.md$', '^policy/', '^scripts/lib/',
  '^scripts/(apply-github-standard|doctor|auto-merge|request-independent-review|upgrade-repos|bootstrap-repo|codex-review|sync-agentic-project)\.ps1$',
  '^(AGENT_RULES|QUALITY_RULES|SECURITY_RISK_AUTONOMY|DELIVERY_GITHUB|EVIDENCE_LEARNING)\.md$'
)
$controlPlane = $Repo -match '/agent-engineering-standard$'
foreach ($file in $files) { if ($controlPlanePatterns | Where-Object { $file -match $_ }) { $controlPlane = $true; break } }
if ($controlPlane -and $riskNumber -lt 3) { throw "Auto-merge refused: control-plane changes must declare at least R3." }
if ($controlPlane -and [bool]$config.manual_gates.control_plane.required) { throw "Auto-merge refused: control-plane gate remains justified. Removal condition: $($config.manual_gates.control_plane.removal_condition)" }

$metaRaw = & gh api "repos/$Repo" 2>&1
if ($LASTEXITCODE -ne 0) { throw "Cannot inspect live repository settings for $Repo." }
$meta = ($metaRaw -join "`n") | ConvertFrom-Json
if (-not $meta.allow_auto_merge) { throw "Live GitHub setting drift: auto-merge is off. Run setup-portfolio.ps1." }
if (-not $meta.allow_squash_merge -or $meta.allow_merge_commit -or $meta.allow_rebase_merge) { throw "Live GitHub merge-method drift: repository is not squash-only. Run setup-portfolio.ps1." }
$isOrgOwned = $meta.owner.type -eq 'Organization'
$expectedCodeOwnerReview = [bool]$config.require_code_owner_review
if ($isOrgOwned -and $config.org_hardening -and [bool]$config.org_hardening.require_code_owner_review) { $expectedCodeOwnerReview = $true }

$actionsAppRaw = & gh api /apps/github-actions 2>&1
if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve GitHub Actions App identity.' }
$actionsAppId = [int]((($actionsAppRaw -join "`n") | ConvertFrom-Json).id)

$rulesetsRaw = & gh api "repos/$Repo/rulesets" 2>&1
if ($LASTEXITCODE -ne 0) { throw "Cannot inspect live rulesets for $Repo." }
$summary = ((($rulesetsRaw -join "`n") | ConvertFrom-Json) | Where-Object { $_.name -eq $config.ruleset_name } | Select-Object -First 1)
if (-not $summary) { throw "Live ruleset '$($config.ruleset_name)' is missing. Run setup-portfolio.ps1." }
$detailRaw = & gh api "repos/$Repo/rulesets/$($summary.id)" 2>&1
if ($LASTEXITCODE -ne 0) { throw "Cannot inspect live ruleset '$($config.ruleset_name)'." }
$detail = ($detailRaw -join "`n") | ConvertFrom-Json
if ($detail.enforcement -ne 'active') { throw 'Live ruleset is not active.' }
if ($detail.bypass_actors -and @($detail.bypass_actors).Count -gt 0) { throw 'Live ruleset has bypass actors; refusing auto-merge.' }

$prRule = $detail.rules | Where-Object { $_.type -eq 'pull_request' } | Select-Object -First 1
if (-not $prRule) { throw 'Live ruleset does not require pull requests.' }
if ([int]$prRule.parameters.required_approving_review_count -ne 0) { throw 'Human approval requirement detected; portfolio default must be 0.' }
if ([bool]$prRule.parameters.require_code_owner_review -ne $expectedCodeOwnerReview) { throw 'Code Owner review policy drift detected.' }
if (-not [bool]$prRule.parameters.required_review_thread_resolution) { throw 'Review-thread resolution is not required; refusing auto-merge.' }
$methods = @($prRule.parameters.allowed_merge_methods)
if ($methods.Count -ne 1 -or $methods[0] -ne 'squash') { throw 'Ruleset is not squash-only.' }

$statusRule = $detail.rules | Where-Object { $_.type -eq 'required_status_checks' } | Select-Object -First 1
if (-not $statusRule) { throw 'Live ruleset has no required-status-check rule.' }
$requiredCheck = @($statusRule.parameters.required_status_checks) | Where-Object { $_.context -eq $config.required_status_context } | Select-Object -First 1
if (-not $requiredCheck) { throw "Live ruleset does not require '$($config.required_status_context)'." }
if ([int]$requiredCheck.integration_id -ne $actionsAppId) { throw "Required '$($config.required_status_context)' is not bound to GitHub Actions." }

$reviewsRaw = & gh api --paginate --slurp "repos/$Repo/pulls/$Pr/reviews?per_page=100" 2>&1
if ($LASTEXITCODE -ne 0) { throw ($reviewsRaw -join "`n") }
$reviewPages = ($reviewsRaw -join "`n") | ConvertFrom-Json
$currentIndependent = @($reviewPages | ForEach-Object { $_ } | Where-Object {
  $provider = Get-ReviewProviderFromLogin -Login $_.user.login
  $_.commit_id -eq $prInfo.headRefOid -and $_.state -notin @('DISMISSED','PENDING') -and $provider -and (Test-IndependentReview -Implementer $Implementer -ReviewerProvider $provider)
} | Sort-Object submitted_at)
if ($currentIndependent.Count -eq 0) { throw "No independent AI review exists on current head $($prInfo.headRefOid). Run request-independent-review.ps1 after the final substantive push." }
$latestReview = $currentIndependent[-1]
if ($latestReview.state -eq 'CHANGES_REQUESTED') { throw "Latest independent review by $($latestReview.user.login) requests changes; refusing auto-merge." }

$reviewer = $latestReview.user.login
& gh pr merge $Pr --repo $Repo --auto --squash
if ($LASTEXITCODE -ne 0) { throw "Could not enable auto-merge for $Repo PR #$Pr." }
Write-Host "AUTO-MERGE ARMED: $Repo PR #$Pr ($Risk), independent reviewer $reviewer. GitHub remains the authority: required PR Gate + resolved threads must pass before merge." -ForegroundColor Green
