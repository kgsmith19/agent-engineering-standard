$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot

foreach ($cmd in @('gh','git','pwsh')) {
  if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { throw "$cmd is required." }
}

& gh auth status | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Authenticate first with: gh auth login' }

Write-Host "`n1/3 Applying repository settings, Actions, labels, and branch rules..." -ForegroundColor Cyan
& pwsh -NoProfile -File (Join-Path $here 'apply-github-standard.ps1')
if ($LASTEXITCODE -ne 0) { throw 'GitHub standard application failed.' }

Write-Host "`n2/3 Pinning the standard content SHA and regenerating thin-caller workflows..." -ForegroundColor Cyan
& pwsh -NoProfile -File (Join-Path $here 'upgrade-repos.ps1')
if ($LASTEXITCODE -ne 0) { throw 'Standard content propagation failed.' }

Write-Host "`n3/3 Verifying effective remote state..." -ForegroundColor Cyan
& pwsh -NoProfile -File (Join-Path $here 'doctor.ps1') -Remote
if ($LASTEXITCODE -ne 0) { throw 'Remote doctor found configuration drift. Fix the reported item, then rerun this script.' }

Write-Host "`nPORTFOLIO CONTROL PLANE: READY" -ForegroundColor Green
