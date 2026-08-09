$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

function Assert-True {
  param([string]$Name, $Condition)
  if (-not $Condition) { throw "$Name failed." }
}

foreach ($relative in @(
  '.gitignore',
  'scripts/prune-portfolio.ps1',
  'templates/.gitignore',
  'templates/dependabot.yml'
)) {
  Assert-True "required file $relative" (Test-Path (Join-Path $root $relative))
}

$textExtensions = @('.md','.ps1','.yml','.yaml','.json','.txt')
$conflicts = Get-ChildItem $root -Recurse -File | Where-Object {
  $_.FullName -notmatch '[\\/]\.git[\\/]' -and $textExtensions -contains $_.Extension.ToLowerInvariant()
} | Select-String -Pattern '^(<<<<<<< .+|=======|>>>>>>> .+)$'
if ($conflicts) {
  throw "Raw merge-conflict markers found:`n$($conflicts -join "`n")"
}

$ignore = Get-Content (Join-Path $root 'templates/.gitignore') -Raw
foreach ($entry in @('.worktrees/','.superpowers/')) {
  Assert-True "gitignore contains $entry" ($ignore -match "(?m)^$([regex]::Escape($entry))\s*$")
}

$dependabot = Get-Content (Join-Path $root 'templates/dependabot.yml') -Raw
Assert-True 'Dependabot v2' ($dependabot -match '(?m)^version:\s*2\s*$')
Assert-True 'Dependabot GitHub Actions ecosystem' ($dependabot -match 'package-ecosystem:\s*github-actions')
Assert-True 'Dependabot groups minor updates' ($dependabot -match '(?m)^\s*-\s*minor\s*$')
Assert-True 'Dependabot groups patch updates' ($dependabot -match '(?m)^\s*-\s*patch\s*$')

$agentsLines = @(Get-Content (Join-Path $root 'templates/AGENTS.md')).Count
if ($agentsLines -gt 120) { throw "templates/AGENTS.md exceeded lean 120-line budget: $agentsLines" }

$bootstrap = Get-Content (Join-Path $root 'scripts/bootstrap-repo.ps1') -Raw
Assert-True 'bootstrap manages scratch ignore' ($bootstrap -match 'templates/\.gitignore')
Assert-True 'bootstrap installs Dependabot default' ($bootstrap -match 'templates/dependabot\.yml')

$tokens = $null; $errors = $null
[System.Management.Automation.Language.Parser]::ParseFile((Join-Path $root 'scripts/prune-portfolio.ps1'), [ref]$tokens, [ref]$errors) | Out-Null
if ($errors.Count -gt 0) { throw "prune-portfolio.ps1 parse failed: $($errors[0].Message)" }

Write-Host 'standard-hygiene tests: PASS' -ForegroundColor Green
