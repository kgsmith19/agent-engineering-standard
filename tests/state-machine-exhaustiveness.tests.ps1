$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $root 'scripts/lib/review-policy.ps1')

function Read-Text { param([string]$Path) Get-Content (Join-Path $root $Path) -Raw }
function Assert-Contains {
  param([string]$Name,[string]$Path,[string]$Pattern)
  if ((Read-Text $Path) -notmatch $Pattern) { throw "$Name failed." }
}
function Assert-Equal {
  param([string]$Name,$Actual,$Expected)
  if ($Actual -cne $Expected) { throw "$Name failed: expected '$Expected', got '$Actual'." }
}

# Material PR mutations must wake authority reconciliation immediately. The
# per-event split routes each trigger family to its own workflow file.
foreach ($path in @('templates/PR_AUTOMATION.yml','.github/workflows/pr-automation.yml')) {
  Assert-Contains "$path handles PR edited" $path '(?s)pull_request_target:.*?types:\s*\[[^\]]*\bedited\b'
  Assert-Contains "$path handles auto-merge enabled" $path '(?s)pull_request_target:.*?types:\s*\[[^\]]*\bauto_merge_enabled\b'
  Assert-Contains "$path handles auto-merge disabled" $path '(?s)pull_request_target:.*?types:\s*\[[^\]]*\bauto_merge_disabled\b'
}
foreach ($path in @('templates/PR_AUTOMATION_REVIEW_EVENT.yml','.github/workflows/pr-automation-review-event.yml')) {
  Assert-Contains "$path handles edited formal reviews" $path '(?s)pull_request_review:.*?types:\s*\[[^\]]*\bedited\b'
  Assert-Contains "$path handles inline review lifecycle" $path '(?s)pull_request_review_comment:.*?types:\s*\[[^\]]*created[^\]]*edited[^\]]*deleted'
}
foreach ($path in @('templates/PR_AUTOMATION_COMMENT_EVENT.yml','.github/workflows/pr-automation-comment-event.yml')) {
  Assert-Contains "$path handles structured comment deletion" $path '(?s)issue_comment:.*?types:\s*\[[^\]]*\bdeleted\b'
}

# Semantic gate must retract stale evidence immediately when review artifacts mutate.
foreach ($path in @('templates/AI_REVIEW.yml','.github/workflows/ai-review.yml')) {
  Assert-Contains "$path handles edited formal reviews" $path '(?s)pull_request_review:.*?types:\s*\[[^\]]*\bedited\b'
  Assert-Contains "$path handles structured comment deletion" $path '(?s)issue_comment:.*?types:\s*\[[^\]]*\bdeleted\b'
}

# PR metadata edits can change the effective base/diff, so deterministic evidence must rerun.
Assert-Contains 'PR Gate template reruns on edited PR metadata' 'templates/PR_GATE.yml' '(?s)pull_request:.*?types:\s*\[[^\]]*\bedited\b'
Assert-Contains 'standard PR Gate reruns on edited PR metadata' '.github/workflows/ci.yml' '(?s)pull_request:\s*\r?\n\s*types:\s*\[[^\]]*\bedited\b'

# Every documented completed workflow conclusion has one explicit authority decision.
$gateCases = @(
  @('success','success'),
  @('failure','repair'),
  @('timed_out','repair'),
  @('startup_failure','repair'),
  @('action_required','block-workflow-approval'),
  @('skipped','block-gate-skipped'),
  @('cancelled','rerun'),
  @('stale','rerun'),
  @('neutral','block-gate-neutral'),
  @('future_unknown_value','block-gate-unknown')
)
foreach ($case in $gateCases) {
  Assert-Equal "gate conclusion $($case[0])" (Get-GateConclusionDecision -Conclusion $case[0]) $case[1]
}

