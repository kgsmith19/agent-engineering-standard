param(
  [Parameter(Mandatory)][string]$Repo,
  [Parameter(Mandatory)][int]$Pr,
  [ValidateSet('R0','R1','R2','R3','R4')][string]$Risk = 'R2'
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib/review-policy.ps1')
. (Join-Path $PSScriptRoot 'lib/gh-api.ps1')

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw 'GitHub CLI (gh) is required.' }
$config = Get-Content (Join-Path $PSScriptRoot '..\policy\github-defaults.json') -Raw | ConvertFrom-Json

function Get-LatestActionsCheckRun {
  param([string]$Head,[string]$Name)
  $encoded = [uri]::EscapeDataString($Name)
  $raw = & gh api -H 'Accept: application/vnd.github+json' "repos/$Repo/commits/$Head/check-runs?check_name=$encoded" 2>&1
  if ($LASTEXITCODE -ne 0) { throw ($raw -join "`n") }
  $runs = (($raw -join "`n") | ConvertFrom-Json).check_runs
  $latest = @($runs | Where-Object { $_.name -eq $Name -and $_.app.slug -eq 'github-actions' } | Sort-Object id | Select-Object -Last 1)
  if ($latest.Count -eq 0) { return $null }
  return $latest[0]
}

$prRaw = & gh pr view $Pr --repo $Repo --json isDraft,state,labels,baseRefName,headRefName,headRefOid,author 2>&1
if ($LASTEXITCODE -ne 0) { throw ($prRaw -join "`n") }
$prData = ($prRaw -join "`n") | ConvertFrom-Json
if ($prData.state -ne 'OPEN') { throw "PR #$Pr is not open." }
if ($prData.isDraft) { throw "Ready-at-creation policy violation: $Repo PR #$Pr is draft. Auto-merge was not attempted." }
if (@($prData.labels | ForEach-Object { $_.name }) -contains 'status:blocked') { throw "PR #$Pr is status:blocked." }
if ([string]$prData.author.login -eq 'Copilot' -or [string]$prData.headRefName -like 'copilot/*') {
  throw 'Copilot-cloud-agent-owned PRs require human review/merge by GitHub platform policy and cannot use the unattended lane.'
}

$labelRisk = Get-RiskFromLabels @($prData.labels | ForEach-Object { $_.name })
if ($Risk -ne $labelRisk) { throw "Risk mismatch: caller supplied $Risk but PR labels resolve to $labelRisk." }
$riskNumber = [int]$Risk.Substring(1)
$maxRisk = [int]([string]$config.auto_merge_max_risk).Substring(1)
if ($Risk -eq 'R4' -or $riskNumber -gt $maxRisk) { throw "Auto-merge refused for $Risk; configured maximum is $($config.auto_merge_max_risk)." }

$reviewersRaw = & gh api "repos/$Repo/pulls/$Pr/requested_reviewers" 2>&1
if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect requested reviewers.' }
$requested = @(($reviewersRaw -join "`n") | ConvertFrom-Json | Select-Object -ExpandProperty users | ForEach-Object { [string]$_.login })
$forbidden = @($config.forbidden_requested_reviewers | Where-Object { $requested -contains [string]$_ })
if ($forbidden.Count -gt 0) { throw "Forbidden human reviewer request remains: $($forbidden -join ', ')." }

$filesRaw = & gh api --paginate "repos/$Repo/pulls/$Pr/files?per_page=100" --jq '.[].filename' 2>&1
if ($LASTEXITCODE -ne 0) { throw ($filesRaw -join "`n") }
$controlPlane = $Repo -match '/agent-engineering-standard$'
foreach ($file in @($filesRaw)) {
  if (Test-ControlPlanePath ([string]$file)) { $controlPlane = $true; break }
}
if ($controlPlane -and $riskNumber -lt 3) { throw 'Control-plane changes must declare at least R3.' }
if ($controlPlane -and [bool]$config.manual_gates.control_plane.required) {
  throw "Auto-merge refused by justified control-plane gate. Removal condition: $($config.manual_gates.control_plane.gate_removal_condition)"
}

