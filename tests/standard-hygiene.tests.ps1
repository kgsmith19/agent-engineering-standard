$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

function Assert-True { param([string]$Name,$Condition) if (-not $Condition) { throw "$Name failed." } }
function Read-Text { param([string]$Path) Get-Content (Join-Path $root $Path) -Raw }
function Assert-Contains { param([string]$Name,[string]$Path,[string]$Pattern) Assert-True $Name ((Read-Text $Path) -match $Pattern) }
function Assert-NotContains { param([string]$Name,[string]$Path,[string]$Pattern) Assert-True $Name ((Read-Text $Path) -notmatch $Pattern) }

$required = @(
  '.gitignore','docs/AUTONOMOUS-PR-STATE-MACHINE.md',
  '.github/workflows/ai-review-reusable.yml','.github/workflows/pr-automation-reusable.yml','.github/workflows/pr-automation.yml',
  'scripts/evaluate-ai-review.ps1','scripts/request-machine-review.ps1','scripts/request-review-repair.ps1','scripts/reconcile-machine-review-threads.ps1','scripts/pr-orchestrator.ps1','scripts/gate-result-router.ps1','scripts/review-metrics.ps1','scripts/lint-pr-creation.ps1','scripts/prune-portfolio.ps1',
  'tests/draft-prevention.tests.ps1','tests/state-machine-exhaustiveness.tests.ps1',
  'templates/.gitignore','templates/AI_REVIEW.yml','templates/PR_AUTOMATION.yml','templates/dependabot.yml'
)
foreach ($relative in $required) { Assert-True "required file $relative" (Test-Path (Join-Path $root $relative)) }
Assert-True 'standard native CODEOWNERS absent' (-not (Test-Path (Join-Path $root '.github/CODEOWNERS')))
Assert-True 'bootstrap CODEOWNERS template absent' (-not (Test-Path (Join-Path $root 'templates/CODEOWNERS')))

