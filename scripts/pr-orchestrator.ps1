param(
  [Parameter(Mandatory)][ValidateSet('pr-event','gate-result','review-event','comment-event','watchdog')][string]$Mode,
  [Parameter(Mandatory)][string]$Repo,
  [int]$Pr = 0,
  [string]$GateConclusion = '',
  [string]$GateHeadSha = '',
  [long]$GateRunId = 0,
  [string]$ConfigPath = (Join-Path $PSScriptRoot '..\policy\github-defaults.json')
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib/review-policy.ps1')

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw 'GitHub CLI (gh) is required.' }
$config = Get-Content $ConfigPath -Raw | ConvertFrom-Json
$automation = $config.pr_automation
$reviewPolicy = $config.independent_review
$ownerTag = "@$($config.owner)"

function Invoke-GhJson {
  param([string]$Method,[string]$Endpoint,$Body)
  $tmp = [System.IO.Path]::GetTempFileName()
  try {
    $Body | ConvertTo-Json -Depth 10 | Set-Content $tmp -Encoding utf8 -NoNewline
    $raw = & gh api --method $Method $Endpoint --input $tmp 2>&1
    if ($LASTEXITCODE -ne 0) { throw ($raw -join "`n") }
    if ($raw) { return (($raw -join "`n") | ConvertFrom-Json) }
  } finally { Remove-Item $tmp -Force -ErrorAction SilentlyContinue }
}

function Get-Paged {
  param([string]$Endpoint)
  $raw = & gh api --paginate --slurp $Endpoint 2>&1
  if ($LASTEXITCODE -ne 0) { throw ($raw -join "`n") }
  $pages = ($raw -join "`n") | ConvertFrom-Json
  foreach ($page in @($pages)) { foreach ($item in @($page)) { $item } }
}

function Get-Pr {
  param([int]$Number)
  $raw = & gh pr view $Number --repo $Repo --json number,state,isDraft,labels,headRefOid,headRefName,baseRefName,author,autoMergeRequest,mergeable,title,updatedAt 2>&1
  if ($LASTEXITCODE -ne 0) { throw ($raw -join "`n") }
  return (($raw -join "`n") | ConvertFrom-Json)
}

function Get-Comments {
  param([int]$Number)
  return @(Get-Paged "repos/$Repo/issues/$Number/comments?per_page=100")
}

function Add-CommentOnce {
  param([int]$Number,[string]$Marker,[string]$Body)
  if (@(Get-Comments $Number | Where-Object { [string]$_.body -like "*$Marker*" }).Count -gt 0) { return }
  & gh pr comment $Number --repo $Repo --body "$Body`n`n$Marker" | Out-Host
  if ($LASTEXITCODE -ne 0) { throw "Could not comment on $Repo PR #$Number." }
}

function Remove-ForbiddenReviewers {
  param([int]$Number)
  $raw = & gh api "repos/$Repo/pulls/$Number/requested_reviewers" 2>&1
  if ($LASTEXITCODE -ne 0) { throw ($raw -join "`n") }
  $requested = @(($raw -join "`n") | ConvertFrom-Json | Select-Object -ExpandProperty users | ForEach-Object { [string]$_.login })
  $forbidden = @($config.forbidden_requested_reviewers | Where-Object { $requested -contains [string]$_ })
  if ($forbidden.Count -eq 0) { return }
  Invoke-GhJson DELETE "repos/$Repo/pulls/$Number/requested_reviewers" @{ reviewers=$forbidden; team_reviewers=@() } | Out-Null
  Add-CommentOnce $Number '<!-- automation:removed-reviewers -->' "Removed forbidden requested reviewer(s): $($forbidden -join ', '). Routine automation may tag $ownerTag for authority, but never assigns Kyle as a reviewer."
}

function Disable-AutoMerge {
  param([int]$Number,$PrData)
  if (-not $PrData.autoMergeRequest) { return }
  $raw = & gh pr merge $Number --repo $Repo --disable-auto 2>&1
  if ($LASTEXITCODE -ne 0) { throw ($raw -join "`n") }
}

function Set-Blocked {
  param([int]$Number,[string]$Code,[string]$Reason)
  & gh pr edit $Number --repo $Repo --add-label $automation.blocked_label 2>&1 | Out-Null
  Add-CommentOnce $Number "<!-- automation:blocked:$Code -->" "$ownerTag AUTOMATION-BLOCKED: $Reason`n`nYou are tagged for the decision, not assigned as a reviewer."
}