# Cancelled/stale gate recovery is deterministic, bounded, and the only lane with Actions write.
Assert-Contains 'gate-result router exists in reusable workflow' '.github/workflows/pr-automation-reusable.yml' 'gate-result-router\.ps1'
Assert-Contains 'gate-result router reruns one workflow run' 'scripts/gate-result-router.ps1' 'actions/runs/\$GateRunId/rerun'
Assert-Contains 'gate-result router records trusted rerun marker' 'scripts/gate-result-router.ps1' 'auto-rerun:v1:gate:'
Assert-Contains 'gate-result router blocks repeat rerun exhaustion' 'scripts/gate-result-router.ps1' 'gate-rerun-exhausted'
Assert-Contains 'gate rerun exhaustion preserves current PR state' 'scripts/gate-result-router.ps1' 'gate-rerun-exhausted.*\$prData'
foreach ($path in @('templates/PR_AUTOMATION_GATE_RESULT.yml','.github/workflows/pr-automation-gate-result.yml')) {
  Assert-Contains "$path scopes Actions write to gate-result" $path '(?s)gate-result:.*?permissions:.*?actions:\s*write'
}
Assert-Contains 'gate rerun budget is one' 'policy/github-defaults.json' '"max_gate_rerun_attempts"\s*:\s*1'
Assert-Equal 'gate-result router is control-plane code' (Test-ControlPlanePath 'scripts/gate-result-router.ps1') $true

# Reviewer independence applies to every recognized machine actor in the current PR, not only the latest commit.
$actorCases = @(
  @(@(), '', 'codex,copilot'),
  @(@('chatgpt-codex-connector[bot]'), '', 'copilot'),
  @(@('Copilot'), '', 'codex'),
  @(@('chatgpt-codex-connector[bot]','Copilot'), '', ''),
  @(@('chatgpt-codex-connector[bot]','kgsmith19'), '', 'copilot'),
  @(@('Copilot','kgsmith19'), '', 'codex'),
  @(@(), 'Copilot', 'codex'),
  @(@('kgsmith19'), 'Copilot', 'codex'),
  @(@('kgsmith19'), 'chatgpt-codex-connector[bot]', 'copilot'),
  @(@('chatgpt-codex-connector[bot]'), 'Copilot', ''),
  @(@('Copilot'), 'Copilot', 'codex')
)
foreach ($case in $actorCases) {
  $actual = @(Get-AcceptedMachineReviewProvidersForActors -ActorLogins $case[0] -PrAuthorLogin $case[1]) -join ','
  Assert-Equal "reviewer actor set $($case[0] -join '+')" $actual $case[2]
}
Assert-Contains 'evaluator paginates all PR commits for independence' 'scripts/evaluate-ai-review.ps1' 'pulls/\$Pr/commits\?per_page=100'
Assert-Contains 'requester paginates all PR commits for independence' 'scripts/request-machine-review.ps1' 'pulls/\$Pr/commits\?per_page=100'
Assert-Contains 'evaluator uses actor-set reviewer policy' 'scripts/evaluate-ai-review.ps1' 'Get-AcceptedMachineReviewProvidersForActors'
Assert-Contains 'requester uses actor-set reviewer policy' 'scripts/request-machine-review.ps1' 'Get-AcceptedMachineReviewProvidersForActors'

# Evaluator and orchestrator share one repo-wide non-canceling authority lock —
# every per-event automation workflow carries it; the deterministic PR Gate
# keeps its own per-PR concurrency group.
foreach ($path in @(
  '.github/workflows/ai-review.yml','templates/AI_REVIEW.yml',
  '.github/workflows/pr-automation.yml','templates/PR_AUTOMATION.yml',
  '.github/workflows/pr-automation-gate-result.yml','templates/PR_AUTOMATION_GATE_RESULT.yml',
  '.github/workflows/pr-automation-review-event.yml','templates/PR_AUTOMATION_REVIEW_EVENT.yml',
  '.github/workflows/pr-automation-comment-event.yml','templates/PR_AUTOMATION_COMMENT_EVENT.yml',
  '.github/workflows/pr-automation-watchdog.yml','templates/PR_AUTOMATION_WATCHDOG.yml'
)) {
  Assert-Contains "$path uses the shared authority lock" $path '(?s)concurrency:\s*\r?\n\s*group:\s*automation-authority-\$\{\{ github\.repository \}\}\s*\r?\n\s*cancel-in-progress:\s*false'
}
Assert-Contains 'PR Gate keeps its per-PR concurrency group' '.github/workflows/ci.yml' 'group:\s*pr-gate-\$\{\{ github\.event\.pull_request\.number \|\| github\.ref \}\}'

