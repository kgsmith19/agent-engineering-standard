$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $root 'scripts/lib/review-policy.ps1')

function Assert-Equal {
  param([string]$Name,$Actual,$Expected)
  if ($Actual -cne $Expected) { throw "$Name failed: expected '$Expected', got '$Actual'." }
}
function Assert-Throws {
  param([string]$Name,[scriptblock]$Action)
  try { & $Action | Out-Null } catch { return }
  throw "$Name failed: expected an exception."
}

Assert-Equal 'Codex bot login recognized' (Get-MachineReviewProvider 'chatgpt-codex-connector[bot]') 'codex'
Assert-Equal 'Codex mention login recognized' (Get-MachineReviewProvider 'codex') 'codex'
Assert-Equal 'Copilot review bot recognized' (Get-MachineReviewProvider 'copilot-pull-request-reviewer[bot]') 'copilot'
Assert-Equal 'Copilot coding agent recognized' (Get-MachineReviewProvider 'copilot-swe-agent[bot]') 'copilot'
Assert-Equal 'Unknown reviewer ignored' (Get-MachineReviewProvider 'random-bot[bot]') $null

$actionsComment = [pscustomobject]@{ user = [pscustomobject]@{ login = 'github-actions[bot]' } }
$ownerComment = [pscustomobject]@{ user = [pscustomobject]@{ login = 'kgsmith19' } }
$untrustedComment = [pscustomobject]@{ user = [pscustomobject]@{ login = 'random-user' } }
Assert-Equal 'Actions marker trusted' (Test-TrustedAutomationComment $actionsComment 'kgsmith19') $true
Assert-Equal 'Owner marker trusted' (Test-TrustedAutomationComment $ownerComment 'kgsmith19') $true
Assert-Equal 'Ordinary commenter marker rejected' (Test-TrustedAutomationComment $untrustedComment 'kgsmith19') $false

$head = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
$trustedRequest = [pscustomobject]@{ id=1; user=[pscustomobject]@{login='kgsmith19'}; body="<!-- ai-review-request:copilot:$head -->"; created_at='2026-08-09T10:00:00Z' }
$earlyPass = [pscustomobject]@{ id=2; user=[pscustomobject]@{login='Copilot'}; body="AI-REVIEW PASS — $head"; created_at='2026-08-09T09:59:00Z' }
$validPass = [pscustomobject]@{ id=3; user=[pscustomobject]@{login='Copilot'}; body="AI-REVIEW PASS — $head"; created_at='2026-08-09T10:01:00Z' }
$validFail = [pscustomobject]@{ id=4; user=[pscustomobject]@{login='Copilot'}; body="AI-REVIEW FAIL — $head"; created_at='2026-08-09T10:02:00Z' }
Assert-Equal 'Unsolicited structured Copilot PASS rejected' (Get-TrustedStructuredCopilotReview -Comments @($validPass) -HeadSha $head -OwnerLogin 'kgsmith19') $null
Assert-Equal 'Structured response before trusted request rejected' (Get-TrustedStructuredCopilotReview -Comments @($earlyPass,$trustedRequest) -HeadSha $head -OwnerLogin 'kgsmith19') $null
Assert-Equal 'Latest structured response after trusted request accepted' (Get-TrustedStructuredCopilotReview -Comments @($trustedRequest,$validPass,$validFail) -HeadSha $head -OwnerLogin 'kgsmith19').id 4

# Test repair (2026-08-09): "$head:41" parses as a drive-qualified variable
# (head:41) and interpolates to empty, so the original fixture contained neither
# head nor issue number and the assertion below was unsatisfiable. ${head} keeps
# the declared marker format <!-- ai-review-advisory:<head>:<issue> --> intact.
$trustedAdvisoryMap = [pscustomobject]@{ id=5; user=[pscustomobject]@{login='github-actions[bot]'}; body="<!-- ai-review-advisory:${head}:41 -->"; created_at='2026-08-09T10:03:00Z' }
$forgedAdvisoryMap = [pscustomobject]@{ id=6; user=[pscustomobject]@{login='random-user'}; body="<!-- ai-review-advisory:${head}:99 -->"; created_at='2026-08-09T10:04:00Z' }
$staleAdvisoryMap = [pscustomobject]@{ id=7; user=[pscustomobject]@{login='github-actions[bot]'}; body='<!-- ai-review-advisory:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb:42 -->'; created_at='2026-08-09T10:05:00Z' }
Assert-Equal 'Trusted advisory Issue mapping is accepted' (Get-TrustedAiReviewAdvisoryIssueNumber -Comments @($trustedAdvisoryMap) -HeadSha $head -OwnerLogin 'kgsmith19') 41
Assert-Equal 'Forged advisory Issue mapping is rejected' (Get-TrustedAiReviewAdvisoryIssueNumber -Comments @($forgedAdvisoryMap) -HeadSha $head -OwnerLogin 'kgsmith19') $null
Assert-Equal 'Stale advisory Issue mapping is ignored' (Get-TrustedAiReviewAdvisoryIssueNumber -Comments @($staleAdvisoryMap) -HeadSha $head -OwnerLogin 'kgsmith19') $null