function Tag-Authority {
  param([int]$Number,[ValidateSet('control_plane','R4')][string]$Kind)
  $gate = $config.manual_gates.PSObject.Properties[$Kind].Value
  $body = @"
$ownerTag AUTHORITY REQUIRED: $Kind

- Failure class prevented: $($gate.failure_class_prevented)
- Why automation is insufficient: $($gate.why_automation_is_insufficient)
- Decision owner: $($gate.decision_owner)
- Gate removal condition: $($gate.gate_removal_condition)

All machine checks still run. You are tagged, never assigned as a GitHub reviewer.
"@
  Add-CommentOnce $Number "<!-- authority-required:$Kind -->" $body
}

function Get-ChangedFiles {
  param([int]$Number)
  $raw = & gh api --paginate "repos/$Repo/pulls/$Number/files?per_page=100" --jq '.[].filename' 2>&1
  if ($LASTEXITCODE -ne 0) { throw ($raw -join "`n") }
  return @($raw | Where-Object { $_ })
}

function Test-ControlPlane {
  param([int]$Number)
  if ($Repo -match '/agent-engineering-standard$') { return $true }
  foreach ($path in @(Get-ChangedFiles $Number)) {
    if (Test-ControlPlanePath $path) { return $true }
  }
  return $false
}

function Get-Risk {
  param($PrData)
  return Get-RiskFromLabels @($PrData.labels | ForEach-Object { $_.name })
}

function Request-Repair {
  param(
    [ValidateSet('ci','review','conflict')][string]$Kind,
    [int]$Number,
    $PrData,
    [long]$RunId = 0
  )

  $limits = @{
    ci = [int]$automation.max_ci_fix_attempts
    review = [int]$automation.max_review_fix_attempts
    conflict = [int]$automation.max_conflict_fix_attempts
  }
  $comments = @(Get-Comments $Number)
  $attempts = @($comments | Where-Object { [string]$_.body -match "<!-- auto-fix:$Kind:" }).Count
  if ($attempts -ge $limits[$Kind]) {
    Set-Blocked $Number "$Kind-budget" "$Kind repair budget exhausted ($($limits[$Kind]))."
    return
  }

  $head = [string]$PrData.headRefOid
  $marker = "<!-- auto-fix:$Kind:$head:$($attempts + 1) -->"
  if ($Kind -eq 'conflict' -and [string]$PrData.author.login -eq 'dependabot[bot]') {
    Add-CommentOnce $Number $marker '@dependabot rebase'
    return
  }

  $scope = switch ($Kind) {
    'ci' { if ($RunId) { "GitHub Actions run $RunId" } else { 'the current failing PR Gate' } }
    'review' { "material current-head AI review findings for $head" }
    'conflict' { 'the merge conflict against current main' }
  }
  $body = "@copilot investigate and fix $scope on PR #$Number. Read the complete evidence before editing. Follow AGENTS.md and the linked Issue/SPEC. For nontrivial or cross-cutting work, create a thin Superpowers-style plan/spec first. Make the smallest root-cause fix, never weaken tests/policies/evaluators, verify, and update this existing PR. Attempt $($attempts + 1)/$($limits[$Kind])."
  Add-CommentOnce $Number $marker $body
}