# The gate-result trigger must listen for the exact gate workflow name, or gate
# completions never reach the orchestrator (atomic rename coupling).
foreach ($pair in @(
  @('.github/workflows/ci.yml','.github/workflows/pr-automation-gate-result.yml'),
  @('templates/PR_GATE.yml','templates/PR_AUTOMATION_GATE_RESULT.yml')
)) {
  $gateName = ([regex]::Match((Read-Text $pair[0]),'(?m)^name:\s*"?([^"\r\n]+?)"?\s*$')).Groups[1].Value
  Assert-Contains "$($pair[1]) triggers on the gate workflow name" $pair[1] ('workflows:\s*\["' + [regex]::Escape($gateName) + '"\]')
}
# Orchestrator taxonomy names, local and template.
$orchestratorNames = @(
  @('pr-automation.yml','PR_AUTOMATION.yml','Orchestrator: PR Lifecycle'),
  @('pr-automation-gate-result.yml','PR_AUTOMATION_GATE_RESULT.yml','Orchestrator: Gate Result'),
  @('pr-automation-review-event.yml','PR_AUTOMATION_REVIEW_EVENT.yml','Orchestrator: Review Event'),
  @('pr-automation-comment-event.yml','PR_AUTOMATION_COMMENT_EVENT.yml','Orchestrator: Comment Event'),
  @('pr-automation-watchdog.yml','PR_AUTOMATION_WATCHDOG.yml','Orchestrator: Watchdog')
)
foreach ($entry in $orchestratorNames) {
  Assert-Contains "$($entry[0]) carries taxonomy name" ".github/workflows/$($entry[0])" ('(?m)^name:\s*"' + [regex]::Escape($entry[2]) + '"\s*$')
  Assert-Contains "$($entry[1]) carries taxonomy name" "templates/$($entry[1])" ('(?m)^name:\s*"' + [regex]::Escape($entry[2]) + '"\s*$')
}
Assert-Contains 'advisory workflow carries taxonomy name' '.github/workflows/ai-review.yml' '(?m)^name:\s*"Advisory: AI Review"\s*$'
Assert-Contains 'advisory template carries taxonomy name' 'templates/AI_REVIEW.yml' '(?m)^name:\s*"Advisory: AI Review"\s*$'

# The watchdog must consume every pagination page of open PRs, not a capped list.
Assert-Contains 'watchdog paginates all open PRs' 'scripts/pr-orchestrator.ps1' 'Get-Paged "repos/\$Repo/pulls\?state=open&per_page=100"'

# Fork heads must be refused with a machine-readable denial before any privileged
# mutation, in every entry path that operates on a PR (PROP-005).
foreach ($path in @('scripts/pr-orchestrator.ps1','scripts/gate-result-router.ps1','scripts/evaluate-ai-review.ps1','scripts/request-machine-review.ps1','scripts/request-review-repair.ps1','scripts/reconcile-machine-review-threads.ps1','scripts/promote-external-draft.ps1')) {
  Assert-Contains "$path denies fork PRs" $path 'FORK-DENIED'
}
Assert-Contains 'orchestrator blocks fork PRs machine-readably' 'scripts/pr-orchestrator.ps1' "'fork-pr'"
foreach ($path in @('templates/PR_AUTOMATION.yml','.github/workflows/pr-automation.yml','templates/PR_AUTOMATION_REVIEW_EVENT.yml','.github/workflows/pr-automation-review-event.yml')) {
  Assert-Contains "$path guards jobs against fork payloads" $path 'github\.event\.pull_request == null \|\| github\.event\.pull_request\.head\.repo\.full_name == github\.repository'
}

Write-Host 'state-machine exhaustiveness tests: PASS' -ForegroundColor Green