$metaRaw = Invoke-WithAdminToken { & gh api "repos/$Repo" 2>&1 }
if ($LASTEXITCODE -ne 0) { throw "Cannot inspect live repository settings for $Repo." }
$meta = ($metaRaw -join "`n") | ConvertFrom-Json
if ($prData.baseRefName -ne $meta.default_branch) { throw "PR targets '$($prData.baseRefName)', not protected default branch '$($meta.default_branch)'." }
if (-not $meta.allow_auto_merge) { throw 'Live GitHub setting drift: auto-merge is off.' }
if (-not $meta.allow_update_branch) { throw 'Live GitHub setting drift: update branch is off.' }
if (-not $meta.allow_squash_merge -or $meta.allow_merge_commit -or $meta.allow_rebase_merge) { throw 'Live GitHub merge policy is not squash-only.' }

# Merge ordering, evaluated not obeyed: the exact head needs a PR Gate success
# and an EXISTING AI Review evaluation with current dispatch_policy_version
# evidence; only a failure conclusion carrying a structured threat verdict
# refuses. neutral and success both arm in every dispatch mode.
$headSha = [string]$prData.headRefOid
$gateRun = Get-LatestActionsCheckRun $headSha ([string]$config.required_status_context)
if (-not $gateRun -or [string]$gateRun.conclusion -ne 'success') { throw "Auto-merge refused: no exact-head 'PR Gate' success from GitHub Actions for $headSha." }
$reviewRun = Get-LatestActionsCheckRun $headSha 'Advisory: AI Review'
if (-not $reviewRun) { throw "Auto-merge refused: no exact-head 'Advisory: AI Review' evaluation exists for $headSha." }
if (-not (Test-CurrentDispatchEvidence -Summary ([string]$reviewRun.output.summary) -PolicyVersion ([int]$config.independent_review.dispatch_policy_version))) { throw "Auto-merge refused: exact-head 'Advisory: AI Review' evidence does not carry current dispatch_policy_version $($config.independent_review.dispatch_policy_version) for $headSha." }
if ([string]$reviewRun.conclusion -eq 'failure' -and (Test-BlockingAiReviewBody ([string]$reviewRun.output.summary))) { throw "Auto-merge refused: exact-head 'Advisory: AI Review' failure carries a structured threat verdict for $headSha." }

$actionsAppRaw = & gh api /apps/github-actions 2>&1
if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve GitHub Actions App identity.' }
$actionsAppId = [int]((($actionsAppRaw -join "`n") | ConvertFrom-Json).id)

$rulesetSummaries = @(Invoke-WithAdminToken { Get-Paged "repos/$Repo/rulesets?per_page=100" })
$summary = ($rulesetSummaries | Where-Object { $_.name -eq $config.ruleset_name -and $_.target -eq 'branch' -and $_.enforcement -eq 'active' } | Select-Object -First 1)
if (-not $summary) { throw "Live active branch ruleset '$($config.ruleset_name)' is missing." }

# GitHub composes every ruleset that targets the branch and the most restrictive
# rule wins. Refuse to arm auto-merge if another active ruleset also governs the
# default branch, because it may silently retain approvals/checks that the
# canonical policy intentionally removed.
$defaultBranchEncoded = [uri]::EscapeDataString([string]$meta.default_branch)
$effectiveRules = @(Invoke-WithAdminToken { Get-Paged "repos/$Repo/rules/branches/${defaultBranchEncoded}?per_page=100" })
$conflictingIds = @($effectiveRules |
  ForEach-Object { [long]$_.ruleset_id } |
  Where-Object { $_ -gt 0 -and $_ -ne [long]$summary.id } |
  Select-Object -Unique)
if ($conflictingIds.Count -gt 0) {
  $conflicts = @($conflictingIds | ForEach-Object {
    $id = $_
    $match = $rulesetSummaries | Where-Object { [long]$_.id -eq $id } | Select-Object -First 1
    if ($match) { "$($match.name) (#$id)" } else { "ruleset #$id" }
  }) -join ', '
  throw "Auto-merge refused: conflicting active default-branch ruleset(s): $conflicts. Reconcile live policy first."
}