function Ensure-PrState {
  param([int]$Number)
  Remove-ForbiddenReviewers $Number
  $prData = Get-Pr $Number
  if ($prData.state -ne 'OPEN') { return $prData }

  $labels = @($prData.labels | ForEach-Object { $_.name })
  if ($prData.isDraft) {
    Disable-AutoMerge $Number $prData
    if ($labels -notcontains $automation.draft_ready_label) { return $prData }
    & gh pr ready $Number --repo $Repo | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Could not mark $Repo PR #$Number Ready." }
    & gh pr edit $Number --repo $Repo --remove-label $automation.draft_ready_label 2>&1 | Out-Null
    $prData = Get-Pr $Number
  }

  if ([string]$prData.author.login -eq 'Copilot' -or [string]$prData.headRefName -like 'copilot/*') {
    Disable-AutoMerge $Number $prData
    Set-Blocked $Number 'copilot-owned-pr' 'GitHub requires human review and merge for pull requests created by Copilot cloud agent. Use Copilot only on an existing non-Copilot PR, or re-home this work through a non-Copilot implementation lane.'
    return $prData
  }

  if ($prData.mergeable -eq 'CONFLICTING') {
    Disable-AutoMerge $Number $prData
    Request-Repair conflict $Number $prData
    return $prData
  }

  try { $risk = Get-Risk $prData }
  catch {
    Disable-AutoMerge $Number $prData
    Set-Blocked $Number 'risk-labels' $_.Exception.Message
    return $prData
  }

  if ($risk -eq 'R4') {
    Disable-AutoMerge $Number $prData
    Tag-Authority $Number R4
    return $prData
  }
  if (Test-ControlPlane $Number) {
    Disable-AutoMerge $Number $prData
    Tag-Authority $Number control_plane
    return $prData
  }
  if ($labels -contains $automation.blocked_label) {
    Disable-AutoMerge $Number $prData
    return $prData
  }

  if (-not $prData.autoMergeRequest) {
    & pwsh -NoProfile -File (Join-Path $PSScriptRoot 'auto-merge.ps1') -Repo $Repo -Pr $Number -Risk $risk
    if ($LASTEXITCODE -ne 0) {
      Set-Blocked $Number 'auto-merge-settings' 'Auto-merge could not be armed. Reconcile live repository settings and ruleset with setup-portfolio.ps1.'
    }
  }
  return $prData
}

function Get-ReviewFailures {
  param([int]$Number,$PrData)
  $head = [string]$PrData.headRefOid
  $failures = New-Object System.Collections.Generic.List[string]
  foreach ($review in @(Get-Paged "repos/$Repo/pulls/$Number/reviews?per_page=100")) {
    $provider = Get-MachineReviewProvider ([string]$review.user.login)
    if (-not $provider -or $review.commit_id -ne $head -or $review.state -in @('DISMISSED','PENDING')) { continue }
    if ($review.state -eq 'CHANGES_REQUESTED' -or (Test-MaterialAiReviewBody ([string]$review.body))) { $failures.Add($provider) }
  }
  foreach ($comment in @(Get-Comments $Number)) {
    if ((Get-MachineReviewProvider ([string]$comment.user.login)) -eq 'copilot' -and
        [string]$comment.body -match '(?im)^\s*AI-REVIEW\s+FAIL\b' -and
        [string]$comment.body -match [regex]::Escape($head)) { $failures.Add('copilot') }
  }
  return @($failures | Select-Object -Unique)
}

function Invoke-AiReview {
  param([int]$Number)
  & pwsh -NoProfile -File (Join-Path $PSScriptRoot 'evaluate-ai-review.ps1') -Repo $Repo -Pr $Number
  if ($LASTEXITCODE -ne 0) { throw "AI Review evaluator failed for $Repo PR #$Number." }
}

function Get-CheckConclusion {
  param([string]$Head,[string]$Name)
  $encoded = [uri]::EscapeDataString($Name)
  $raw = & gh api -H 'Accept: application/vnd.github+json' "repos/$Repo/commits/$Head/check-runs?check_name=$encoded" 2>&1
  if ($LASTEXITCODE -ne 0) { throw ($raw -join "`n") }
  $runs = (($raw -join "`n") | ConvertFrom-Json).check_runs
  $latest = @($runs | Where-Object { $_.name -eq $Name -and $_.app.slug -eq 'github-actions' } | Sort-Object id | Select-Object -Last 1)
  if ($latest.Count -eq 0) { return $null }
  return [string]$latest[0].conclusion
}

function Wait-ForReview {
  param([int]$Number,[string]$Head,[int]$Minutes)
  $deadline = [datetimeoffset]::UtcNow.AddMinutes($Minutes)
  do {
    Start-Sleep -Seconds ([int]$reviewPolicy.poll_seconds)
    $current = Get-Pr $Number
    if ($current.state -ne 'OPEN' -or $current.isDraft -or [string]$current.headRefOid -ne $Head) { return 'changed' }
    Invoke-AiReview $Number
    $failures = @(Get-ReviewFailures $Number $current)
    if ($failures.Count -gt 0) {
      Request-Repair review $Number $current
      return 'failed'
    }
    if ((Get-CheckConclusion $Head 'AI Review') -eq 'success') { return 'success' }
  } while ([datetimeoffset]::UtcNow -lt $deadline)
  return 'timeout'
}