Assert-Equal 'Unknown human head has no machine implementer' (Get-HeadImplementerProvider -HeadAuthorLogin 'kgsmith19') $null
Assert-Equal 'Latest Copilot commit is detected' (Get-HeadImplementerProvider -HeadAuthorLogin 'Copilot') 'copilot'
Assert-Equal 'Latest Codex commit is detected' (Get-HeadImplementerProvider -HeadCommitterLogin 'chatgpt-codex-connector[bot]') 'codex'
Assert-Equal 'Mixed machine head records both actors' (Get-HeadImplementerProvider -HeadAuthorLogin 'chatgpt-codex-connector[bot]' -HeadCommitterLogin 'Copilot') 'codex+copilot'
Assert-Equal 'Machine PR author is recorded despite human commit actors' (Get-HeadImplementerProvider -HeadAuthorLogin 'kgsmith19' -PrAuthorLogin 'Copilot') 'copilot'
Assert-Equal 'Machine PR author is unioned with machine commit actors' (Get-HeadImplementerProvider -HeadAuthorLogin 'chatgpt-codex-connector[bot]' -PrAuthorLogin 'Copilot') 'codex+copilot'

Assert-Equal 'Human or unknown head prefers Codex' (Get-PreferredMachineReviewer -HeadAuthorLogin 'kgsmith19') 'codex'
Assert-Equal 'Copilot-implemented head requires Codex' (Get-PreferredMachineReviewer -HeadAuthorLogin 'Copilot') 'codex'
Assert-Equal 'Codex-implemented head requires Copilot' (Get-PreferredMachineReviewer -HeadAuthorLogin 'chatgpt-codex-connector[bot]') 'copilot'
Assert-Throws 'Mixed Codex and Copilot head has no independent connected reviewer' { Get-PreferredMachineReviewer -HeadAuthorLogin 'chatgpt-codex-connector[bot]' -HeadCommitterLogin 'Copilot' }

$copilotAccepted = @(Get-AcceptedMachineReviewProviders -HeadAuthorLogin 'Copilot')
Assert-Equal 'Copilot head has one accepted reviewer' $copilotAccepted.Count 1
Assert-Equal 'Copilot head accepts Codex only' $copilotAccepted[0] 'codex'
$codexAccepted = @(Get-AcceptedMachineReviewProviders -HeadAuthorLogin 'chatgpt-codex-connector[bot]')
Assert-Equal 'Codex head accepts Copilot only' $codexAccepted[0] 'copilot'
$humanAccepted = @(Get-AcceptedMachineReviewProviders -HeadAuthorLogin 'kgsmith19')
Assert-Equal 'Unknown human head allows bounded fallback' $humanAccepted.Count 2
Assert-Equal 'Unknown human head starts with Codex' $humanAccepted[0] 'codex'
Assert-Equal 'Unknown human head allows Copilot fallback' $humanAccepted[1] 'copilot'
$mixedAccepted = @(Get-AcceptedMachineReviewProviders -HeadAuthorLogin 'chatgpt-codex-connector[bot]' -HeadCommitterLogin 'Copilot')
Assert-Equal 'Mixed machine head accepts no connected reviewer' $mixedAccepted.Count 0

Assert-Equal 'Structured AI review failure blocks' (Test-BlockingAiReviewBody 'AI-REVIEW FAIL — sha') $true
Assert-Equal 'P1 heading blocks' (Test-BlockingAiReviewBody '## P1 — unsafe bypass') $true
Assert-Equal 'P2 bullet does not block' (Test-BlockingAiReviewBody '- **P2: missing pagination') $false
Assert-Equal 'P2 bullet is advisory' (Test-AdvisoryAiReviewBody '- **P2: missing pagination') $true
Assert-Equal 'P1 badge blocks' (Test-BlockingAiReviewBody '![P1 Badge](badge.svg)') $true
Assert-Equal 'Bracketed P1 title blocks' (Test-BlockingAiReviewBody '[P1] unsafe bypass') $true
Assert-Equal 'Bracketed markdown P2 bullet is advisory' (Test-AdvisoryAiReviewBody '- **[P2] missing pagination**') $true
Assert-Equal 'Mixed P1 and P2 blocks' (Test-BlockingAiReviewBody "[P1] unsafe bypass`n[P2] tidy-up") $true
Assert-Equal 'Mixed P1 and P2 is not advisory-only' (Test-AdvisoryOnlyAiReviewBody "[P1] unsafe bypass`n[P2] tidy-up") $false
Assert-Equal 'P2-only change request does not block' (Test-BlockingAiReviewEvidence -Body '[P2] typo in prose' -ReviewState 'CHANGES_REQUESTED') $false
Assert-Equal 'Unclassified change request fails closed' (Test-BlockingAiReviewEvidence -Body 'Please change this.' -ReviewState 'CHANGES_REQUESTED') $true
Assert-Equal 'No-findings prose does not block' (Test-BlockingAiReviewBody 'No P0-P2 findings. Everything is clean.') $false
Assert-Equal 'Ordinary review prose does not block' (Test-BlockingAiReviewBody 'Looks good; no material issues found.') $false
Assert-Equal 'Neutral is a passing required-check conclusion' (Test-AiReviewPassingConclusion 'neutral') $true
Assert-Equal 'Success is a passing required-check conclusion' (Test-AiReviewPassingConclusion 'success') $true
Assert-Equal 'Failure is not a passing required-check conclusion' (Test-AiReviewPassingConclusion 'failure') $false