$detailRaw = Invoke-WithAdminToken { & gh api "repos/$Repo/rulesets/$($summary.id)" 2>&1 }
if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect live ruleset details.' }
$detail = ($detailRaw -join "`n") | ConvertFrom-Json
if ($detail.enforcement -ne 'active') { throw 'Live ruleset is not active.' }
if ($detail.bypass_actors -and @($detail.bypass_actors).Count -gt 0) { throw 'Live ruleset has bypass actors.' }
if (-not (@($detail.conditions.ref_name.include) -contains '~DEFAULT_BRANCH')) { throw 'Live ruleset does not protect the default branch.' }

$prRule = $detail.rules | Where-Object { $_.type -eq 'pull_request' } | Select-Object -First 1
if (-not $prRule) { throw 'Live ruleset does not require pull requests.' }
if ([int]$prRule.parameters.required_approving_review_count -ne 0) { throw 'Human approval requirement is not zero.' }
if ([bool]$prRule.parameters.require_code_owner_review) { throw 'Code Owner review requirement is enabled.' }
if ([bool]$prRule.parameters.require_last_push_approval) { throw 'Last-push human approval requirement is enabled.' }
if (-not [bool]$prRule.parameters.dismiss_stale_reviews_on_push) { throw 'Stale reviews are not dismissed on push.' }
if ([bool]$prRule.parameters.required_review_thread_resolution -ne [bool]$config.required_review_thread_resolution) { throw 'Review-thread resolution requirement drifted from policy.' }
$methods = @($prRule.parameters.allowed_merge_methods)
if ($methods.Count -ne 1 -or $methods[0] -ne 'squash') { throw 'Ruleset is not squash-only.' }

$statusRule = $detail.rules | Where-Object { $_.type -eq 'required_status_checks' } | Select-Object -First 1
if (-not $statusRule) { throw 'Live ruleset has no required-status-check rule.' }
$requiredContexts = @([string]$config.required_status_context)
if ([bool]$config.independent_review.required_for_auto_merge) { $requiredContexts += [string]$config.required_ai_review_context }
foreach ($context in $requiredContexts) {
  $required = @($statusRule.parameters.required_status_checks) | Where-Object { $_.context -eq $context } | Select-Object -First 1
  if (-not $required) { throw "Live ruleset does not require '$context'." }
  if ([int]$required.integration_id -ne $actionsAppId) { throw "Required '$context' is not bound to GitHub Actions." }
}

# The arming identity is the fine-grained AUTOMATION_TOKEN PAT and requires
# Administration:read + Contents:write + Pull requests:write. No GitHub App
# exists; provisioning one is an owner authority item, deliberately not built here.
# Draft/ready races: re-verify the exact PR immediately before arming.
for ($attempt = 1; $attempt -le 3; $attempt++) {
  $freshRaw = & gh api "repos/$Repo/pulls/$Pr" 2>&1
  if ($LASTEXITCODE -ne 0) { throw ($freshRaw -join "`n") }
  $fresh = ($freshRaw -join "`n") | ConvertFrom-Json
  if ([string]$fresh.head.sha -ne $headSha) { throw "Auto-merge refused: head moved from $headSha to $($fresh.head.sha) before arming." }
  if ($fresh.state -ne 'open') { throw "Auto-merge refused: PR #$Pr is no longer open." }
  if (-not $fresh.draft) { break }
  if ($attempt -eq 3) { throw "Auto-merge refused: PR #$Pr still reports draft after $attempt pre-arm checks." }
  Start-Sleep -Seconds 5
}

Invoke-WithAdminToken { & gh pr merge $Pr --repo $Repo --auto --squash }
if ($LASTEXITCODE -ne 0) { throw "Could not enable auto-merge for $Repo PR #$Pr." }
Write-Host "AUTO-MERGE ARMED: $Repo PR #$Pr ($Risk). GitHub must receive a latest-head $($requiredContexts -join ' + ') success before squash merge." -ForegroundColor Green