function Run-ReviewCycle {
  param([int]$Number)
  $prData = Get-Pr $Number
  if ($prData.state -ne 'OPEN' -or $prData.isDraft) { return }

  Invoke-AiReview $Number
  $failures = @(Get-ReviewFailures $Number $prData)
  if ($failures.Count -gt 0) {
    Request-Repair review $Number $prData
    return
  }
  if ((Get-CheckConclusion ([string]$prData.headRefOid) 'AI Review') -eq 'success') { return }

  & pwsh -NoProfile -File (Join-Path $PSScriptRoot 'request-machine-review.ps1') -Repo $Repo -Pr $Number -Provider auto
  if ($LASTEXITCODE -ne 0) {
    Set-Blocked $Number 'review-request' 'No budgeted machine reviewer could be requested.'
    return
  }

  $result = Wait-ForReview $Number ([string]$prData.headRefOid) ([int]$reviewPolicy.primary_wait_minutes)
  if ($result -ne 'timeout') { return }

  & pwsh -NoProfile -File (Join-Path $PSScriptRoot 'request-machine-review.ps1') -Repo $Repo -Pr $Number -Provider auto
  if ($LASTEXITCODE -ne 0) {
    Set-Blocked $Number 'review-fallback' 'Primary machine review stalled and no fallback reviewer was available.'
    return
  }

  $result = Wait-ForReview $Number ([string]$prData.headRefOid) ([int]$reviewPolicy.fallback_wait_minutes)
  if ($result -eq 'timeout') {
    Set-Blocked $Number 'review-timeout' 'Machine review did not return within the bounded primary and fallback windows.'
  }
}

function Handle-GateResult {
  param([int]$Number)
  $prData = Ensure-PrState $Number
  if ($prData.state -ne 'OPEN' -or $prData.isDraft) { return }
  if ($GateHeadSha -and [string]$prData.headRefOid -ne $GateHeadSha) { return }

  switch ($GateConclusion) {
    'success' { Run-ReviewCycle $Number }
    'failure' { Request-Repair ci $Number $prData $GateRunId }
    'timed_out' { Request-Repair ci $Number $prData $GateRunId }
    'startup_failure' { Request-Repair ci $Number $prData $GateRunId }
    'action_required' { Set-Blocked $Number 'workflow-approval' 'GitHub is waiting for workflow approval. Disable the Copilot cloud-agent workflow-approval setting for this repository.' }
    'skipped' { Set-Blocked $Number 'gate-skipped' 'Ready PR Gate was skipped; its workflow trigger or job condition is invalid.' }
    default { }
  }
}

function Handle-ReviewEvent {
  param([int]$Number)
  Remove-ForbiddenReviewers $Number
  $prData = Get-Pr $Number
  if ($prData.state -ne 'OPEN' -or $prData.isDraft) { return }
  Invoke-AiReview $Number
  $failures = @(Get-ReviewFailures $Number $prData)
  if ($failures.Count -gt 0) { Request-Repair review $Number $prData }
}

function Handle-Watchdog {
  $raw = & gh pr list --repo $Repo --state open --limit 100 --json number 2>&1
  if ($LASTEXITCODE -ne 0) { throw ($raw -join "`n") }
  foreach ($item in @(($raw -join "`n") | ConvertFrom-Json)) {
    $number = [int]$item.number
    try {
      $prData = Ensure-PrState $number
      if ($prData.state -ne 'OPEN' -or $prData.isDraft) { continue }
      $gate = Get-CheckConclusion ([string]$prData.headRefOid) 'PR Gate'
      if ($gate -eq 'success') { Run-ReviewCycle $number }
      elseif ($gate -in @('failure','timed_out','startup_failure')) { Request-Repair ci $number $prData }
      elseif (-not $gate) { Set-Blocked $number 'missing-pr-gate' 'No current-head PR Gate check exists.' }
    } catch { Write-Warning "$Repo PR #$number watchdog: $($_.Exception.Message)" }
  }
}

switch ($Mode) {
  'pr-event' { if ($Pr -le 0) { throw 'Pr is required.' }; Ensure-PrState $Pr | Out-Null }
  'gate-result' { if ($Pr -le 0) { throw 'Pr is required.' }; Handle-GateResult $Pr }
  'review-event' { if ($Pr -le 0) { throw 'Pr is required.' }; Handle-ReviewEvent $Pr }
  'comment-event' { if ($Pr -le 0) { throw 'Pr is required.' }; Handle-ReviewEvent $Pr }
  'watchdog' { Handle-Watchdog }
}
