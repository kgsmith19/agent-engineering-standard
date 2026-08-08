param(
  [Parameter(Mandatory)][string]$Repo,
  [Parameter(Mandatory)][int]$Pr,
  [ValidateSet('R0','R1','R2','R3','R4')][string]$Risk = 'R2'
)

$ErrorActionPreference = 'Stop'
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw 'GitHub CLI (gh) is required.' }
& gh auth status | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'gh is not authenticated.' }

$prRaw = & gh pr view $Pr --repo $Repo --json isDraft,state,headRefOid 2>&1
if ($LASTEXITCODE -ne 0) { throw ($prRaw -join "`n") }
$prInfo = ($prRaw -join "`n") | ConvertFrom-Json
if ($prInfo.state -ne 'OPEN') { throw "PR #$Pr is not open." }
if ($prInfo.isDraft) { throw "PR #$Pr is still draft. Finish local verification and mark it ready first." }

$filesRaw = & gh api --paginate "repos/$Repo/pulls/$Pr/files?per_page=100" --jq '.[].filename' 2>&1
if ($LASTEXITCODE -ne 0) { throw ($filesRaw -join "`n") }
$files = @($filesRaw)

$controlPlanePatterns = @(
  '^\.github/workflows/',
  '^\.agent/',
  '^AGENTS\.md$',
  '^policy/',
  '^scripts/(apply-github-standard|doctor|auto-merge|upgrade-repos|bootstrap-repo|codex-review|sync-agentic-project)\.ps1$',
  '^(QUALITY_RULES|SECURITY_RISK_AUTONOMY|DELIVERY_GITHUB)\.md$'
)
$controlPlane = $Repo -match '/agent-engineering-standard$'
foreach ($file in $files) {
  if ($controlPlanePatterns | Where-Object { $file -match $_ }) { $controlPlane = $true; break }
}

$riskNumber = [int]$Risk.Substring(1)
if ($controlPlane -or $riskNumber -ge 3) {
  throw "Auto-merge refused: PR #$Pr is R3/R4 or changes the control plane. Request a fresh external Codex review after the final substantive push, resolve every material review thread, then merge through an independent authority path."
}

& gh pr merge $Pr --repo $Repo --auto --squash
if ($LASTEXITCODE -ne 0) { throw "Could not enable auto-merge for $Repo PR #$Pr." }
Write-Host "AUTO-MERGE ENABLED: $Repo PR #$Pr ($Risk). GitHub will merge only after required checks and review threads pass." -ForegroundColor Green
