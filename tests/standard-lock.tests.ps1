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
Assert-Equal -Name 'reads sha schema revision' `
  -Actual (Get-StandardLockRevision -Content $shaLock) `
  -Expected $old
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
Assert-Equal -Name 'reads commit schema revision' `
  -Actual (Get-StandardLockRevision -Content $commitLock) `
  -Expected $old
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
Assert-Equal -Name 'reads standard_commit schema revision' `
  -Actual (Get-StandardLockRevision -Content $standardCommitLock) `
  -Expected $old
Assert-Equal -Name 'updates standard_commit schema' `
  -Actual (Update-StandardLockContent -Content $standardCommitLock -StandardSha $new -PinnedAt $date) `
  -Expected $standardCommitExpected

$projectStandardSha = @"
project:
  name: app
  standard_sha: $old
other:
  commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
"@
$projectStandardShaExpected = @"
project:
  name: app
  standard_sha: $new
other:
  commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
"@
Assert-Equal -Name 'updates only matching standard_sha project metadata' `
  -Actual (Update-StandardProjectContent -Content $projectStandardSha -PreviousStandardSha $old -StandardSha $new) `
  -Expected $projectStandardShaExpected

$projectNestedSha = @"
standard:
  repo: kgsmith19/agent-engineering-standard
  sha: $old
runtime:
  image_sha: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
"@
$projectNestedShaExpected = @"
standard:
  repo: kgsmith19/agent-engineering-standard
  sha: $new
runtime:
  image_sha: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
"@
Assert-Equal -Name 'updates matching nested sha project metadata' `
  -Actual (Update-StandardProjectContent -Content $projectNestedSha -PreviousStandardSha $old -StandardSha $new) `
  -Expected $projectNestedShaExpected

$projectUnrelated = @"
standard:
  repo: kgsmith19/agent-engineering-standard
other:
  commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
"@
Assert-Equal -Name 'leaves unrelated project commit unchanged' `
  -Actual (Update-StandardProjectContent -Content $projectUnrelated -PreviousStandardSha $old -StandardSha $new) `
  -Expected $projectUnrelated

$existingTracking = @"
project:
  name: app
work_tracking:
  system: github-issues
  labels_present: [future]
"@
$existingTrackingExpected = @"
project:
  name: app
work_tracking:
  system: github-projects
  labels_present: [future]
  project: "Agentic Portfolio"
  backing_record: github-issues
"@
Assert-Equal -Name 'migrates tracking while preserving repo-specific keys' `
  -Actual (Update-ProjectWorkTrackingContent -Content $existingTracking -ProjectTitle 'Agentic Portfolio') `
  -Expected $existingTrackingExpected

$missingTracking = @"
project:
  name: app
"@
$missingTrackingExpected = @"
project:
  name: app

work_tracking:
  system: github-projects
  project: "Agentic Portfolio"
  backing_record: github-issues
"@
Assert-Equal -Name 'adds tracking block when missing' `
  -Actual (Update-ProjectWorkTrackingContent -Content $missingTracking -ProjectTitle 'Agentic Portfolio') `
  -Expected $missingTrackingExpected

Assert-Throws -Name 'refuses missing revision field' -Action {
  Update-StandardLockContent -Content "revision: $old`npinned_at: 2026-08-08" -StandardSha $new -PinnedAt $date
}

Assert-Throws -Name 'refuses ambiguous revision fields' -Action {
  Get-StandardLockRevision -Content "sha: $old`ncommit: $old`npinned_at: 2026-08-08"
}

Assert-Throws -Name 'refuses missing pinned_at field' -Action {
  Update-StandardLockContent -Content "commit: $old" -StandardSha $new -PinnedAt $date
}

Assert-Throws -Name 'refuses invalid target SHA' -Action {
  Update-StandardLockContent -Content $commitLock -StandardSha 'not-a-sha' -PinnedAt $date
}

Assert-Throws -Name 'refuses ambiguous project references' -Action {
  Update-StandardProjectContent -Content "sha: $old`nstandard_sha: $old" -PreviousStandardSha $old -StandardSha $new
}

Assert-Throws -Name 'refuses duplicate work tracking system fields' -Action {
  Update-ProjectWorkTrackingContent -Content "work_tracking:`n  system: github-issues`n  system: github-projects`n" -ProjectTitle 'Agentic Portfolio'
}

Write-Host 'standard-lock tests: PASS' -ForegroundColor Green
