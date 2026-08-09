param(
  [Parameter(Mandatory)][string]$Repo,
  [Parameter(Mandatory)][int]$Pr
)

$ErrorActionPreference = 'Stop'
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw 'GitHub CLI (gh) is required.' }
$config = Get-Content (Join-Path $PSScriptRoot '..\policy\github-defaults.json') -Raw | ConvertFrom-Json
if (-not [bool]$config.pr_automation.external_draft_promotion) {
  Write-Host 'PROMOTION-SKIPPED: pr_automation.external_draft_promotion is disabled by policy.' -ForegroundColor Yellow
  exit 0
}

$prRaw = & gh api "repos/$Repo/pulls/$Pr" 2>&1
if ($LASTEXITCODE -ne 0) { throw ($prRaw -join "`n") }
$prData = ($prRaw -join "`n") | ConvertFrom-Json
if ([string]$prData.head.repo.full_name -ne $Repo) {
  Write-Host "FORK-DENIED: $Repo PR #$Pr head repository '$([string]$prData.head.repo.full_name)' is not the target repository; promotion never runs for fork heads."
  exit 0
}
if ($prData.state -ne 'open' -or -not $prData.draft) {
  Write-Host "PROMOTION-SKIPPED: $Repo PR #$Pr is not an open draft." -ForegroundColor Yellow
  exit 0
}
$author = [string]$prData.user.login
if ($author -eq [string]$config.owner -or $author -in @('github-actions[bot]','github-actions')) {
  Write-Host "PROMOTION-SKIPPED: author '$author' is not an external agent; ready-at-creation policy applies unchanged." -ForegroundColor Yellow
  exit 0
}
if ([string]::IsNullOrWhiteSpace($env:GH_TOKEN_ADMIN)) {
  # Fail closed without tagging a human: the dedicated automation identity is an
  # owner-provisioned prerequisite for acting on external-agent drafts.
  Write-Host 'PROMOTION-BLOCKED: automation-identity-missing'
  exit 0
}

$nodeId = [string]$prData.node_id
$previous = $env:GH_TOKEN
$env:GH_TOKEN = $env:GH_TOKEN_ADMIN
try {
  $mutationRaw = & gh api graphql -f query='mutation($id: ID!) { markPullRequestReadyForReview(input: { pullRequestId: $id }) { pullRequest { isDraft } } }' -f "id=$nodeId" 2>&1
  if ($LASTEXITCODE -ne 0) { throw ($mutationRaw -join "`n") }
} finally { $env:GH_TOKEN = $previous }

for ($poll = 1; $poll -le 5; $poll++) {
  $freshRaw = & gh api "repos/$Repo/pulls/$Pr" 2>&1
  if ($LASTEXITCODE -ne 0) { throw ($freshRaw -join "`n") }
  if (-not (($freshRaw -join "`n") | ConvertFrom-Json).draft) {
    Write-Host "PROMOTED: $Repo PR #$Pr by '$author' is Ready; the ready_for_review event drives reprocessing." -ForegroundColor Green
    exit 0
  }
  Start-Sleep -Seconds 3
}
throw "PROMOTION-UNVERIFIED: $Repo PR #$Pr still reports draft after 5 polls."
