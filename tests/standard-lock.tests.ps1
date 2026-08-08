$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $root 'scripts/lib/standard-lock.ps1')

function Assert-Equal {
  param(
    [Parameter(Mandatory)][string]$Name,
    [AllowEmptyString()][string]$Actual,
    [AllowEmptyString()][string]$Expected
  )
  if ($Actual -cne $Expected) {
    throw "$Name failed.`nEXPECTED:`n$Expected`nACTUAL:`n$Actual"
  }
}

function Assert-Throws {
  param(
    [Parameter(Mandatory)][string]$Name,
    [Parameter(Mandatory)][scriptblock]$Action
  )
  $threw = $false
  try { & $Action | Out-Null }
  catch { $threw = $true }
  if (-not $threw) { throw "$Name failed: expected an exception." }
}

$newSha = '1111111111111111111111111111111111111111'
$oldSha = '2222222222222222222222222222222222222222'
$date = '2026-08-08'

$cases = @(
  @{ name = 'commit format'; key = 'commit' },
  @{ name = 'sha format'; key = 'sha' },
  @{ name = 'standard_commit format'; key = 'standard_commit' }
)

foreach ($case in $cases) {
  $input = "header: keep`n$($case.key): $oldSha`npinned_at: `"2026-01-01`"`ntail: keep`n"
  $expected = "header: keep`n$($case.key): $newSha`npinned_at: `"$date`"`ntail: keep`n"
  $actual = Update-StandardLockText -Text $input -StandardSha $newSha -PinnedAt $date
  Assert-Equal -Name $case.name -Actual $actual -Expected $expected
}

$inlineComment = "commit: $oldSha # keep me`npinned_at: old`n"
$expectedInline = "commit: $newSha # keep me`npinned_at: `"$date`"`n"
Assert-Equal -Name 'preserves inline comment and updates date' `
  -Actual (Update-StandardLockText -Text $inlineComment -StandardSha $newSha -PinnedAt $date) `
  -Expected $expectedInline

Assert-Throws -Name 'refuses unknown lock format' -Action {
  Update-StandardLockText -Text "revision: $oldSha`n" -StandardSha $newSha -PinnedAt $date
}

Assert-Throws -Name 'refuses ambiguous lock format' -Action {
  Update-StandardLockText -Text "commit: $oldSha`nsha: $oldSha`n" -StandardSha $newSha -PinnedAt $date
}

Write-Host 'standard-lock tests: PASS' -ForegroundColor Green