Assert-Equal 'No blocking findings need no repair' (Get-ReviewRepairDecision -HeadSha $head -AttemptedHeadShas @() -MaxAttempts 1 -HasBlockingFindings $false) 'none'
Assert-Equal 'First blocking finding head requests repair' (Get-ReviewRepairDecision -HeadSha $head -AttemptedHeadShas @() -MaxAttempts 1 -HasBlockingFindings $true) 'request'
Assert-Equal 'Same blocking finding head remains pending instead of exhausting' (Get-ReviewRepairDecision -HeadSha $head -AttemptedHeadShas @($head) -MaxAttempts 1 -HasBlockingFindings $true) 'pending'
Assert-Equal 'Post-fix blocking finding head exhausts one-repair budget' (Get-ReviewRepairDecision -HeadSha 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb' -AttemptedHeadShas @($head) -MaxAttempts 1 -HasBlockingFindings $true) 'block'
Assert-Throws 'Repair budget must be positive' { Get-ReviewRepairDecision -HeadSha $head -AttemptedHeadShas @() -MaxAttempts 0 -HasBlockingFindings $true }

$config = Get-Content (Join-Path $root 'policy/github-defaults.json') -Raw | ConvertFrom-Json
Assert-Equal 'Review dispatch mode is explicitly disabled pending canary' ([string]$config.independent_review.dispatch_mode) 'disabled_pending_e2e'
Assert-Equal 'Dispatch policy version is a positive integer' ([int]$config.independent_review.dispatch_policy_version -ge 1) $true
Assert-Equal 'Unreviewed canary auto-merge stops at R2' ([string]$config.auto_merge_max_risk) 'R2'
Assert-Equal 'Primary review window is two minutes when dispatch is re-enabled' ([int]$config.independent_review.primary_wait_minutes) 2
Assert-Equal 'Fallback review window is two minutes when dispatch is re-enabled' ([int]$config.independent_review.fallback_wait_minutes) 2

Assert-Equal 'No risk label defaults to R2' (Get-RiskFromLabels @()) 'R2'
Assert-Equal 'Single risk label is parsed' (Get-RiskFromLabels @('risk:R3','status:blocked')) 'R3'
Assert-Throws 'Multiple risk labels fail closed' { Get-RiskFromLabels @('risk:R1','risk:R3') }

Assert-Equal 'Workflow is control plane' (Test-ControlPlanePath '.github/workflows/pr-gate.yml') $true
Assert-Equal 'Evaluator is control plane' (Test-ControlPlanePath 'scripts/evaluate-ai-review.ps1') $true
Assert-Equal 'Review repair is control plane' (Test-ControlPlanePath 'scripts/request-review-repair.ps1') $true
Assert-Equal 'Pending-review pause is control plane' (Test-ControlPlanePath 'scripts/pause-pending-review.ps1') $true
Assert-Equal 'Thread reconciler is control plane' (Test-ControlPlanePath 'scripts/reconcile-machine-review-threads.ps1') $true
Assert-Equal 'Ordinary product source is not control plane' (Test-ControlPlanePath 'src/feature.ts') $false

$validGate = [pscustomobject]@{
  failure_class_prevented = 'irreversible production data loss'
  why_automation_is_insufficient = 'intent cannot be inferred from repository state'
  decision_owner = 'authorized human owner'
  gate_removal_condition = 'operation becomes reversible with verified restore'
}
Assert-Equal 'Complete manual gate accepted' (Assert-ManualGateJustification $validGate) $true
Assert-Throws 'Incomplete manual gate refused' { Assert-ManualGateJustification ([pscustomobject]@{failure_class_prevented='x';why_automation_is_insufficient='y';decision_owner='z'}) }

$bootstrap = Get-Content (Join-Path $root 'scripts/bootstrap-repo.ps1') -Raw
if ($bootstrap -notmatch 'templates/AI_REVIEW\.yml') { throw 'bootstrap must source AI_REVIEW template.' }
if ($bootstrap -notmatch 'templates/PR_AUTOMATION\.yml') { throw 'bootstrap must source PR_AUTOMATION template.' }
if ($bootstrap -match 'templates/CODEOWNERS|Copy-Item[^\r\n]*CODEOWNERS') { throw 'bootstrap must not install native human CODEOWNERS.' }
if ($bootstrap -notmatch 'Remove-Item[^\r\n]*\.github/CODEOWNERS') { throw 'bootstrap must remove legacy native CODEOWNERS.' }

Write-Host 'review-policy tests: PASS' -ForegroundColor Green
