param(
  [Parameter(Mandatory)][string]$Repo,
  [Parameter(Mandatory)][int]$Pr
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib/review-policy.ps1')
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw 'GitHub CLI (gh) is required.' }
$config = Get-Content (Join-Path $PSScriptRoot '..\policy\github-defaults.json') -Raw | ConvertFrom-Json

$prRaw = & gh pr view $Pr --repo $Repo --json state,isDraft,headRefOid,autoMergeRequest 2>&1
if ($LASTEXITCODE -ne 0) { throw ($prRaw -join "`n") }
$prData = ($prRaw -join "`n") | ConvertFrom-Json
if ($prData.state -ne 'OPEN' -or $prData.isDraft -or -not $prData.autoMergeRequest) { exit 0 }

$head = [string]$prData.headRefOid
$encoded = [uri]::EscapeDataString('AI Review')
$checksRaw = & gh api -H 'Accept: application/vnd.github+json' "repos/$Repo/commits/$head/check-runs?check_name=$encoded" 2>&1
if ($LASTEXITCODE -ne 0) { throw ($checksRaw -join "`n") }
$checks = (($checksRaw -join "`n") | ConvertFrom-Json).check_runs
$latest = @($checks | Where-Object { $_.name -eq 'AI Review' -and $_.app.slug -eq 'github-actions' } | Sort-Object id | Select-Object -Last 1)
if ($latest.Count -gt 0 -and $latest[0].conclusion -eq 'success') { exit 0 }

$disableRaw = & gh pr merge $Pr --repo $Repo --disable-auto 2>&1
if ($LASTEXITCODE -ne 0) { throw "Could not pause auto-merge for $Repo PR #$Pr. $($disableRaw -join ' ')" }

$marker = "<!-- automation:review-pending:$head -->"
$commentsRaw = & gh api --paginate --slurp "repos/$Repo/issues/$Pr/comments?per_page=100" 2>&1
if ($LASTEXITCODE -ne 0) { throw ($commentsRaw -join "`n") }
$pages = ($commentsRaw -join "`n") | ConvertFrom-Json
$comments = @($pages | ForEach-Object { $_ })
$existing = @($comments | Where-Object {
  (Test-TrustedAutomationComment -Comment $_ -OwnerLogin ([string]$config.owner)) -and [string]$_.body -like "*$marker*"
})
if ($existing.Count -eq 0) {
  & gh pr comment $Pr --repo $Repo --body "AUTO-MERGE PAUSED: exact-head machine review is still pending. A later valid review event will re-evaluate policy and re-arm auto-merge automatically.`n`n$marker" | Out-Host
  if ($LASTEXITCODE -ne 0) { throw "Could not record pending-review state for $Repo PR #$Pr." }
}
