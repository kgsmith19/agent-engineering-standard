$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

function Assert-True { param([string]$Name,$Condition) if (-not $Condition) { throw "$Name failed." } }
function Read-Text { param([string]$Path) Get-Content (Join-Path $root $Path) -Raw }
function Assert-Contains { param([string]$Name,[string]$Path,[string]$Pattern) Assert-True $Name ((Read-Text $Path) -match $Pattern) }
function Assert-NotContains { param([string]$Name,[string]$Path,[string]$Pattern) Assert-True $Name ((Read-Text $Path) -notmatch $Pattern) }

$required = @(
  '.gitignore','docs/AUTONOMOUS-PR-STATE-MACHINE.md',
  '.github/workflows/ai-review-reusable.yml','.github/workflows/pr-automation-reusable.yml','.github/workflows/pr-automation.yml',
  '.github/workflows/pr-automation-gate-result.yml','.github/workflows/pr-automation-review-event.yml','.github/workflows/pr-automation-comment-event.yml','.github/workflows/pr-automation-watchdog.yml',
  'scripts/evaluate-ai-review.ps1','scripts/request-machine-review.ps1','scripts/request-review-repair.ps1','scripts/reconcile-machine-review-threads.ps1','scripts/pr-orchestrator.ps1','scripts/gate-result-router.ps1','scripts/review-metrics.ps1','scripts/lint-pr-creation.ps1','scripts/prune-portfolio.ps1',
  'tests/draft-prevention.tests.ps1','tests/state-machine-exhaustiveness.tests.ps1','tests/unconditional-evaluation.tests.ps1','tests/script-smoke.tests.ps1','tests/gate-result-arming.tests.ps1','tests/automation-entrypoints.tests.ps1','tests/upgrade-repos.tests.ps1',
  'templates/.gitignore','templates/AI_REVIEW.yml','templates/PR_AUTOMATION.yml','templates/dependabot.yml',
  'templates/PR_AUTOMATION_GATE_RESULT.yml','templates/PR_AUTOMATION_REVIEW_EVENT.yml','templates/PR_AUTOMATION_COMMENT_EVENT.yml','templates/PR_AUTOMATION_WATCHDOG.yml'
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
Assert-Contains 'ops bootstrap also triggers on push to main' '.github/workflows/ops-portfolio-bootstrap.yml' '(?s)push:\s*\n\s*branches:\s*\[main\]'
Assert-Contains 'ops bootstrap requires the automation identity' '.github/workflows/ops-portfolio-bootstrap.yml' 'AUTOMATION-IDENTITY-MISSING'
Assert-Contains 'ops bootstrap uses the automation token' '.github/workflows/ops-portfolio-bootstrap.yml' 'secrets\.AUTOMATION_TOKEN'
Assert-Contains 'ops bootstrap pins its checkout action' '.github/workflows/ops-portfolio-bootstrap.yml' 'actions/checkout@11d5960a326750d5838078e36cf38b85af677262'
Assert-Contains 'ops bootstrap runs setup then remote doctor' '.github/workflows/ops-portfolio-bootstrap.yml' '(?s)setup-portfolio\.ps1.*doctor\.ps1 -Remote'
Assert-Contains 'AI Review delegates to evaluator' '.github/workflows/ai-review-reusable.yml' 'scripts/evaluate-ai-review\.ps1'
Assert-Contains 'AI Review requests bounded repair' '.github/workflows/ai-review-reusable.yml' 'scripts/request-review-repair\.ps1'
Assert-Contains 'AI Review reconciles stale machine threads' '.github/workflows/ai-review-reusable.yml' 'scripts/reconcile-machine-review-threads\.ps1'
Assert-NotContains 'AI reusable does not duplicate provider map' '.github/workflows/ai-review-reusable.yml' 'chatgpt-codex-connector|copilot-pull-request-reviewer'
Assert-Contains 'standard AI Review uses trusted PR base evaluator' '.github/workflows/ai-review.yml' 'github\.event\.pull_request\.base\.sha \|\| github\.sha'
Assert-Contains 'standard AI Review ignores ordinary issue comments' '.github/workflows/ai-review.yml' 'AI-REVIEW PASS'

foreach ($templateName in @('AI_REVIEW.yml','PR_AUTOMATION.yml','PR_AUTOMATION_GATE_RESULT.yml','PR_AUTOMATION_REVIEW_EVENT.yml','PR_AUTOMATION_COMMENT_EVENT.yml','PR_AUTOMATION_WATCHDOG.yml')) {
  Assert-Contains "$templateName has exact SHA placeholder" "templates/$templateName" '__STANDARD_SHA__'
  Assert-NotContains "$templateName does not follow moving main" "templates/$templateName" '@main\b'
}
Assert-Contains 'AI Review reacts to inline evidence' 'templates/AI_REVIEW.yml' 'pull_request_review_comment:'
Assert-Contains 'AI Review can post bounded repair' 'templates/AI_REVIEW.yml' 'issues:\s*write'
Assert-NotContains 'AI Review does not run on ordinary pull-request pushes' 'templates/AI_REVIEW.yml' '(?m)^\s*pull_request:'
Assert-Contains 'product AI Review ignores ordinary issue comments' 'templates/AI_REVIEW.yml' 'AI-REVIEW PASS'
# Expected cron updated 2026-08-09 with policy watchdog_interval_minutes 60->360
# per the approved all-13 design: six-hourly reconciliation is the convergence
# net and stays under the 720-minute absolute review timeout. The per-event
# split routes each invariant to the workflow file that now carries it.
Assert-Contains 'watchdog runs six-hourly, before absolute review timeout' 'templates/PR_AUTOMATION_WATCHDOG.yml' 'cron:\s*"17 \*/6 \* \* \*"'
Assert-Contains 'standard watchdog runs six-hourly' '.github/workflows/pr-automation-watchdog.yml' 'cron:\s*"17 \*/6 \* \* \*"'
Assert-Contains 'review_requested cleanup is immediate' 'templates/PR_AUTOMATION.yml' 'review_requested'
Assert-Contains 'gate automation can write AI Review' 'templates/PR_AUTOMATION_GATE_RESULT.yml' '(?s)gate-result:.*?checks:\s*write'
Assert-Contains 'review automation can remove reviewers' 'templates/PR_AUTOMATION_REVIEW_EVENT.yml' '(?s)review-event:.*?pull-requests:\s*write'
Assert-Contains 'PR target lane is contents read only' 'templates/PR_AUTOMATION.yml' '(?s)pr-event:.*?contents:\s*read.*?pull-requests:\s*write'
Assert-Contains 'standard review_requested cleanup is immediate' '.github/workflows/pr-automation.yml' 'review_requested'
Assert-Contains 'standard review orchestration uses trusted base code' '.github/workflows/pr-automation-review-event.yml' 'github\.event\.pull_request\.base\.sha'
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
# Threat-tier contract: the dispatch prompts carry the structured verdict shape
# and the full T4 bar; prose classifications are always advisory.
Assert-Contains 'review request protocol demands structured verdicts' 'scripts/request-machine-review.ps1' 'BLOCK: <CLASS> <file:line>'
Assert-Contains 'review request protocol carries the T4 bar' 'scripts/request-machine-review.ps1' 'T4-CRITICAL-VULN requires ALL of'
Assert-Contains 'review request protocol keeps prose advisory' 'scripts/request-machine-review.ps1' 'always advisory'
Assert-Contains 'repair prompt keys on structured verdicts' 'scripts/request-review-repair.ps1' 'BLOCK: <CLASS> <file:line>'
Assert-Contains 'evaluator quotes matched verdicts on failure' 'scripts/evaluate-ai-review.ps1' 'verdictLines'
Assert-Contains 'evaluator flags severe advisories prominently' 'scripts/evaluate-ai-review.ps1' 'Severe \(P0/P1-classified\)'
Assert-Contains 'evaluator reads every PR commit for independence' 'scripts/evaluate-ai-review.ps1' 'pulls/\$Pr/commits\?per_page=100'
Assert-Contains 'evaluator uses independent providers' 'scripts/evaluate-ai-review.ps1' 'Get-AcceptedMachineReviewProviders'
Assert-Contains 'evaluator authenticates structured Copilot verdict' 'scripts/evaluate-ai-review.ps1' 'Get-TrustedStructuredCopilotReview'
Assert-Contains 'evaluator trusts only authoritative Codex request markers' 'scripts/evaluate-ai-review.ps1' 'Test-TrustedAutomationComment'
Assert-Contains 'evaluator checks inline comments' 'scripts/evaluate-ai-review.ps1' 'inline review comment'
Assert-Contains 'evaluator records P2 follow-up Issues before neutral outcome' 'scripts/evaluate-ai-review.ps1' 'Ensure-AdvisoryIssue'
Assert-Contains 'evaluator updates one open advisory Issue per PR' 'scripts/evaluate-ai-review.ps1' 'gh issue edit'
Assert-Contains 'evaluator searches prior advisory Issues across heads' 'scripts/evaluate-ai-review.ps1' 'Get-TrustedAiReviewAdvisoryIssueNumbers'
# Test repair (2026-08-09): the original double-quoted pattern interpolated
# $headSha to empty (backslash is not an escape in PowerShell strings), leaving
# an unsatisfiable two-space literal. Single quotes preserve the intended regex.
Assert-Contains 'evaluator exposes disabled dispatch with neutral check' 'scripts/evaluate-ai-review.ps1' 'Set-AiReviewCheck \$headSha neutral'
Assert-Contains 'evaluator embeds machine-readable dispatch evidence' 'scripts/evaluate-ai-review.ps1' 'dispatch-evidence repo=\$Repo pr=\$Pr head=\$headSha base=\$baseSha risk=\$evidenceRisk mode='
Assert-Contains 'evaluator scopes evidence to dispatch policy version' 'scripts/evaluate-ai-review.ps1' 'policy_version='
Assert-Contains 'evidence risk derives from PR labels' 'scripts/evaluate-ai-review.ps1' 'Get-RiskFromLabels'
Assert-Contains 'orchestrator re-evaluates stale policy-version evidence' 'scripts/pr-orchestrator.ps1' 'Test-CurrentDispatchEvidence'
Assert-Contains 'auto-merge verifies current dispatch policy version' 'scripts/auto-merge.ps1' 'Test-CurrentDispatchEvidence'
Assert-Contains 'policy-version evidence check is shared from the lib' 'scripts/lib/review-policy.ps1' 'function Test-CurrentDispatchEvidence'
Assert-Contains 'doctor pins dispatch policy version to a positive integer' 'scripts/doctor.ps1' 'dispatch_policy_version'
Assert-Contains 'repair script has bounded review budget' 'scripts/request-review-repair.ps1' 'max_review_fix_attempts'
Assert-Contains 'repair script uses centralized decision' 'scripts/request-review-repair.ps1' 'Get-ReviewRepairDecision'
Assert-Contains 'repair script authenticates structured Copilot verdict' 'scripts/request-review-repair.ps1' 'Get-TrustedStructuredCopilotReview'
Assert-Contains 'repair script launches Copilot on existing PR' 'scripts/request-review-repair.ps1' '@copilot address all material machine-review findings'
Assert-Contains 'repair exhaustion disables auto-merge' 'scripts/request-review-repair.ps1' '--disable-auto'
Assert-Contains 'repair script refuses repair while reviewer dispatch is disabled' 'scripts/request-review-repair.ps1' 'disabled_pending_e2e'

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
Assert-True 'orchestrator authenticates structured Copilot failures' ($orchestrator -match 'Get-TrustedStructuredCopilotReview')
Assert-True 'orchestrator checks exact-head inline blocking evidence' ($orchestrator -match 'pulls/\$Number/comments\?per_page=100')
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
Assert-Contains 'pause lane emits versioned pending marker' 'scripts/pause-pending-review.ps1' 'automation:v1:review-pending:'
Assert-Contains 'pause lane reads legacy pending markers' 'scripts/pause-pending-review.ps1' 'automation:\(\?:v\\d\+:\)\?review-pending:'
Assert-Contains 'router emits versioned rerun markers' 'scripts/gate-result-router.ps1' 'auto-rerun:v1:gate:'
Assert-Contains 'requester emits versioned request markers' 'scripts/request-machine-review.ps1' 'ai-review-request:v1:'
Assert-Contains 'evaluator emits versioned advisory markers' 'scripts/evaluate-ai-review.ps1' 'ai-review-advisory:v1:'
Assert-Contains 'review policy accepts legacy advisory markers' 'scripts/lib/review-policy.ps1' 'ai-review-advisory:\(\?:v\\d\+:\)\?'
$reviewStart = $orchestrator.IndexOf('function Run-ReviewCycle')
$reviewEnd = $orchestrator.IndexOf('function Resolve-GateBlocks')
Assert-True 'review-cycle boundaries found' ($reviewStart -ge 0 -and $reviewEnd -gt $reviewStart)
$reviewCycle = $orchestrator.Substring($reviewStart,$reviewEnd-$reviewStart)
Assert-True 'disabled dispatch does not request a reviewer' ($reviewCycle -match 'disabled_pending_e2e' -and $reviewCycle -match 'Complete-ReviewSuccess')
# Evaluation must precede every solicit_reviews/dispatch_mode gate: the
# evaluator runs unconditionally and those flags gate only what follows.
Assert-True 'evaluation precedes solicitation gating' ($reviewCycle -match "(?s)Invoke-AiReview \`$Number.*?\`$reviewSolicit")
Assert-True 'watchdog evaluates disabled-mode heads' ($orchestrator -match '\$dispatchDisabled\)\{Run-ReviewCycle')
Assert-True 'arming waits for exact-head deterministic gate success' ($orchestrator -match "Get-CheckConclusion \`$head \(\[string\]\`$config.required_status_context\)")
Assert-True 'arming requires existing current-version advisory evidence' ($orchestrator -match "(?s)Get-CheckRun \`$head 'Advisory: AI Review'.*?Test-CurrentDispatchEvidence")
Assert-True 'arming refuses only verdict-carrying failures' ($orchestrator -match "conclusion -eq 'failure' -and \(Test-BlockingAiReviewBody")
Assert-True 'primary clean review immediately completes and re-arms' ($reviewCycle -match "result-eq'success'\)\{Complete-ReviewSuccess")
Assert-True 'orchestrator does not launch review repair' ($orchestrator -notmatch '(?m)^\s*Request-Repair review\b')
# Disabled dispatch gates every outbound agent tag, including the CI/conflict
# repair lanes and the @dependabot rebase path, behind a recoverable block.
Assert-True 'repair lanes honor disabled dispatch' ($orchestrator -match '\$Kind-dispatch-disabled')
Assert-True 'repair dispatch block precedes any agent tag' ($orchestrator -match '(?s)function Request-Repair.*?dispatch-disabled.*?@copilot investigate and fix')
# Block/authority comments carry calm prose plus a machine-actionable next step,
# never an alarm-caps header; disabled mode still avoids @-mentions, and a block
# born from a script failure quotes the underlying error line (RC-I).
Assert-True 'block comments carry per-code advice' ($orchestrator -match 'Next step: \$\(Get-BlockAdvice \$Code\)')
Assert-True 'blocked comments avoid mentions while disabled' ($orchestrator -match "the owner \(\`$\(\`$config.owner\)\)")
Assert-True 'authority comments carry a next step' ($orchestrator -match 'Next step: review the evidence above and decide')
Assert-True 'arming failure quotes the underlying error' ($orchestrator -match 'Underlying error: \$armError')
Assert-True 'review-request failure quotes the underlying error' ($orchestrator -match 'Underlying error: \$requestError')
Assert-True 'orchestrator dropped alarm-caps block headers' ($orchestrator -notmatch 'AUTOMATION-BLOCKED')
Assert-Contains 'gate blocks carry per-code advice' 'scripts/gate-result-router.ps1' 'Next step: \$\(Get-GateBlockAdvice \$Code\)'
Assert-NotContains 'router dropped alarm-caps block headers' 'scripts/gate-result-router.ps1' 'AUTOMATION-BLOCKED'
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
Assert-Contains 'auto-merge requires exact-head PR Gate success' 'scripts/auto-merge.ps1' "no exact-head 'PR Gate' success"
Assert-Contains 'auto-merge requires existing advisory evaluation' 'scripts/auto-merge.ps1' "no exact-head 'Advisory: AI Review' evaluation exists"
Assert-Contains 'auto-merge refuses only verdict-carrying failures' 'scripts/auto-merge.ps1' "conclusion -eq 'failure' -and \(Test-BlockingAiReviewBody"
Assert-Contains 'auto-merge refetches the PR immediately before arming' 'scripts/auto-merge.ps1' 'head moved from'
Assert-Contains 'auto-merge pre-arm retry is bounded' 'scripts/auto-merge.ps1' '\$attempt -le 3'
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
Assert-Contains 'upgrade derives each live default branch' 'scripts/upgrade-repos.ps1' 'default_branch'
Assert-Contains 'upgrade targets the derived default branch' 'scripts/upgrade-repos.ps1' '--base \$defaultBranch'
Assert-NotContains 'upgrade never hardcodes a main base' 'scripts/upgrade-repos.ps1' '--base main'
Assert-Contains 'upgrade fails closed when any repository fails' 'scripts/upgrade-repos.ps1' 'ROLLOUT FAILED'
Assert-Contains 'doctor pins repositories to the approved design note' 'scripts/doctor.ps1' 'all-13-github-automation-design'
Assert-Contains 'upgrade removes native CODEOWNERS' 'scripts/upgrade-repos.ps1' "Remove-Item '.github/CODEOWNERS'"
Assert-Contains 'upgrade normalizes gate workflow name to taxonomy' 'scripts/upgrade-repos.ps1' 'name: "Gate: Deterministic CI"'
Assert-Contains 'upgrade normalizes legacy ci and PR Gate names' 'scripts/upgrade-repos.ps1' '\(\?im\)\^name:\\s\*\(ci\|PR Gate\)'
Assert-Contains 'upgrade labels rollout R2' 'scripts/upgrade-repos.ps1' "--add-label 'risk:R2'"
Assert-Contains 'upgrade reuses existing rollout PR' 'scripts/upgrade-repos.ps1' 'existing rollout PR'
Assert-Contains 'setup portfolio invokes upgrade-repos' 'scripts/setup-portfolio.ps1' 'upgrade-repos\.ps1'

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
Assert-Contains 'delivery guide documents the structured threat threshold' 'DELIVERY_GITHUB.md' 'BLOCK: <CLASS>'

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
