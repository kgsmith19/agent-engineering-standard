param(
  [Parameter(Mandatory)][string]$Repo,
  [Parameter(Mandatory)][int]$Pr,
  [ValidateSet('auto','codex','copilot')][string]$Provider = 'auto'
)

# Backward-compatible entry point. The process is a machine review, not a
# GitHub human reviewer request. New automation calls request-machine-review.ps1.
& pwsh -NoProfile -File (Join-Path $PSScriptRoot 'request-machine-review.ps1') `
  -Repo $Repo `
  -Pr $Pr `
  -Provider $Provider
exit $LASTEXITCODE
