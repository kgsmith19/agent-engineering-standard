param(
  [Parameter(Mandatory)][string]$Repo,
  [Parameter(Mandatory)][int]$Pr,
  [Parameter(Mandatory)][string]$GateConclusion,
  [Parameter(Mandatory)][string]$GateHeadSha,
  [Parameter(Mandatory)][long]$GateRunId,
  [string]$ConfigPath = (Join-Path $PSScriptRoot '..\policy\github-defaults.json')
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib/review-policy.ps1')
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw 'GitHub CLI (gh) is required.' }
$config = Get-Content $ConfigPath -Raw | ConvertFrom-Json
$automation = $config.pr_automation
$dispatchDisabled = -not [bool]$automation.repair_dispatch_enabled

function Get-Paged {
  param([string]$Endpoint)
  $raw = & gh api --paginate --slurp $Endpoint 2>&1
  if ($LASTEXITCODE -ne 0) { throw ($raw -join "`n") }
  $pages = ($raw -join "`n") | ConvertFrom-Json
  foreach ($page in @($pages)) { foreach ($item in @($page)) { $item } }
}

function Get-PrData {
  $raw = & gh pr view $Pr --repo $Repo --json state,isDraft,headRefOid,headRepository,headRepositoryOwner,autoMergeRequest 2>&1
  if ($LASTEXITCODE -ne 0) { throw ($raw -join "`n") }
  return (($raw -join "`n") | ConvertFrom-Json)
}

function Get-Comments { return @(Get-Paged "repos/$Repo/issues/$Pr/comments?per_page=100") }

function Add-TrustedCommentOnce {
  # MatchPattern deduplicates against both versioned and legacy marker forms.
  param([string]$Marker,[string]$Body,[string]$MatchPattern = '')
  if (-not $MatchPattern) { $MatchPattern = [regex]::Escape($Marker) }
  if (@(Get-Comments | Where-Object {
    (Test-TrustedAutomationComment -Comment $_ -OwnerLogin ([string]$config.owner)) -and
    [string]$_.body -match $MatchPattern
  }).Count -gt 0) { return }
  & gh pr comment $Pr --repo $Repo --body "$Body`n`n$Marker" | Out-Host
  if ($LASTEXITCODE -ne 0) { throw "Could not comment on $Repo PR #$Pr." }
}

function Get-GateBlockAdvice {
  param([string]$Code)
  $advice = @{
    'gate-rerun-exhausted'='inspect the workflow run for the repeated cancellation/staleness cause, fix it, and push or re-run manually; the bounded automatic rerun is spent.'
    'gate-rerun-failed'='re-run the workflow manually from the Actions tab and fix whatever made GitHub refuse the automatic rerun.'
    'gate-neutral'='make the deterministic gate produce success or an actionable failure; a neutral required gate cannot authorize a merge.'
    'gate-unknown'='inspect the new conclusion value and teach Get-GateConclusionDecision an explicit decision for it.'
  }
  if ($advice.ContainsKey($Code)) { return [string]$advice[$Code] }
  return 'inspect the reason above, fix the underlying condition, and the next gate run re-evaluates.'
}
function Set-GateBlock {
  param([string]$Code,[string]$Reason,$PrData)
  if ($PrData.autoMergeRequest) {
    & gh pr merge $Pr --repo $Repo --disable-auto 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Could not disable auto-merge for $Repo PR #$Pr." }
  }
  & gh pr edit $Pr --repo $Repo --add-label $automation.blocked_label 2>&1 | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "Could not add $($automation.blocked_label) to $Repo PR #$Pr." }
  # While dispatch is disabled no comment @-mentions a human; the owner is named.
  $ownerReference = if ($dispatchDisabled) { "the owner ($($config.owner))" } else { "@$($config.owner)" }
  $body = "Automation put this PR on hold ($Code): $Reason`n`nNext step: $(Get-GateBlockAdvice $Code)`n`nDecision contact: $ownerReference — named for the decision, never assigned as a reviewer."
  Add-TrustedCommentOnce "<!-- automation:v1:block:${Code}:$GateHeadSha -->" $body "<!-- automation:(?:v\d+:)?block:${Code}:$GateHeadSha -->"
}

$prData = Get-PrData
if ($prData.state -ne 'OPEN' -or $prData.isDraft) { exit 0 }
if ([string]$prData.headRefOid -ne $GateHeadSha) { exit 0 }
$headRepo = "$([string]$prData.headRepositoryOwner.login)/$([string]$prData.headRepository.name)"
if ($headRepo -ne $Repo) {
  Write-Host "FORK-DENIED: $Repo PR #$Pr head repository '$headRepo' is not the target repository; gate-result automation refuses cross-repository PRs."
  exit 0
}

$decision = Get-GateConclusionDecision -Conclusion $GateConclusion
if ($decision -in @('success','repair','block-workflow-approval','block-gate-skipped')) {
  & pwsh -NoProfile -File (Join-Path $PSScriptRoot 'pr-orchestrator.ps1') `
    -Mode gate-result `
    -Repo $Repo `
    -Pr $Pr `
    -GateConclusion $GateConclusion `
    -GateHeadSha $GateHeadSha `
    -GateRunId $GateRunId
  exit $LASTEXITCODE
}

if ($decision -eq 'rerun') {
  $limit = [int]$automation.max_gate_rerun_attempts
  $attempts = @(Get-Comments | Where-Object {
    (Test-TrustedAutomationComment -Comment $_ -OwnerLogin ([string]$config.owner)) -and
    [string]$_.body -match "<!-- auto-rerun:(?:v\d+:)?gate:$([regex]::Escape($GateHeadSha)):[0-9]+ -->"
  }).Count
  if ($attempts -ge $limit) {
    Set-GateBlock 'gate-rerun-exhausted' "PR Gate ended '$GateConclusion' again after the bounded automatic rerun." $prData
    exit 0
  }

  $raw = & gh api --method POST "repos/$Repo/actions/runs/$GateRunId/rerun" 2>&1
  if ($LASTEXITCODE -ne 0) {
    Set-GateBlock 'gate-rerun-failed' "PR Gate ended '$GateConclusion' and GitHub refused the automatic rerun: $($raw -join ' ')" $prData
    exit 0
  }
  Add-TrustedCommentOnce "<!-- auto-rerun:v1:gate:${GateHeadSha}:${GateRunId} -->" "AUTOMATION-RECOVERY: PR Gate ended '$GateConclusion' on the current head, so GitHub reran the same workflow once before escalating." "<!-- auto-rerun:(?:v\d+:)?gate:${GateHeadSha}:${GateRunId} -->"
  exit 0
}

if ($decision -eq 'block-gate-neutral') {
  Set-GateBlock 'gate-neutral' 'PR Gate completed neutral on the current head. A required deterministic gate must produce success or an actionable failure.' $prData
  exit 0
}

Set-GateBlock 'gate-unknown' "PR Gate returned unsupported conclusion '$GateConclusion'. The control plane failed closed instead of ignoring it." $prData
