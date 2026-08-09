$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

function Assert-True {
  param([string]$Name, $Condition)
  if (-not $Condition) { throw "$Name failed." }
}

foreach ($relative in @(
  '.gitignore',
  '.github/workflows/ai-review-reusable.yml',
  '.github/workflows/pr-automation-reusable.yml',
  '.github/workflows/pr-automation.yml',
  'scripts/evaluate-ai-review.ps1',
  'scripts/request-machine-review.ps1',
  'scripts/pr-orchestrator.ps1',
  'scripts/prune-portfolio.ps1',
  'templates/.gitignore',
  'templates/AI_REVIEW.yml',
  'templates/PR_AUTOMATION.yml',
  'templates/dependabot.yml'
)) {
  Assert-True "required file $relative" (Test-Path (Join-Path $root $relative))
}

Assert-True 'standard native CODEOWNERS absent' (-not (Test-Path (Join-Path $root '.github/CODEOWNERS')))
Assert-True 'bootstrap CODEOWNERS template absent' (-not (Test-Path (Join-Path $root 'templates/CODEOWNERS')))

$textExtensions = @('.md','.ps1','.yml','.yaml','.json','.txt')
$conflicts = Get-ChildItem $root -Recurse -File | Where-Object {
  $_.FullName -notmatch '[\\/]\.git[\\/]' -and $textExtensions -contains $_.Extension.ToLowerInvariant()
} | Select-String -Pattern '^(<<<<<<< .+|=======|>>>>>>> .+)$'
if ($conflicts) { throw "Raw merge-conflict markers found:`n$($conflicts -join "`n")" }

$ignore = Get-Content (Join-Path $root 'templates/.gitignore') -Raw
foreach ($entry in @('.worktrees/','.superpowers/')) {
  Assert-True "gitignore contains $entry" ($ignore -match "(?m)^$([regex]::Escape($entry))\s*$")
}

$dependabot = Get-Content (Join-Path $root 'templates/dependabot.yml') -Raw
Assert-True 'Dependabot v2' ($dependabot -match '(?m)^version:\s*2\s*$')
Assert-True 'Dependabot GitHub Actions ecosystem' ($dependabot -match 'package-ecosystem:\s*github-actions')
Assert-True 'Dependabot groups minor updates' ($dependabot -match '(?m)^\s*-\s*minor\s*$')
Assert-True 'Dependabot groups patch updates' ($dependabot -match '(?m)^\s*-\s*patch\s*$')

$ci = Get-Content (Join-Path $root '.github/workflows/ci.yml') -Raw
Assert-True 'standard workflow named PR Gate' ($ci -match '(?m)^name:\s*PR Gate\s*$')
Assert-True 'standard job context named PR Gate' ($ci -match '(?m)^\s+name:\s*PR Gate\s*$')

$aiReusable = Get-Content (Join-Path $root '.github/workflows/ai-review-reusable.yml') -Raw
Assert-True 'AI Review delegates to tested evaluator' ($aiReusable -match 'scripts/evaluate-ai-review\.ps1')
Assert-True 'AI Review does not duplicate provider login map' ($aiReusable -notmatch 'chatgpt-codex-connector|copilot-pull-request-reviewer')

foreach ($templateName in @('AI_REVIEW.yml','PR_AUTOMATION.yml')) {
  $template = Get-Content (Join-Path $root "templates/$templateName") -Raw
  Assert-True "$templateName has exact SHA placeholder" ($template -match '__STANDARD_SHA__')
  Assert-True "$templateName does not follow moving main" ($template -notmatch '@main\b')
}

$bootstrap = Get-Content (Join-Path $root 'scripts/bootstrap-repo.ps1') -Raw
Assert-True 'bootstrap manages scratch ignore' ($bootstrap -match 'templates/\.gitignore')
Assert-True 'bootstrap installs Dependabot default' ($bootstrap -match 'templates/dependabot\.yml')
Assert-True 'bootstrap installs AI Review caller' ($bootstrap -match 'templates/AI_REVIEW\.yml')
Assert-True 'bootstrap installs PR Automation caller' ($bootstrap -match 'templates/PR_AUTOMATION\.yml')
Assert-True 'bootstrap renders exact standard SHA' ($bootstrap -match "Replace\('__STANDARD_SHA__',\$standardSha\)")
Assert-True 'bootstrap does not overwrite PowerShell automatic args variable' ($bootstrap -notmatch '(?m)^\s*\$args\s*=')
Assert-True 'bootstrap removes native CODEOWNERS' ($bootstrap -match "Remove-Item .*\.github/CODEOWNERS")

$agentsLines = @(Get-Content (Join-Path $root 'templates/AGENTS.md')).Count
if ($agentsLines -gt 120) { throw "templates/AGENTS.md exceeded lean 120-line budget: $agentsLines" }

$parseFailures = New-Object System.Collections.Generic.List[string]
foreach ($file in @(Get-ChildItem (Join-Path $root 'scripts') -Recurse -Filter '*.ps1') + @(Get-ChildItem (Join-Path $root 'tests') -Recurse -Filter '*.ps1')) {
  $tokens = $null; $errors = $null
  [System.Management.Automation.Language.Parser]::ParseFile($file.FullName, [ref]$tokens, [ref]$errors) | Out-Null
  foreach ($error in @($errors)) { $parseFailures.Add("$($file.FullName): $($error.Message)") }
}
if ($parseFailures.Count -gt 0) { throw "PowerShell parse failures:`n$($parseFailures -join "`n")" }

Write-Host 'standard-hygiene tests: PASS' -ForegroundColor Green