$textExtensions = @('.md','.ps1','.yml','.yaml','.json','.txt')
$conflicts = Get-ChildItem $root -Recurse -File | Where-Object { $_.FullName -notmatch '[\\/]\.git[\\/]' -and $textExtensions -contains $_.Extension.ToLowerInvariant() } | Select-String -Pattern '^(<<<<<<< .+|=======|>>>>>>> .+)$'
if ($conflicts) { throw "Raw merge-conflict markers found:`n$($conflicts -join "`n")" }

$ignore = Read-Text 'templates/.gitignore'
foreach ($entry in @('.worktrees/','.superpowers/')) { Assert-True "gitignore contains $entry" ($ignore -match "(?m)^$([regex]::Escape($entry))\s*$") }
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
# Expected cron updated 2026-08-09 with policy watchdog_interval_minutes 360->60:
# the invariant is unchanged (template cron matches the policy interval and stays
# under the absolute review timeout); only the pinned cadence moved to hourly.
Assert-Contains 'watchdog runs hourly, before absolute review timeout' 'templates/PR_AUTOMATION.yml' 'cron:\s*"17 \* \* \* \*"'
Assert-Contains 'review_requested cleanup is immediate' 'templates/PR_AUTOMATION.yml' 'review_requested'
Assert-Contains 'gate automation can write AI Review' 'templates/PR_AUTOMATION.yml' '(?s)gate-result:.*?checks:\s*write'
Assert-Contains 'review automation can remove reviewers' 'templates/PR_AUTOMATION.yml' '(?s)review-event:.*?pull-requests:\s*write'
Assert-Contains 'PR target lane is contents read only' 'templates/PR_AUTOMATION.yml' '(?s)pr-event:.*?contents:\s*read.*?pull-requests:\s*write'
Assert-Contains 'standard review_requested cleanup is immediate' '.github/workflows/pr-automation.yml' 'review_requested'
Assert-Contains 'standard review orchestration uses trusted base code' '.github/workflows/pr-automation.yml' 'github\.event\.pull_request\.base\.sha'
Assert-Contains 'AI Review handles missing trusted evaluator without proposed-code execution' '.github/workflows/ai-review-reusable.yml' 'Trusted evaluator unavailable'
Assert-Contains 'PR Automation handles missing trusted orchestrator without proposed-code execution' '.github/workflows/pr-automation-reusable.yml' 'Trusted orchestrator unavailable'

Assert-Contains 'review policy derives latest-head implementer' 'scripts/lib/review-policy.ps1' 'Get-HeadImplementerProvider'
Assert-Contains 'automation markers require trusted authors' 'scripts/lib/review-policy.ps1' 'Test-TrustedAutomationComment'
Assert-Contains 'structured Copilot verdict requires trusted request' 'scripts/lib/review-policy.ps1' 'Get-TrustedStructuredCopilotReview'
Assert-Contains 'review policy returns independent providers' 'scripts/lib/review-policy.ps1' 'Get-AcceptedMachineReviewProviders'
Assert-Contains 'review policy centralizes repair decision' 'scripts/lib/review-policy.ps1' 'Get-ReviewRepairDecision'
Assert-Contains 'review policy distinguishes blocking findings' 'scripts/lib/review-policy.ps1' 'Test-BlockingAiReviewBody'
Assert-Contains 'review policy distinguishes P2 advisory findings' 'scripts/lib/review-policy.ps1' 'Test-AdvisoryAiReviewBody'
Assert-Contains 'review policy recognizes passing neutral checks' 'scripts/lib/review-policy.ps1' 'Test-AiReviewPassingConclusion'
Assert-Contains 'review policy authenticates advisory Issue mapping' 'scripts/lib/review-policy.ps1' 'Get-TrustedAiReviewAdvisoryIssueNumber'
# Assertion updated with #44's reviewer-independence redesign: the requester and
# evaluator derive machine actors from ALL PR commits (pulls/{pr}/commits), not a
# single head-commit read; the old repos/{repo}/commits/{head} contract is gone.
Assert-Contains 'review request reads every PR commit for independence' 'scripts/request-machine-review.ps1' 'pulls/\$Pr/commits\?per_page=100'
Assert-Contains 'review requester authenticates structured Copilot verdict' 'scripts/request-machine-review.ps1' 'Get-TrustedStructuredCopilotReview'
Assert-Contains 'fallback must be independent' 'scripts/request-machine-review.ps1' "acceptedProviders -contains 'copilot'"
Assert-Contains 'review request blocks inline reviewer-shopping' 'scripts/request-machine-review.ps1' 'pulls/\$Pr/comments\?per_page=100'
Assert-Contains 'review request honors disabled-dispatch canary' 'scripts/request-machine-review.ps1' 'disabled_pending_e2e'
Assert-Contains 'review request protocol makes P2 advisory' 'scripts/request-machine-review.ps1' 'P2-only'
Assert-Contains 'evaluator reads every PR commit for independence' 'scripts/evaluate-ai-review.ps1' 'pulls/\$Pr/commits\?per_page=100'
Assert-Contains 'evaluator uses independent providers' 'scripts/evaluate-ai-review.ps1' 'Get-AcceptedMachineReviewProviders'
Assert-Contains 'evaluator authenticates structured Copilot verdict' 'scripts/evaluate-ai-review.ps1' 'Get-TrustedStructuredCopilotReview'
Assert-Contains 'evaluator trusts only authoritative Codex request markers' 'scripts/evaluate-ai-review.ps1' 'Test-TrustedAutomationComment'
Assert-Contains 'evaluator checks inline comments' 'scripts/evaluate-ai-review.ps1' 'inline review comment'
Assert-Contains 'evaluator records P2 follow-up Issues before neutral outcome' 'scripts/evaluate-ai-review.ps1' 'Ensure-AdvisoryIssue'
# Test repair (2026-08-09): the original double-quoted pattern interpolated
# $headSha to empty (backslash is not an escape in PowerShell strings), leaving
# an unsatisfiable two-space literal. Single quotes preserve the intended regex.
Assert-Contains 'evaluator exposes disabled dispatch with neutral check' 'scripts/evaluate-ai-review.ps1' 'Set-AiReviewCheck \$headSha neutral'
Assert-Contains 'repair script has bounded review budget' 'scripts/request-review-repair.ps1' 'max_review_fix_attempts'
Assert-Contains 'repair script uses centralized decision' 'scripts/request-review-repair.ps1' 'Get-ReviewRepairDecision'
Assert-Contains 'repair script authenticates structured Copilot verdict' 'scripts/request-review-repair.ps1' 'Get-TrustedStructuredCopilotReview'
Assert-Contains 'repair script launches Copilot on existing PR' 'scripts/request-review-repair.ps1' '@copilot address all material machine-review findings'
Assert-Contains 'repair exhaustion disables auto-merge' 'scripts/request-review-repair.ps1' '--disable-auto'
Assert-Contains 'repair script refuses repair while reviewer dispatch is disabled' 'scripts/request-review-repair.ps1' 'disabled_pending_e2e'

$orchestrator = Read-Text 'scripts/pr-orchestrator.ps1'
Assert-True 'orchestrator removes forbidden reviewers' ($orchestrator -match 'requested_reviewers' -and $orchestrator -match 'forbidden_requested_reviewers')
Assert-True 'orchestrator blocks Copilot-owned PRs' ($orchestrator -match 'copilot-owned-pr')
Assert-True 'orchestrator uses Copilot only to repair existing PR' ($orchestrator -match '@copilot investigate and fix')
Assert-True 'orchestrator authenticates structured Copilot failures' ($orchestrator -match 'Get-TrustedStructuredCopilotReview')
Assert-True 'orchestrator checks exact-head inline blocking evidence' ($orchestrator -match 'pulls/\$Number/comments\?per_page=100')
Assert-True 'blocked state disables auto-merge' ($orchestrator -match '(?s)function Set-Blocked.*?Disable-AutoMerge')
Assert-True 'automation blocks have recovery markers' ($orchestrator -match 'automation:resolve:')
$reviewStart = $orchestrator.IndexOf('function Run-ReviewCycle')
$reviewEnd = $orchestrator.IndexOf('function Resolve-GateBlocks')
Assert-True 'review-cycle boundaries found' ($reviewStart -ge 0 -and $reviewEnd -gt $reviewStart)
$reviewCycle = $orchestrator.Substring($reviewStart,$reviewEnd-$reviewStart)
Assert-True 'disabled dispatch does not request a reviewer' ($reviewCycle -match 'disabled_pending_e2e' -and $reviewCycle -match 'Complete-ReviewSuccess')
Assert-True 'primary clean review immediately completes and re-arms' ($reviewCycle -match "result-eq'success'\)\{Complete-ReviewSuccess")
Assert-True 'orchestrator does not launch review repair' ($orchestrator -notmatch '(?m)^\s*Request-Repair review\b')
Assert-True 'orchestrator recognizes neutral AI Review as passing' ($orchestrator -match 'Test-AiReviewPassingConclusion')
foreach ($field in @('max_ci_fix_attempts','max_review_fix_attempts','max_conflict_fix_attempts')) { Assert-True "orchestrator uses $field" ($orchestrator -match $field) }

Assert-Contains 'thread reconciliation requires a passing AI Review conclusion' 'scripts/reconcile-machine-review-threads.ps1' 'Test-AiReviewPassingConclusion'
Assert-Contains 'current-head threads are preserved' 'scripts/reconcile-machine-review-threads.ps1' 'currentHead'
Assert-Contains 'human-involved threads are preserved' 'scripts/reconcile-machine-review-threads.ps1' 'nonMachine'
Assert-Contains 'P2-only machine threads are safely resolved' 'scripts/reconcile-machine-review-threads.ps1' 'Test-AdvisoryOnlyAiReviewBody'
Assert-Contains 'thread reconciliation keeps truncated conversations' 'scripts/reconcile-machine-review-threads.ps1' 'hasNextPage'

Assert-Contains 'ruleset dismisses stale reviews' 'scripts/apply-github-standard.ps1' 'dismiss_stale_reviews_on_push=\$true'
Assert-Contains 'ruleset requires zero approvals' 'scripts/apply-github-standard.ps1' 'required_approving_review_count=0'
Assert-Contains 'setup checks effective default-branch rulesets' 'scripts/apply-github-standard.ps1' 'rules/branches/\$\{?defaultBranchEncoded\}?'
Assert-Contains 'setup rejects conflicting default-branch rulesets' 'scripts/apply-github-standard.ps1' 'conflicting active default-branch ruleset'
Assert-Contains 'doctor checks effective default-branch rulesets' 'scripts/doctor.ps1' 'rules/branches/\$\{?defaultBranchEncoded\}?'
Assert-Contains 'doctor detects conflicting default-branch rulesets' 'scripts/doctor.ps1' 'conflicting active default-branch ruleset'
Assert-Contains 'auto-merge checks effective default-branch rulesets' 'scripts/auto-merge.ps1' 'rules/branches/\$\{?defaultBranchEncoded\}?'
Assert-Contains 'auto-merge rejects conflicting default-branch rulesets' 'scripts/auto-merge.ps1' 'Auto-merge refused: conflicting active default-branch ruleset'
Assert-Contains 'ruleset authority checks paginate' 'scripts/auto-merge.ps1' 'rules/branches/\$\{defaultBranchEncoded\}\?per_page=100'
Assert-Contains 'setup authority check paginates' 'scripts/apply-github-standard.ps1' 'rules/branches/\$\{defaultBranchEncoded\}\?per_page=100'
Assert-Contains 'doctor authority check paginates' 'scripts/doctor.ps1' 'rules/branches/\$\{defaultBranchEncoded\}\?per_page=100'
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
Assert-Contains 'doctor validates every reusable workflow ref pin' 'scripts/doctor.ps1' '\$usesRefs'
Assert-Contains 'doctor validates reusable workflow ref pin' 'scripts/doctor.ps1' 'reusable-workflow ref not pinned to standard.lock'
Assert-Contains 'doctor validates standard_sha input pin' 'scripts/doctor.ps1' 'standard_sha input not pinned to standard.lock'
Assert-Contains 'doctor checks legacy protection absence' 'scripts/doctor.ps1' 'legacy branch protection still present'
Assert-Contains 'doctor checks review dispatch canary' 'scripts/doctor.ps1' 'dispatch_mode'
Assert-Contains 'doctor verifies no-dispatch auto-merge ceiling' 'scripts/doctor.ps1' 'auto_merge_max_risk'
Assert-Contains 'doctor requires state map' 'scripts/doctor.ps1' 'AUTONOMOUS-PR-STATE-MACHINE\.md'

Assert-NotContains 'portfolio policy does not retain GitHub Project title' 'policy/github-defaults.json' 'project_title'
Assert-NotContains 'portfolio setup does not invoke GitHub Project sync' 'scripts/setup-portfolio.ps1' 'sync-agentic-project'
Assert-NotContains 'portfolio setup has no GitHub Project skip switch' 'scripts/setup-portfolio.ps1' 'SkipProject'
Assert-True 'obsolete GitHub Project sync script is removed' (-not (Test-Path (Join-Path $root 'scripts/sync-agentic-project.ps1')))
Assert-NotContains 'agent guidance does not advertise GitHub Project sync' 'AGENTS.md' 'sync-agentic-project'

Assert-Contains 'agent rules explain P2 Issue-only follow-up' 'AGENT_RULES.md' 'P2.*Issue'
Assert-Contains 'template guidance keeps reviewer dispatch disabled pending E2E' 'templates/AGENTS.md' 'disabled_pending_e2e'
Assert-Contains 'state machine documents neutral canary outcome' 'docs/AUTONOMOUS-PR-STATE-MACHINE.md' 'neutral'
Assert-Contains 'delivery guide documents P0/P1 blocking threshold' 'DELIVERY_GITHUB.md' 'P0/P1'

$agentsLines = @(Get-Content (Join-Path $root 'templates/AGENTS.md')).Count
if ($agentsLines -gt 120) { throw "templates/AGENTS.md exceeded lean 120-line budget: $agentsLines" }

$parseFailures = New-Object System.Collections.Generic.List[string]
foreach ($file in @(Get-ChildItem (Join-Path $root 'scripts') -Recurse -Filter '*.ps1') + @(Get-ChildItem (Join-Path $root 'tests') -Recurse -Filter '*.ps1')) {
  $tokens=$null;$errors=$null
  [System.Management.Automation.Language.Parser]::ParseFile($file.FullName,[ref]$tokens,[ref]$errors)|Out-Null
  foreach($error in @($errors)){$parseFailures.Add("$($file.FullName): $($error.Message)")}
}
if($parseFailures.Count-gt 0){throw"PowerShell parse failures:`n$($parseFailures -join "`n")"}
Write-Host 'standard-hygiene tests: PASS' -ForegroundColor Green
