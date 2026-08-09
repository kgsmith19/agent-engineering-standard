$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

function Assert-True {
  param([string]$Name,$Condition)
  if (-not $Condition) { throw "$Name failed." }
}

foreach ($relative in @(
  '.gitignore',
  'docs/AUTONOMOUS-PR-STATE-MACHINE.md',
  '.github/workflows/ai-review-reusable.yml',
  '.github/workflows/pr-automation-reusable.yml',
  '.github/workflows/pr-automation.yml',
  'scripts/evaluate-ai-review.ps1',
  'scripts/request-machine-review.ps1',
  'scripts/reconcile-machine-review-threads.ps1',
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
Assert-True 'AI Review reconciles stale machine threads' ($aiReusable -match 'scripts/reconcile-machine-review-threads\.ps1')
Assert-True 'AI Review does not duplicate provider login map' ($aiReusable -notmatch 'chatgpt-codex-connector|copilot-pull-request-reviewer')

foreach ($templateName in @('AI_REVIEW.yml','PR_AUTOMATION.yml')) {
  $template = Get-Content (Join-Path $root "templates/$templateName") -Raw
  Assert-True "$templateName has exact SHA placeholder" ($template -match '__STANDARD_SHA__')
  Assert-True "$templateName does not follow moving main" ($template -notmatch '@main\b')
}

$aiTemplate = Get-Content (Join-Path $root 'templates/AI_REVIEW.yml') -Raw
Assert-True 'draft AI Review runner is skipped' ($aiTemplate -match 'github\.event\.pull_request\.draft == false')
Assert-True 'AI Review can reconcile threads' ($aiTemplate -match 'pull-requests:\s*write')

$prAutomationWorkflow = Get-Content (Join-Path $root 'templates/PR_AUTOMATION.yml') -Raw
Assert-True 'watchdog is low frequency' ($prAutomationWorkflow -match 'cron:\s*"17 \*/12 \* \* \*"')
Assert-True 'gate automation can write AI Review check' ($prAutomationWorkflow -match '(?s)gate-result:.*?checks:\s*write')
Assert-True 'review automation can remove requested reviewers' ($prAutomationWorkflow -match '(?s)review-event:.*?pull-requests:\s*write')

$reviewPolicy = Get-Content (Join-Path $root 'scripts/lib/review-policy.ps1') -Raw
Assert-True 'review policy derives latest-head implementer' ($reviewPolicy -match 'Get-HeadImplementerProvider')
Assert-True 'review policy returns accepted independent providers' ($reviewPolicy -match 'Get-AcceptedMachineReviewProviders')

$requestReview = Get-Content (Join-Path $root 'scripts/request-machine-review.ps1') -Raw
Assert-True 'review request reads current head commit' ($requestReview -match 'repos/\$Repo/commits/\$headSha')
Assert-True 'fallback must be independent' ($requestReview -match "acceptedProviders -contains 'copilot'")

$evaluator = Get-Content (Join-Path $root 'scripts/evaluate-ai-review.ps1') -Raw
Assert-True 'evaluator reads current head commit' ($evaluator -match 'repos/\$Repo/commits/\$headSha')
Assert-True 'evaluator uses accepted independent providers' ($evaluator -match 'Get-AcceptedMachineReviewProviders')

$orchestrator = Get-Content (Join-Path $root 'scripts/pr-orchestrator.ps1') -Raw
Assert-True 'orchestrator removes forbidden reviewers' ($orchestrator -match 'requested_reviewers' -and $orchestrator -match 'forbidden_requested_reviewers')
Assert-True 'orchestrator blocks Copilot-owned PRs' ($orchestrator -match 'copilot-owned-pr')
Assert-True 'orchestrator uses Copilot only to repair existing PR' ($orchestrator -match '@copilot investigate and fix')
Assert-True 'blocked state disables auto-merge' ($orchestrator -match '(?s)function Set-Blocked.*?Disable-AutoMerge')
Assert-True 'automation blocks have recovery markers' ($orchestrator -match 'automation:resolve:')
Assert-True 'short review timeout stays recoverable' ($orchestrator -match '(?i)short polling window expiring is not a blocker')
Assert-True 'absolute reviewer timeout is enforced by watchdog' ($orchestrator -match 'absolute_timeout_minutes')
Assert-True 'orchestrator has bounded CI repair' ($orchestrator -match 'max_ci_fix_attempts')
Assert-True 'orchestrator has bounded review repair' ($orchestrator -match 'max_review_fix_attempts')
Assert-True 'orchestrator has bounded conflict repair' ($orchestrator -match 'max_conflict_fix_attempts')

$reconciler = Get-Content (Join-Path $root 'scripts/reconcile-machine-review-threads.ps1') -Raw
Assert-True 'thread reconciliation requires AI Review success' ($reconciler -match "conclusion -ne 'success'")
Assert-True 'current-head threads are preserved' ($reconciler -match 'currentHead')
Assert-True 'human-involved threads are preserved' ($reconciler -match 'nonMachine')

$apply = Get-Content (Join-Path $root 'scripts/apply-github-standard.ps1') -Raw
Assert-True 'ruleset dismisses stale reviews' ($apply -match 'dismiss_stale_reviews_on_push=\$true')
Assert-True 'ruleset requires zero approvals' ($apply -match 'required_approving_review_count=0')
Assert-True 'workflow token default is read-only' ($apply -match "default_workflow_permissions = 'read'")
Assert-True 'workflow token cannot approve reviews' ($apply -match 'can_approve_pull_request_reviews = \$false')
Assert-True 'legacy branch protection is deleted' ($apply -match 'branches/\$Repo/branches/|branches/\$\(\$meta\.default_branch\)/protection')

$bootstrap = Get-Content (Join-Path $root 'scripts/bootstrap-repo.ps1') -Raw
Assert-True 'bootstrap manages scratch ignore' ($bootstrap -match 'templates/\.gitignore')
Assert-True 'bootstrap installs Dependabot default' ($bootstrap -match 'templates/dependabot\.yml')
Assert-True 'bootstrap installs AI Review caller' ($bootstrap -match 'templates/AI_REVIEW\.yml')
Assert-True 'bootstrap installs PR Automation caller' ($bootstrap -match 'templates/PR_AUTOMATION\.yml')
Assert-True 'bootstrap renders exact standard SHA' ($bootstrap -match 'Replace\(''__STANDARD_SHA__'',\$standardSha\)')
Assert-True 'bootstrap does not overwrite PowerShell automatic args variable' ($bootstrap -notmatch '(?m)^\s*\$args\s*=')
Assert-True 'bootstrap removes native CODEOWNERS' ($bootstrap -match 'Remove-Item .*\.github/CODEOWNERS')

$upgrade = Get-Content (Join-Path $root 'scripts/upgrade-repos.ps1') -Raw
Assert-True 'upgrade installs AI Review caller' ($upgrade -match 'templates/AI_REVIEW\.yml')
Assert-True 'upgrade installs PR Automation caller' ($upgrade -match 'templates/PR_AUTOMATION\.yml')
Assert-True 'upgrade removes native CODEOWNERS' ($upgrade -match "Remove-Item '.github/CODEOWNERS'")
Assert-True 'upgrade normalizes PR Gate workflow name' ($upgrade -match 'name: PR Gate')

$doctor = Get-Content (Join-Path $root 'scripts/doctor.ps1') -Raw
Assert-True 'doctor checks Copilot workflow approval' ($doctor -match 'require_actions_workflow_approval')
Assert-True 'doctor checks requested reviewers' ($doctor -match 'requested_reviewers')
Assert-True 'doctor checks legacy protection absence' ($doctor -match 'legacy branch protection still present')
Assert-True 'doctor checks absolute review timeout' ($doctor -match 'absolute_timeout_minutes')
Assert-True 'doctor requires exhaustive state map' ($doctor -match 'AUTONOMOUS-PR-STATE-MACHINE\.md')

$agentsLines = @(Get-Content (Join-Path $root 'templates/AGENTS.md')).Count
if ($agentsLines -gt 120) { throw "templates/AGENTS.md exceeded lean 120-line budget: $agentsLines" }

$parseFailures = New-Object System.Collections.Generic.List[string]
foreach ($file in @(Get-ChildItem (Join-Path $root 'scripts') -Recurse -Filter '*.ps1') + @(Get-ChildItem (Join-Path $root 'tests') -Recurse -Filter '*.ps1')) {
  $tokens = $null; $errors = $null
  [System.Management.Automation.Language.Parser]::ParseFile($file.FullName,[ref]$tokens,[ref]$errors) | Out-Null
  foreach ($error in @($errors)) { $parseFailures.Add("$($file.FullName): $($error.Message)") }
}
if ($parseFailures.Count -gt 0) { throw "PowerShell parse failures:`n$($parseFailures -join "`n")" }

Write-Host 'standard-hygiene tests: PASS' -ForegroundColor Green
