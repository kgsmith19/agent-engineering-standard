$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

function Assert-True { param([string]$Name,$Condition) if (-not $Condition) { throw "$Name failed." } }
function Read-Text { param([string]$Path) Get-Content (Join-Path $root $Path) -Raw }
function Assert-Contains { param([string]$Name,[string]$Path,[string]$Pattern) Assert-True $Name ((Read-Text $Path) -match $Pattern) }
function Assert-NotContains { param([string]$Name,[string]$Path,[string]$Pattern) Assert-True $Name ((Read-Text $Path) -notmatch $Pattern) }

$required = @(
  '.gitignore','docs/AUTONOMOUS-PR-STATE-MACHINE.md',
  '.github/workflows/pr-automation-reusable.yml','.github/workflows/pr-automation.yml',
  '.github/workflows/pr-automation-gate-result.yml','.github/workflows/pr-automation-watchdog.yml',
  'scripts/pr-orchestrator.ps1','scripts/gate-result-router.ps1','scripts/lint-pr-creation.ps1','scripts/prune-portfolio.ps1',
  'tests/draft-prevention.tests.ps1','tests/script-smoke.tests.ps1','tests/gate-result-arming.tests.ps1','tests/automation-entrypoints.tests.ps1',
  'templates/.gitignore','templates/PR_AUTOMATION.yml',
  'templates/PR_AUTOMATION_GATE_RESULT.yml','templates/PR_AUTOMATION_WATCHDOG.yml'
)
foreach ($relative in $required) { Assert-True "required file $relative" (Test-Path (Join-Path $root $relative)) }
Assert-True 'standard native CODEOWNERS absent' (-not (Test-Path (Join-Path $root '.github/CODEOWNERS')))
Assert-True 'bootstrap CODEOWNERS template absent' (-not (Test-Path (Join-Path $root 'templates/CODEOWNERS')))

$retired = @(
  '.github/workflows/ai-review.yml','.github/workflows/ai-review-reusable.yml',
  '.github/workflows/pr-automation-review-event.yml','.github/workflows/pr-automation-comment-event.yml',
  'scripts/evaluate-ai-review.ps1','scripts/request-machine-review.ps1','scripts/request-review-repair.ps1',
  'scripts/reconcile-machine-review-threads.ps1','scripts/pause-pending-review.ps1','scripts/review-metrics.ps1',
  'scripts/request-independent-review.ps1','templates/AI_REVIEW.yml','templates/PR_AUTOMATION_REVIEW_EVENT.yml',
  'templates/PR_AUTOMATION_COMMENT_EVENT.yml','templates/dependabot.yml',
  'tests/unconditional-evaluation.tests.ps1','tests/state-machine-exhaustiveness.tests.ps1'
)
foreach ($relative in $retired) { Assert-True "retired file absent: $relative" (-not (Test-Path (Join-Path $root $relative))) }

