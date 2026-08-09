$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

function Assert-True {
  param([string]$Name,$Condition)
  if (-not $Condition) { throw "$Name failed." }
}
function Read-Text { param([string]$Path) Get-Content (Join-Path $root $Path) -Raw }
function Assert-Contains {
  param([string]$Name,[string]$Path,[string]$Pattern)
  Assert-True $Name ((Read-Text $Path) -match $Pattern)
}
function Assert-NotContains {
  param([string]$Name,[string]$Path,[string]$Pattern)
  Assert-True $Name ((Read-Text $Path) -notmatch $Pattern)
}

$required = @(
  '.gitignore','docs/AUTONOMOUS-PR-STATE-MACHINE.md',
  '.github/workflows/ai-review-reusable.yml','.github/workflows/pr-automation-reusable.yml','.github/workflows/pr-automation.yml',
  'scripts/evaluate-ai-review.ps1','scripts/request-machine-review.ps1','scripts/request-review-repair.ps1','scripts/reconcile-machine-review-threads.ps1','scripts/pr-orchestrator.ps1','scripts/prune-portfolio.ps1',
  'templates/.gitignore','templates/AI_REVIEW.yml','templates/PR_AUTOMATION.yml','templates/dependabot.yml'
)
foreach ($relative in $required) { Assert-True "required file $relative" (Test-Path (Join-Path $root $relative)) }
Assert-True 'standard native CODEOWNERS absent' (-not (Test-Path (Join-Path $root '.github/CODEOWNERS')))
Assert-True 'bootstrap CODEOWNERS template absent' (-not (Test-Path (Join-Path $root 'templates/CODEOWNERS')))

