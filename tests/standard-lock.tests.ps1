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

  try {
    & $Action | Out-Null
  }
  catch {
    return
  }
  throw "$Name failed: expected an exception."
}

$old = '79ba6aaf18651b1c46f0b81368748fe0e4f8813e'
$new = '0123456789abcdef0123456789abcdef01234567'
$date = '2026-08-09'

$shaLock = @"
standard: kgsmith19/agent-engineering-standard
sha: $old
pinned_at: "2026-08-08"
"@
$shaExpected = @"
standard: kgsmith19/agent-engineering-standard
sha: $new
pinned_at: "$date"
"@
Assert-Equal -Name 'updates sha schema' `
  -Actual (Update-StandardLockContent -Content $shaLock -StandardSha $new -PinnedAt $date) `
  -Expected $shaExpected

$commitLock = @"
repo: https://github.com/kgsmith19/agent-engineering-standard
commit: $old
pinned_at: 2026-08-08
"@
$commitExpected = @"
repo: https://github.com/kgsmith19/agent-engineering-standard
commit: $new
pinned_at: "$date"
"@
Assert-Equal -Name 'updates commit schema' `
  -Actual (Update-StandardLockContent -Content $commitLock -StandardSha $new -PinnedAt $date) `
  -Expected $commitExpected

$standardCommitLock = @"
standard_repo: kgsmith19/agent-engineering-standard
standard_commit: $old
pinned_at: 2026-08-08
pinned_by: lean PR Gate conformance
"@
$standardCommitExpected = @"
standard_repo: kgsmith19/agent-engineering-standard
standard_commit: $new
pinned_at: "$date"
pinned_by: lean PR Gate conformance
"@
Assert-Equal -Name 'updates standard_commit schema' `
  -Actual (Update-StandardLockContent -Content $standardCommitLock -StandardSha $new -PinnedAt $date) `
  -Expected $standardCommitExpected

Assert-Throws -Name 'refuses missing revision field' -Action {
  Update-StandardLockContent -Content "revision: $old`npinned_at: 2026-08-08" -StandardSha $new -PinnedAt $date
}

Assert-Throws -Name 'refuses ambiguous revision fields' -Action {
  Update-StandardLockContent -Content "sha: $old`ncommit: $old`npinned_at: 2026-08-08" -StandardSha $new -PinnedAt $date
}

Assert-Throws -Name 'refuses missing pinned_at field' -Action {
  Update-StandardLockContent -Content "commit: $old" -StandardSha $new -PinnedAt $date
}

Assert-Throws -Name 'refuses invalid target SHA' -Action {
  Update-StandardLockContent -Content $commitLock -StandardSha 'not-a-sha' -PinnedAt $date
}

Write-Host 'standard-lock tests: PASS' -ForegroundColor Green
