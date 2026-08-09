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

# Material PR mutations must wake authority reconciliation immediately.
foreach ($path in @('templates/PR_AUTOMATION.yml','.github/workflows/pr-automation.yml')) {
  Assert-Contains "$path handles PR edited" $path '(?s)pull_request_target:.*?types:\s*\[[^\]]*\bedited\b'
  Assert-Contains "$path handles auto-merge enabled" $path '(?s)pull_request_target:.*?types:\s*\[[^\]]*\bauto_merge_enabled\b'
  Assert-Contains "$path handles auto-merge disabled" $path '(?s)pull_request_target:.*?types:\s*\[[^\]]*\bauto_merge_disabled\b'
  Assert-Contains "$path handles edited formal reviews" $path '(?s)pull_request_review:.*?types:\s*\[[^\]]*\bedited\b'
  Assert-Contains "$path handles inline review lifecycle" $path '(?s)pull_request_review_comment:.*?types:\s*\[[^\]]*created[^\]]*edited[^\]]*deleted'
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
Assert-Contains 'gate-result router records trusted rerun marker' 'scripts/gate-result-router.ps1' 'auto-rerun:gate:'
Assert-Contains 'gate-result router blocks repeat rerun exhaustion' 'scripts/gate-result-router.ps1' 'gate-rerun-exhausted'
Assert-Contains 'gate rerun exhaustion preserves current PR state' 'scripts/gate-result-router.ps1' 'gate-rerun-exhausted.*\$prData'
foreach ($path in @('templates/PR_AUTOMATION.yml','.github/workflows/pr-automation.yml')) {
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

Write-Host 'state-machine exhaustiveness tests: PASS' -ForegroundColor Green