$textExtensions = @('.md','.ps1','.yml','.yaml','.json','.txt')
$conflicts = Get-ChildItem $root -Recurse -File | Where-Object {
  $_.FullName -notmatch '[\\/]\.git[\\/]' -and $textExtensions -contains $_.Extension.ToLowerInvariant()
} | Select-String -Pattern '^(<<<<<<< .+|=======|>>>>>>> .+)$'
if ($conflicts) { throw "Raw merge-conflict markers found:`n$($conflicts -join "`n")" }

$ignore = Read-Text 'templates/.gitignore'
foreach ($entry in @('.worktrees/','.superpowers/')) {
  Assert-True "gitignore contains $entry" ($ignore -match "(?m)^$([regex]::Escape($entry))\s*$")
}
Assert-Contains 'Dependabot v2' 'templates/dependabot.yml' '(?m)^version:\s*2\s*$'
Assert-Contains 'Dependabot GitHub Actions ecosystem' 'templates/dependabot.yml' 'package-ecosystem:\s*github-actions'
Assert-Contains 'Dependabot groups minor updates' 'templates/dependabot.yml' '(?m)^\s*-\s*minor\s*$'
Assert-Contains 'Dependabot groups patch updates' 'templates/dependabot.yml' '(?m)^\s*-\s*patch\s*$'

Assert-Contains 'standard workflow named PR Gate' '.github/workflows/ci.yml' '(?m)^name:\s*PR Gate\s*$'
Assert-Contains 'standard job context named PR Gate' '.github/workflows/ci.yml' '(?m)^\s+name:\s*PR Gate\s*$'
Assert-Contains 'AI Review delegates to evaluator' '.github/workflows/ai-review-reusable.yml' 'scripts/evaluate-ai-review\.ps1'
Assert-Contains 'AI Review requests bounded repair' '.github/workflows/ai-review-reusable.yml' 'scripts/request-review-repair\.ps1'
Assert-Contains 'AI Review reconciles stale machine threads' '.github/workflows/ai-review-reusable.yml' 'scripts/reconcile-machine-review-threads\.ps1'
Assert-NotContains 'AI reusable does not duplicate provider map' '.github/workflows/ai-review-reusable.yml' 'chatgpt-codex-connector|copilot-pull-request-reviewer'
Assert-Contains 'standard AI Review uses trusted PR base evaluator' '.github/workflows/ai-review.yml' 'github\.event\.pull_request\.base\.sha \|\| github\.sha'
Assert-Contains 'standard AI Review ignores ordinary issue comments' '.github/workflows/ai-review.yml' 'AI-REVIEW PASS'

foreach ($templateName in @('AI_REVIEW.yml','PR_AUTOMATION.yml')) {
  Assert-Contains "$templateName has exact SHA placeholder" "templates/$templateName" '__STANDARD_SHA__'
  Assert-NotContains "$templateName does not follow moving main" "templates/$templateName" '@main\b'
}
Assert-Contains 'AI Review reacts to inline evidence' 'templates/AI_REVIEW.yml' 'pull_request_review_comment:'
Assert-Contains 'AI Review can post bounded repair' 'templates/AI_REVIEW.yml' 'issues:\s*write'
Assert-NotContains 'AI Review does not run on ordinary pull-request pushes' 'templates/AI_REVIEW.yml' '(?m)^\s*pull_request:'
Assert-Contains 'product AI Review ignores ordinary issue comments' 'templates/AI_REVIEW.yml' 'AI-REVIEW PASS'
Assert-Contains 'watchdog runs before absolute review timeout' 'templates/PR_AUTOMATION.yml' 'cron:\s*"17 \*/6 \* \* \*"'
Assert-Contains 'review_requested cleanup is immediate' 'templates/PR_AUTOMATION.yml' 'review_requested'
Assert-Contains 'gate automation can write AI Review' 'templates/PR_AUTOMATION.yml' '(?s)gate-result:.*?checks:\s*write'
Assert-Contains 'review automation can remove reviewers' 'templates/PR_AUTOMATION.yml' '(?s)review-event:.*?pull-requests:\s*write'
Assert-Contains 'PR target lane is contents read only' 'templates/PR_AUTOMATION.yml' '(?s)pr-event:.*?contents:\s*read.*?pull-requests:\s*write'
Assert-Contains 'standard review_requested cleanup is immediate' '.github/workflows/pr-automation.yml' 'review_requested'
Assert-Contains 'standard review orchestration uses trusted base code' '.github/workflows/pr-automation.yml' 'github\.event\.pull_request\.base\.sha'

Assert-Contains 'review policy derives latest-head implementer' 'scripts/lib/review-policy.ps1' 'Get-HeadImplementerProvider'
Assert-Contains 'automation markers require trusted authors' 'scripts/lib/review-policy.ps1' 'Test-TrustedAutomationComment'
Assert-Contains 'review policy returns independent providers' 'scripts/lib/review-policy.ps1' 'Get-AcceptedMachineReviewProviders'
Assert-Contains 'review policy centralizes repair decision' 'scripts/lib/review-policy.ps1' 'Get-ReviewRepairDecision'
Assert-Contains 'review request reads current head commit' 'scripts/request-machine-review.ps1' 'repos/\$Repo/commits/\$headSha'
Assert-Contains 'fallback must be independent' 'scripts/request-machine-review.ps1' "acceptedProviders -contains 'copilot'"
Assert-Contains 'review request blocks inline reviewer-shopping' 'scripts/request-machine-review.ps1' 'pulls/\$Pr/comments\?per_page=100'
Assert-Contains 'evaluator reads current head commit' 'scripts/evaluate-ai-review.ps1' 'repos/\$Repo/commits/\$headSha'
Assert-Contains 'evaluator uses independent providers' 'scripts/evaluate-ai-review.ps1' 'Get-AcceptedMachineReviewProviders'
Assert-Contains 'evaluator trusts only authoritative review-request markers' 'scripts/evaluate-ai-review.ps1' 'Test-TrustedAutomationComment'
Assert-Contains 'evaluator checks inline comments' 'scripts/evaluate-ai-review.ps1' 'inline review comment'
Assert-Contains 'repair script has bounded review budget' 'scripts/request-review-repair.ps1' 'max_review_fix_attempts'
Assert-Contains 'repair script uses centralized decision' 'scripts/request-review-repair.ps1' 'Get-ReviewRepairDecision'
Assert-Contains 'repair script launches Copilot on existing PR' 'scripts/request-review-repair.ps1' '@copilot address all material machine-review findings'
Assert-Contains 'repair exhaustion disables auto-merge' 'scripts/request-review-repair.ps1' '--disable-auto'

$orchestrator = Read-Text 'scripts/pr-orchestrator.ps1'
Assert-True 'orchestrator removes forbidden reviewers' ($orchestrator -match 'requested_reviewers' -and $orchestrator -match 'forbidden_requested_reviewers')
Assert-True 'orchestrator blocks Copilot-owned PRs' ($orchestrator -match 'copilot-owned-pr')
Assert-True 'orchestrator uses Copilot only to repair existing PR' ($orchestrator -match '@copilot investigate and fix')
Assert-True 'blocked state disables auto-merge' ($orchestrator -match '(?s)function Set-Blocked.*?Disable-AutoMerge')
Assert-True 'automation blocks have recovery markers' ($orchestrator -match 'automation:resolve:')
$reviewStart = $orchestrator.IndexOf('function Run-ReviewCycle')
$reviewEnd = $orchestrator.IndexOf('function Resolve-GateBlocks')
Assert-True 'review-cycle boundaries found' ($reviewStart -ge 0 -and $reviewEnd -gt $reviewStart)
$reviewCycle = $orchestrator.Substring($reviewStart,$reviewEnd-$reviewStart)
Assert-True 'short review timeout stays recoverable' ($reviewCycle -notmatch "Set-Blocked[^\r\n]*'review-timeout'")
Assert-True 'pending review pauses auto-merge before waiting' ($reviewCycle -match 'pause-pending-review\.ps1')
Assert-True 'orchestrator does not launch review repair' ($orchestrator -notmatch '(?m)^\s*Request-Repair review\b')
Assert-True 'absolute reviewer timeout is enforced by watchdog' ($orchestrator -match 'absolute_timeout_minutes')
foreach ($field in @('max_ci_fix_attempts','max_review_fix_attempts','max_conflict_fix_attempts')) {
  Assert-True "orchestrator uses $field" ($orchestrator -match $field)
}

Assert-Contains 'thread reconciliation requires AI success' 'scripts/reconcile-machine-review-threads.ps1' "conclusion -ne 'success'"
Assert-Contains 'current-head threads are preserved' 'scripts/reconcile-machine-review-threads.ps1' 'currentHead'
Assert-Contains 'human-involved threads are preserved' 'scripts/reconcile-machine-review-threads.ps1' 'nonMachine'

Assert-Contains 'ruleset dismisses stale reviews' 'scripts/apply-github-standard.ps1' 'dismiss_stale_reviews_on_push=\$true'
Assert-Contains 'ruleset requires zero approvals' 'scripts/apply-github-standard.ps1' 'required_approving_review_count=0'
Assert-Contains 'workflow token is read-only' 'scripts/apply-github-standard.ps1' "default_workflow_permissions = 'read'"
Assert-Contains 'workflow cannot approve reviews' 'scripts/apply-github-standard.ps1' 'can_approve_pull_request_reviews = \$false'
Assert-Contains 'legacy branch protection is deleted' 'scripts/apply-github-standard.ps1' 'branches/\$\(\$meta\.default_branch\)/protection'

Assert-Contains 'bootstrap installs AI Review' 'scripts/bootstrap-repo.ps1' 'templates/AI_REVIEW\.yml'
Assert-Contains 'bootstrap installs PR Automation' 'scripts/bootstrap-repo.ps1' 'templates/PR_AUTOMATION\.yml'
Assert-Contains 'bootstrap renders exact SHA' 'scripts/bootstrap-repo.ps1' 'Replace\(''__STANDARD_SHA__'',\$standardSha\)'
Assert-NotContains 'bootstrap does not overwrite automatic args' 'scripts/bootstrap-repo.ps1' '(?m)^\s*\$args\s*='
Assert-Contains 'bootstrap removes native CODEOWNERS' 'scripts/bootstrap-repo.ps1' 'Remove-Item .*\.github/CODEOWNERS'
Assert-Contains 'upgrade installs AI Review' 'scripts/upgrade-repos.ps1' 'templates/AI_REVIEW\.yml'
Assert-Contains 'upgrade installs PR Automation' 'scripts/upgrade-repos.ps1' 'templates/PR_AUTOMATION\.yml'
Assert-Contains 'upgrade removes native CODEOWNERS' 'scripts/upgrade-repos.ps1' "Remove-Item '.github/CODEOWNERS'"
Assert-Contains 'upgrade normalizes PR Gate name' 'scripts/upgrade-repos.ps1' 'name: PR Gate'
Assert-Contains 'upgrade normalizes lowercase ci names' 'scripts/upgrade-repos.ps1' '\(\?im\)\^name:\\s\*ci'
Assert-Contains 'upgrade labels rollout R3' 'scripts/upgrade-repos.ps1' "--add-label 'risk:R3'"
Assert-Contains 'upgrade reuses existing rollout PR' 'scripts/upgrade-repos.ps1' 'existing rollout PR'

Assert-Contains 'doctor checks Copilot workflow approval' 'scripts/doctor.ps1' 'require_actions_workflow_approval'
Assert-Contains 'doctor checks requested reviewers' 'scripts/doctor.ps1' 'requested_reviewers'
Assert-Contains 'doctor checks legacy protection absence' 'scripts/doctor.ps1' 'legacy branch protection still present'
Assert-Contains 'doctor checks absolute review timeout' 'scripts/doctor.ps1' 'absolute_timeout_minutes'
Assert-Contains 'doctor requires state map' 'scripts/doctor.ps1' 'AUTONOMOUS-PR-STATE-MACHINE\.md'

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