$textExtensions = @('.md','.ps1','.yml','.yaml','.json','.txt')
$conflicts = Get-ChildItem $root -Recurse -File | Where-Object { $_.FullName -notmatch '[\\/]\.git[\\/]' -and $textExtensions -contains $_.Extension.ToLowerInvariant() } | Select-String -Pattern '^(<<<<<<< .+|=======|>>>>>>> .+)$'
if ($conflicts) { throw "Raw merge-conflict markers found:`n$($conflicts -join "`n")" }

$ignore = Read-Text 'templates/.gitignore'
foreach ($entry in @('.worktrees/','.superpowers/','.specs/')) { Assert-True "gitignore contains $entry" ($ignore -match "(?m)^$([regex]::Escape($entry))\s*$") }

# Pipeline taxonomy: the deterministic gate carries the new name while the
# fail-closed pr-gate-bridge job keeps the legacy required 'PR Gate' context
# green until the owner flips the ruleset (context-rename runbook).
Assert-Contains 'gate workflow carries taxonomy name' '.github/workflows/ci.yml' '(?m)^name:\s*"Gate: Deterministic CI"\s*$'
Assert-Contains 'gate job carries taxonomy name' '.github/workflows/ci.yml' '(?m)^\s+name:\s*"Gate: Deterministic CI"\s*$'
Assert-Contains 'bridge job keeps legacy PR Gate context' '.github/workflows/ci.yml' '(?m)^\s+name:\s*PR Gate\s*$'
Assert-Contains 'bridge is fail-closed via needs' '.github/workflows/ci.yml' '(?s)pr-gate-bridge:.*?needs:\s*\[gate\]'
Assert-Contains 'policy names the transition target context' 'policy/github-defaults.json' '"required_status_context_next"\s*:\s*"Gate: Deterministic CI"'
Assert-Contains 'gate template carries taxonomy name and bridge' 'templates/PR_GATE.yml' '(?s)^name:\s*"Gate: Deterministic CI".*pr-gate-bridge:'
# Ops lane: manual + weekly portfolio bootstrap that fails closed without the
# dedicated automation identity (it writes live settings and rulesets).
Assert-Contains 'ops bootstrap is dispatchable and scheduled' '.github/workflows/ops-portfolio-bootstrap.yml' '(?s)workflow_dispatch:.*schedule:'
Assert-Contains 'ops bootstrap requires the automation identity' '.github/workflows/ops-portfolio-bootstrap.yml' 'AUTOMATION-IDENTITY-MISSING'
Assert-Contains 'ops bootstrap uses the automation token' '.github/workflows/ops-portfolio-bootstrap.yml' 'secrets\.AUTOMATION_TOKEN'
Assert-Contains 'ops bootstrap pins its checkout action' '.github/workflows/ops-portfolio-bootstrap.yml' 'actions/checkout@11d5960a326750d5838078e36cf38b85af677262'
Assert-Contains 'ops bootstrap runs setup then remote doctor' '.github/workflows/ops-portfolio-bootstrap.yml' '(?s)setup-portfolio\.ps1.*doctor\.ps1 -Remote'

foreach ($templateName in @('PR_AUTOMATION.yml','PR_AUTOMATION_GATE_RESULT.yml','PR_AUTOMATION_WATCHDOG.yml')) {
  Assert-Contains "$templateName has exact SHA placeholder" "templates/$templateName" '__STANDARD_SHA__'
  Assert-NotContains "$templateName does not follow moving main" "templates/$templateName" '@main\b'
}
# Expected cron updated 2026-08-09 with policy watchdog_interval_minutes 60->360
# per the approved all-13 design: six-hourly reconciliation is the general
# missed-webhook/CI-gate convergence net (unrelated to AI Review, removed ADR-0004).
Assert-Contains 'watchdog runs six-hourly' 'templates/PR_AUTOMATION_WATCHDOG.yml' 'cron:\s*"17 \*/6 \* \* \*"'
Assert-Contains 'standard watchdog runs six-hourly' '.github/workflows/pr-automation-watchdog.yml' 'cron:\s*"17 \*/6 \* \* \*"'
Assert-Contains 'review_requested cleanup is immediate' 'templates/PR_AUTOMATION.yml' 'review_requested'
Assert-Contains 'gate automation can write checks' 'templates/PR_AUTOMATION_GATE_RESULT.yml' '(?s)gate-result:.*?checks:\s*write'
Assert-Contains 'PR target lane is contents read only' 'templates/PR_AUTOMATION.yml' '(?s)pr-event:.*?contents:\s*read.*?pull-requests:\s*write'
Assert-Contains 'standard review_requested cleanup is immediate' '.github/workflows/pr-automation.yml' 'review_requested'
Assert-Contains 'PR Automation handles missing trusted orchestrator without proposed-code execution' '.github/workflows/pr-automation-reusable.yml' 'Trusted orchestrator unavailable'

Assert-Contains 'automation markers require trusted authors' 'scripts/lib/review-policy.ps1' 'Test-TrustedAutomationComment'
Assert-Contains 'review policy resolves gate conclusions to decisions' 'scripts/lib/review-policy.ps1' 'Get-GateConclusionDecision'
Assert-Contains 'review policy parses risk labels' 'scripts/lib/review-policy.ps1' 'Get-RiskFromLabels'
Assert-Contains 'review policy identifies control-plane paths' 'scripts/lib/review-policy.ps1' 'Test-ControlPlanePath'
Assert-Contains 'review policy justifies manual gates' 'scripts/lib/review-policy.ps1' 'Assert-ManualGateJustification'

# External-agent drafts are promoted only with the dedicated automation identity;
# owner/steady-state drafts keep the hard ready-at-creation block.
Assert-Contains 'promotion requires the dedicated automation identity' 'scripts/promote-external-draft.ps1' 'PROMOTION-BLOCKED: automation-identity-missing'
Assert-Contains 'promotion uses the GraphQL ready mutation' 'scripts/promote-external-draft.ps1' 'markPullRequestReadyForReview'
Assert-Contains 'promotion refetch loop is bounded' 'scripts/promote-external-draft.ps1' '\$poll -le 5'
Assert-Contains 'promotion never acts for the owner' 'scripts/promote-external-draft.ps1' 'ready-at-creation policy applies unchanged'
Assert-Contains 'orchestrator routes external drafts to promotion' 'scripts/pr-orchestrator.ps1' 'promote-external-draft\.ps1'
Assert-Contains 'orchestrator fails closed without the automation identity' 'scripts/pr-orchestrator.ps1' "'automation-identity-missing'"
Assert-Contains 'external draft promotion is a policy switch' 'policy/github-defaults.json' '"external_draft_promotion"\s*:\s*(true|false)'
Assert-Contains 'doctor types the promotion switch' 'scripts/doctor.ps1' 'external_draft_promotion'
Assert-Contains 'doctor requires the promotion script' 'scripts/doctor.ps1' 'scripts/promote-external-draft\.ps1'

$orchestrator = Read-Text 'scripts/pr-orchestrator.ps1'
Assert-True 'orchestrator removes forbidden reviewers' ($orchestrator -match 'requested_reviewers' -and $orchestrator -match 'forbidden_requested_reviewers')
Assert-True 'orchestrator blocks Copilot-owned PRs' ($orchestrator -match 'copilot-owned-pr')
Assert-True 'orchestrator uses Copilot only to repair existing PR' ($orchestrator -match '@copilot investigate and fix')
Assert-True 'blocked state disables auto-merge' ($orchestrator -match '(?s)function Set-Blocked.*?Disable-AutoMerge')
Assert-True 'automation blocks have recovery markers' ($orchestrator -match 'automation:v1:resolve:')
# Writers emit versioned correlation markers; readers accept both versioned and
# legacy unversioned forms.
Assert-True 'orchestrator emits versioned block markers' ($orchestrator -match 'automation:v1:block:')
Assert-True 'orchestrator reads legacy and versioned block markers' ($orchestrator -match 'automation:\(\?:v\\d\+:\)\?block:')
Assert-True 'orchestrator emits versioned repair markers' ($orchestrator -match 'auto-fix:v1:')
Assert-True 'orchestrator emits versioned reviewer-removal marker' ($orchestrator -match 'automation:v1:removed-reviewers')
Assert-True 'orchestrator reads legacy reviewer-removal markers' ($orchestrator -match 'automation:\(\?:v\\d\+:\)\?removed-reviewers')
Assert-True 'orchestrator emits versioned authority marker' ($orchestrator -match 'authority-required:v1:')
Assert-True 'orchestrator reads legacy authority markers' ($orchestrator -match 'authority-required:\(\?:v\\d\+:\)\?')
Assert-Contains 'router emits versioned rerun markers' 'scripts/gate-result-router.ps1' 'auto-rerun:v1:gate:'
Assert-True 'orchestrator does not launch review repair' ($orchestrator -notmatch '(?m)^\s*Request-Repair review\b')
Assert-True 'orchestrator no longer defines a review cycle' ($orchestrator -notmatch 'Run-ReviewCycle|Invoke-AiReview|Wait-ForReview')
Assert-True 'arming waits for exact-head deterministic gate success' ($orchestrator -match "Get-CheckConclusion \`$head \(\[string\]\`$config.required_status_context\)")
# Disabled repair dispatch gates every outbound agent tag (CI/conflict repair,
# @dependabot rebase) behind a recoverable block — unaffected by AI Review's removal.
Assert-True 'repair lanes honor disabled dispatch' ($orchestrator -match '\$Kind-dispatch-disabled')
Assert-True 'repair dispatch block precedes any agent tag' ($orchestrator -match '(?s)function Request-Repair.*?dispatch-disabled.*?@copilot investigate and fix')
# Block/authority comments carry calm prose plus a machine-actionable next step,
# never an alarm-caps header; disabled mode still avoids @-mentions, and a block
# born from a script failure quotes the underlying error line (RC-I).
Assert-True 'block comments carry per-code advice' ($orchestrator -match 'Next step: \$\(Get-BlockAdvice \$Code\)')
Assert-True 'blocked comments avoid mentions while disabled' ($orchestrator -match "the owner \(\`$\(\`$config.owner\)\)")
Assert-True 'authority comments carry a next step' ($orchestrator -match 'Next step: review the evidence above and decide')
Assert-True 'arming failure quotes the underlying error' ($orchestrator -match 'Underlying error: \$armError')
Assert-True 'orchestrator dropped alarm-caps block headers' ($orchestrator -notmatch 'AUTOMATION-BLOCKED')
Assert-Contains 'gate blocks carry per-code advice' 'scripts/gate-result-router.ps1' 'Next step: \$\(Get-GateBlockAdvice \$Code\)'
Assert-NotContains 'router dropped alarm-caps block headers' 'scripts/gate-result-router.ps1' 'AUTOMATION-BLOCKED'
foreach ($field in @('max_ci_fix_attempts','max_conflict_fix_attempts')) { Assert-True "orchestrator uses $field" ($orchestrator -match $field) }

Assert-Contains 'ruleset dismisses stale reviews' 'scripts/apply-github-standard.ps1' 'dismiss_stale_reviews_on_push=\$true'
Assert-Contains 'ruleset requires zero approvals' 'scripts/apply-github-standard.ps1' 'required_approving_review_count=0'
Assert-Contains 'setup checks effective default-branch rulesets' 'scripts/apply-github-standard.ps1' 'rules/branches/\$\{?defaultBranchEncoded\}?'
Assert-Contains 'setup rejects conflicting default-branch rulesets' 'scripts/apply-github-standard.ps1' 'conflicting active default-branch ruleset'
Assert-Contains 'doctor checks effective default-branch rulesets' 'scripts/doctor.ps1' 'rules/branches/\$\{?defaultBranchEncoded\}?'
Assert-Contains 'doctor detects conflicting default-branch rulesets' 'scripts/doctor.ps1' 'conflicting active default-branch ruleset'
Assert-Contains 'auto-merge checks effective default-branch rulesets' 'scripts/auto-merge.ps1' 'rules/branches/\$\{?defaultBranchEncoded\}?'
Assert-Contains 'auto-merge rejects conflicting default-branch rulesets' 'scripts/auto-merge.ps1' 'Auto-merge refused: conflicting active default-branch ruleset'
Assert-Contains 'ruleset authority checks paginate' 'scripts/auto-merge.ps1' 'rules/branches/\$\{defaultBranchEncoded\}\?per_page=100'
Assert-Contains 'auto-merge requires exact-head PR Gate success' 'scripts/auto-merge.ps1' "no exact-head 'PR Gate' success"
Assert-Contains 'auto-merge refetches the PR immediately before arming' 'scripts/auto-merge.ps1' 'head moved from'
Assert-Contains 'auto-merge pre-arm retry is bounded' 'scripts/auto-merge.ps1' '\$attempt -le 3'
Assert-Contains 'setup authority check paginates' 'scripts/apply-github-standard.ps1' 'rules/branches/\$\{defaultBranchEncoded\}\?per_page=100'
Assert-Contains 'doctor authority check paginates' 'scripts/doctor.ps1' 'rules/branches/\$\{defaultBranchEncoded\}\?per_page=100'
Assert-Contains 'workflow token is read-only' 'scripts/apply-github-standard.ps1' "default_workflow_permissions = 'read'"
Assert-Contains 'workflow cannot approve reviews' 'scripts/apply-github-standard.ps1' 'can_approve_pull_request_reviews = \$false'
Assert-Contains 'legacy branch protection is deleted' 'scripts/apply-github-standard.ps1' 'branches/\$\(\$meta\.default_branch\)/protection'

Assert-NotContains 'bootstrap does not install the retired AI Review workflow' 'scripts/bootstrap-repo.ps1' 'templates/AI_REVIEW\.yml'
Assert-Contains 'bootstrap installs PR Automation' 'scripts/bootstrap-repo.ps1' 'templates/PR_AUTOMATION\.yml'
Assert-Contains 'bootstrap renders exact SHA' 'scripts/bootstrap-repo.ps1' 'Replace\(''__STANDARD_SHA__'',\$standardSha\)'
Assert-NotContains 'bootstrap does not overwrite automatic args' 'scripts/bootstrap-repo.ps1' '(?m)^\s*\$args\s*='
Assert-Contains 'bootstrap removes native CODEOWNERS' 'scripts/bootstrap-repo.ps1' 'Remove-Item .*\.github/CODEOWNERS'
Assert-NotContains 'upgrade does not install the retired AI Review workflow' 'scripts/upgrade-repos.ps1' 'templates/AI_REVIEW\.yml'
Assert-Contains 'upgrade retires previously-provisioned AI Review workflows' 'scripts/upgrade-repos.ps1' '\.github/workflows/ai-review\.yml'
Assert-Contains 'upgrade installs PR Automation' 'scripts/upgrade-repos.ps1' 'templates/PR_AUTOMATION\.yml'
Assert-Contains 'upgrade derives each live default branch' 'scripts/upgrade-repos.ps1' 'default_branch'
Assert-Contains 'upgrade targets the derived default branch' 'scripts/upgrade-repos.ps1' '--base \$defaultBranch'
Assert-NotContains 'upgrade never hardcodes a main base' 'scripts/upgrade-repos.ps1' '--base main'
Assert-Contains 'upgrade fails closed when any repository fails' 'scripts/upgrade-repos.ps1' 'ROLLOUT FAILED'
Assert-Contains 'doctor pins repositories to the approved design note' 'scripts/doctor.ps1' 'all-13-github-automation-design'
Assert-Contains 'upgrade removes native CODEOWNERS' 'scripts/upgrade-repos.ps1' "Remove-Item '.github/CODEOWNERS'"
Assert-Contains 'upgrade normalizes gate workflow name to taxonomy' 'scripts/upgrade-repos.ps1' 'name: "Gate: Deterministic CI"'
Assert-Contains 'upgrade normalizes legacy ci and PR Gate names' 'scripts/upgrade-repos.ps1' '\(\?im\)\^name:\\s\*\(ci\|PR Gate\)'
Assert-Contains 'upgrade labels rollout R3' 'scripts/upgrade-repos.ps1' "--add-label 'risk:R3'"
Assert-Contains 'upgrade reuses existing rollout PR' 'scripts/upgrade-repos.ps1' 'existing rollout PR'

Assert-Contains 'doctor checks Copilot workflow approval' 'scripts/doctor.ps1' 'require_actions_workflow_approval'
Assert-Contains 'doctor checks requested reviewers' 'scripts/doctor.ps1' 'requested_reviewers'
Assert-Contains 'doctor validates every reusable workflow ref pin' 'scripts/doctor.ps1' '\$usesRefs'
Assert-Contains 'doctor validates reusable workflow ref pin' 'scripts/doctor.ps1' 'reusable-workflow ref not pinned to standard.lock'
Assert-Contains 'doctor validates standard_sha input pin' 'scripts/doctor.ps1' 'standard_sha input not pinned to standard.lock'
Assert-Contains 'doctor checks legacy protection absence' 'scripts/doctor.ps1' 'legacy branch protection still present'
Assert-Contains 'doctor verifies no-dispatch auto-merge ceiling' 'scripts/doctor.ps1' 'auto_merge_max_risk'
Assert-Contains 'doctor requires state map' 'scripts/doctor.ps1' 'AUTONOMOUS-PR-STATE-MACHINE\.md'
Assert-Contains 'doctor types repair dispatch switch' 'scripts/doctor.ps1' 'repair_dispatch_enabled'

Assert-NotContains 'portfolio policy does not retain GitHub Project title' 'policy/github-defaults.json' 'project_title'
Assert-NotContains 'portfolio setup does not invoke GitHub Project sync' 'scripts/setup-portfolio.ps1' 'sync-agentic-project'
Assert-NotContains 'portfolio setup has no GitHub Project skip switch' 'scripts/setup-portfolio.ps1' 'SkipProject'
Assert-True 'obsolete GitHub Project sync script is removed' (-not (Test-Path (Join-Path $root 'scripts/sync-agentic-project.ps1')))
Assert-NotContains 'agent guidance does not advertise GitHub Project sync' 'AGENTS.md' 'sync-agentic-project'

$agentsLines = @(Get-Content (Join-Path $root 'templates/AGENTS.md')).Count
if ($agentsLines -gt 120) { throw "templates/AGENTS.md exceeded lean 120-line budget: $agentsLines" }

# PowerShell variable names are case-insensitive and typed params keep their
# constraint: assigning a parsed object to $pr under [int]$Pr crashes the script
# before any logic runs. Forbid reassigning any [int]/[long] param name.
foreach ($scriptFile in Get-ChildItem (Join-Path $root 'scripts') -Recurse -Filter '*.ps1') {
  $scriptText = Get-Content $scriptFile.FullName -Raw
  $numericParams = @([regex]::Matches($scriptText,'(?m)^\s*(?:\[Parameter[^\]]*\])?\[(?:int|long)\]\$(\w+)\s*(?:=\s*\d+\s*)?[,)]?\s*$') | ForEach-Object { $_.Groups[1].Value })
  foreach ($numericParam in $numericParams) {
    if ($scriptText -match "(?im)^\s*\`$$numericParam\s*=(?!=)") {
      throw "typed numeric param `$$numericParam is case-insensitively reassigned in $($scriptFile.Name); rename the local variable."
    }
  }
}

$parseFailures = New-Object System.Collections.Generic.List[string]
foreach ($file in @(Get-ChildItem (Join-Path $root 'scripts') -Recurse -Filter '*.ps1') + @(Get-ChildItem (Join-Path $root 'tests') -Recurse -Filter '*.ps1')) {
  $tokens=$null;$errors=$null
  [System.Management.Automation.Language.Parser]::ParseFile($file.FullName,[ref]$tokens,[ref]$errors)|Out-Null
  foreach($error in @($errors)){$parseFailures.Add("$($file.FullName): $($error.Message)")}
}
if($parseFailures.Count-gt 0){throw"PowerShell parse failures:`n$($parseFailures -join "`n")"}
Write-Host 'standard-hygiene tests: PASS' -ForegroundColor Green
