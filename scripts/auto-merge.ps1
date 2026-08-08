param(
  [Parameter(Mandatory)][string]$Repo,
  [Parameter(Mandatory)][int]$Pr,
  [ValidateSet('R0','R1','R2','R3','R4')][string]$Risk = 'R2'
)

$ErrorActionPreference = 'Stop'
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw 'GitHub CLI (gh) is required.' }
& gh auth status | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'gh is not authenticated.' }

$config = Get-Content (Join-Path $PSScriptRoot '..\policy\github-defaults.json') -Raw | ConvertFrom-Json
$prRaw = & gh pr view $Pr --repo $Repo --json isDraft,state,labels,baseRefName 2>&1
if ($LASTEXITCODE -ne 0) { throw ($prRaw -join "`n") }
$pr = ($prRaw -join "`n") | ConvertFrom-Json
if ($pr.state -ne 'OPEN') { throw "PR #$Pr is not open." }
if ($pr.isDraft) { throw "PR #$Pr is draft." }
if (@($pr.labels | ForEach-Object { $_.name }) -contains 'status:blocked') { throw "PR #$Pr is status:blocked." }

$riskNumber = [int]$Risk.Substring(1)
$maxRisk = [int]([string]$config.auto_merge_max_risk).Substring(1)
if ($riskNumber -gt $maxRisk -or $Risk -eq 'R4') { throw "Auto-merge refused for $Risk; configured maximum is $($config.auto_merge_max_risk)." }

$filesRaw = & gh api --paginate "repos/$Repo/pulls/$Pr/files?per_page=100" --jq '.[].filename' 2>&1
if ($LASTEXITCODE -ne 0) { throw ($filesRaw -join "`n") }
$controlPlanePatterns = @(
  '^\.github/workflows/', '^\.agent/', '^AGENTS\.md$', '^policy/', '^scripts/lib/',
  '^scripts/(apply-github-standard|doctor|auto-merge|request-independent-review|upgrade-repos|bootstrap-repo|codex-review|sync-agentic-project)\.ps1$',
  '^(AGENT_RULES|QUALITY_RULES|SECURITY_RISK_AUTONOMY|DELIVERY_GITHUB|EVIDENCE_LEARNING)\.md$'
)
$controlPlane = $Repo -match '/agent-engineering-standard$'
foreach ($file in @($filesRaw)) { if ($controlPlanePatterns | Where-Object { $file -match $_ }) { $controlPlane = $true; break } }
if ($controlPlane -and $riskNumber -lt 3) { throw 'Control-plane changes must declare at least R3.' }
if ($controlPlane -and [bool]$config.manual_gates.control_plane.required) {
  throw "Auto-merge refused by justified control-plane gate. Removal condition: $($config.manual_gates.control_plane.gate_removal_condition)"
}

$metaRaw = & gh api "repos/$Repo" 2>&1
if ($LASTEXITCODE -ne 0) { throw "Cannot inspect live repository settings for $Repo." }
$meta = ($metaRaw -join "`n") | ConvertFrom-Json
if ($pr.baseRefName -ne $meta.default_branch) { throw "Auto-merge refused: PR #$Pr targets '$($pr.baseRefName)', not protected default branch '$($meta.default_branch)'." }
if (-not $meta.allow_auto_merge) { throw 'Live GitHub setting drift: auto-merge is off.' }
if (-not $meta.allow_squash_merge -or $meta.allow_merge_commit -or $meta.allow_rebase_merge) { throw 'Live GitHub merge policy is not squash-only.' }
$isOrgOwned = $meta.owner.type -eq 'Organization'
$expectedCodeOwnerReview = [bool]$config.require_code_owner_review
if ($isOrgOwned -and [bool]$config.org_hardening.require_code_owner_review) { $expectedCodeOwnerReview = $true }

$actionsAppRaw = & gh api /apps/github-actions 2>&1
if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve GitHub Actions App identity.' }
$actionsAppId = [int]((($actionsAppRaw -join "`n") | ConvertFrom-Json).id)

$rulesetsRaw = & gh api "repos/$Repo/rulesets" 2>&1
if ($LASTEXITCODE -ne 0) { throw "Cannot inspect live rulesets for $Repo." }
$summary = ((($rulesetsRaw -join "`n") | ConvertFrom-Json) | Where-Object { $_.name -eq $config.ruleset_name } | Select-Object -First 1)
if (-not $summary) { throw "Live ruleset '$($config.ruleset_name)' is missing." }
$detailRaw = & gh api "repos/$Repo/rulesets/$($summary.id)" 2>&1
if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect live ruleset details.' }
$detail = ($detailRaw -join "`n") | ConvertFrom-Json
if ($detail.enforcement -ne 'active') { throw 'Live ruleset is not active.' }
if ($detail.bypass_actors -and @($detail.bypass_actors).Count -gt 0) { throw 'Live ruleset has bypass actors.' }
if (-not (@($detail.conditions.ref_name.include) -contains '~DEFAULT_BRANCH')) { throw 'Live ruleset does not protect the default branch.' }

$prRule = $detail.rules | Where-Object { $_.type -eq 'pull_request' } | Select-Object -First 1
if (-not $prRule) { throw 'Live ruleset does not require pull requests.' }
if ([int]$prRule.parameters.required_approving_review_count -ne 0) { throw 'Human approval requirement is not zero.' }
if ([bool]$prRule.parameters.require_code_owner_review -ne $expectedCodeOwnerReview) { throw 'Code Owner review policy drift detected.' }
if (-not [bool]$prRule.parameters.required_review_thread_resolution) { throw 'Review-thread resolution is not required.' }
$methods = @($prRule.parameters.allowed_merge_methods)
if ($methods.Count -ne 1 -or $methods[0] -ne 'squash') { throw 'Ruleset is not squash-only.' }

$statusRule = $detail.rules | Where-Object { $_.type -eq 'required_status_checks' } | Select-Object -First 1
if (-not $statusRule) { throw 'Live ruleset has no required-status-check rule.' }
foreach ($context in @($config.required_status_context, $config.required_ai_review_context)) {
  $required = @($statusRule.parameters.required_status_checks) | Where-Object { $_.context -eq $context } | Select-Object -First 1
  if (-not $required) { throw "Live ruleset does not require '$context'." }
  if ([int]$required.integration_id -ne $actionsAppId) { throw "Required '$context' is not bound to GitHub Actions." }
}

& gh pr merge $Pr --repo $Repo --auto --squash
if ($LASTEXITCODE -ne 0) { throw "Could not enable auto-merge for $Repo PR #$Pr." }
Write-Host "AUTO-MERGE ARMED: $Repo PR #$Pr ($Risk). GitHub now requires exact-head PR Gate + AI Review and resolved review threads before merge." -ForegroundColor Green
