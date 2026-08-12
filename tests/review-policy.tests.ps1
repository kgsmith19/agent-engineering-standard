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

$actionsComment = [pscustomobject]@{ user = [pscustomobject]@{ login = 'github-actions[bot]' } }
$ownerComment = [pscustomobject]@{ user = [pscustomobject]@{ login = 'kgsmith19' } }
$untrustedComment = [pscustomobject]@{ user = [pscustomobject]@{ login = 'random-user' } }
Assert-Equal 'Actions marker trusted' (Test-TrustedAutomationComment $actionsComment 'kgsmith19') $true
Assert-Equal 'Owner marker trusted' (Test-TrustedAutomationComment $ownerComment 'kgsmith19') $true
Assert-Equal 'Ordinary commenter marker rejected' (Test-TrustedAutomationComment $untrustedComment 'kgsmith19') $false

$config = Get-Content (Join-Path $root 'policy/github-defaults.json') -Raw | ConvertFrom-Json
Assert-Equal 'Policy manages all 13 non-archived repositories' (@($config.repositories).Count) 13
Assert-Equal 'Unreviewed canary auto-merge stops at R2' ([string]$config.auto_merge_max_risk) 'R2'
Assert-Equal 'Repair dispatch is explicitly disabled' ([bool]$config.pr_automation.repair_dispatch_enabled) $false
Assert-Equal 'CI repair budget is the approved three attempts' ([int]$config.pr_automation.max_ci_fix_attempts) 3
Assert-Equal 'Conflict repair budget is the approved two attempts' ([int]$config.pr_automation.max_conflict_fix_attempts) 2
Assert-Equal 'Watchdog reconciles six-hourly' ([int]$config.pr_automation.watchdog_interval_minutes) 360

Assert-Equal 'No risk label defaults to R2' (Get-RiskFromLabels @()) 'R2'
Assert-Equal 'Single risk label is parsed' (Get-RiskFromLabels @('risk:R3','status:blocked')) 'R3'
Assert-Throws 'Multiple risk labels fail closed' { Get-RiskFromLabels @('risk:R1','risk:R3') }

Assert-Equal 'Workflow is control plane' (Test-ControlPlanePath '.github/workflows/pr-gate.yml') $true
Assert-Equal 'Orchestrator is control plane' (Test-ControlPlanePath 'scripts/pr-orchestrator.ps1') $true
Assert-Equal 'Gate result router is control plane' (Test-ControlPlanePath 'scripts/gate-result-router.ps1') $true
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
if ($bootstrap -match 'templates/AI_REVIEW\.yml') { throw 'bootstrap must not source the retired AI_REVIEW template.' }
if ($bootstrap -notmatch 'templates/PR_AUTOMATION\.yml') { throw 'bootstrap must source PR_AUTOMATION template.' }
if ($bootstrap -match 'templates/CODEOWNERS|Copy-Item[^\r\n]*CODEOWNERS') { throw 'bootstrap must not install native human CODEOWNERS.' }
if ($bootstrap -notmatch 'Remove-Item[^\r\n]*\.github/CODEOWNERS') { throw 'bootstrap must remove legacy native CODEOWNERS.' }

Write-Host 'review-policy tests: PASS' -ForegroundColor Green
