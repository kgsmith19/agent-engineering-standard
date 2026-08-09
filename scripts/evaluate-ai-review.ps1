param(
  [Parameter(Mandatory)][string]$Repo,
  [Parameter(Mandatory)][int]$Pr
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib/review-policy.ps1')

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw 'GitHub CLI (gh) is required.' }

function Invoke-GhJson {
  param([string]$Method, [string]$Endpoint, $Body)
  $tmp = [System.IO.Path]::GetTempFileName()
  try {
    $Body | ConvertTo-Json -Depth 10 | Set-Content $tmp -Encoding utf8 -NoNewline
    $raw = & gh api --method $Method $Endpoint --input $tmp 2>&1
    if ($LASTEXITCODE -ne 0) { throw ($raw -join "`n") }
    if ($raw) { return (($raw -join "`n") | ConvertFrom-Json) }
  }
  finally { Remove-Item $tmp -Force -ErrorAction SilentlyContinue }
}

function Get-Paged {
  param([Parameter(Mandatory)][string]$Endpoint)
  $raw = & gh api --paginate --slurp $Endpoint 2>&1
  if ($LASTEXITCODE -ne 0) { throw ($raw -join "`n") }
  $pages = ($raw -join "`n") | ConvertFrom-Json
  foreach ($page in @($pages)) { foreach ($item in @($page)) { $item } }
}

function Set-AiReviewCheck {
  param([string]$HeadSha,[ValidateSet('success','failure')][string]$Conclusion,[string]$Summary)
  $encoded = [uri]::EscapeDataString('AI Review')
  $raw = & gh api -H 'Accept: application/vnd.github+json' "repos/$Repo/commits/$HeadSha/check-runs?check_name=$encoded" 2>&1
  if ($LASTEXITCODE -ne 0) { throw ($raw -join "`n") }
  $runs = (($raw -join "`n") | ConvertFrom-Json).check_runs
  $existing = @($runs | Where-Object { $_.name -eq 'AI Review' -and $_.app.slug -eq 'github-actions' } | Sort-Object id | Select-Object -Last 1)
  $body = @{ status='completed'; conclusion=$Conclusion; output=@{ title='AI Review'; summary=$Summary } }
  if ($existing.Count -gt 0) {
    Invoke-GhJson -Method PATCH -Endpoint "repos/$Repo/check-runs/$($existing[0].id)" -Body $body | Out-Null
  }
  else {
    $body.name = 'AI Review'; $body.head_sha = $HeadSha
    Invoke-GhJson -Method POST -Endpoint "repos/$Repo/check-runs" -Body $body | Out-Null
  }
}

$prRaw = & gh api "repos/$Repo/pulls/$Pr" 2>&1
if ($LASTEXITCODE -ne 0) { throw ($prRaw -join "`n") }
$prData = ($prRaw -join "`n") | ConvertFrom-Json
$headSha = [string]$prData.head.sha
$author = [string]$prData.user.login

if ($prData.draft) {
  Set-AiReviewCheck -HeadSha $headSha -Conclusion failure -Summary 'Draft PR: machine review is intentionally deferred until Ready.'
  exit 0
}

# A Codex-authored GitHub App PR must use Copilot. All other PRs accept one fresh
# Codex review task/session, with bounded Copilot fallback. Branch names are not
# trusted as implementation identity.
$acceptedProviders = if ($author.ToLowerInvariant() -match '^chatgpt-codex-connector(?:\[bot\])?$') { @('copilot') } else { @('codex','copilot') }
$reviews = @(Get-Paged "repos/$Repo/pulls/$Pr/reviews?per_page=100")
$comments = @(Get-Paged "repos/$Repo/issues/$Pr/comments?per_page=100")
$passes = New-Object System.Collections.Generic.List[string]
$failures = New-Object System.Collections.Generic.List[string]

foreach ($review in $reviews) {
  $provider = Get-MachineReviewProvider -Login ([string]$review.user.login)
  if (-not $provider -or $review.commit_id -ne $headSha -or $review.state -in @('DISMISSED','PENDING')) { continue }
  if ($review.state -eq 'CHANGES_REQUESTED' -or (Test-MaterialAiReviewBody -Body ([string]$review.body))) {
    $failures.Add("$provider review by $($review.user.login) contains material findings")
  }
  elseif ($acceptedProviders -contains $provider) {
    $passes.Add("$provider formal review by $($review.user.login)")
  }
}

$structured = @($comments | Where-Object {
  (Get-MachineReviewProvider -Login ([string]$_.user.login)) -eq 'copilot' -and
  $_.body -match '(?im)^\s*AI-REVIEW\s+(PASS|FAIL)\b' -and
  $_.body -match [regex]::Escape($headSha)
} | Sort-Object created_at)
if ($structured.Count -gt 0) {
  $latest = $structured[-1]
  if ($latest.body -match '(?im)^\s*AI-REVIEW\s+FAIL\b') { $failures.Add('Copilot structured exact-head review contains material findings') }
  elseif ($acceptedProviders -contains 'copilot') { $passes.Add('Copilot structured exact-head review') }
}

# Codex may react with thumbs-up instead of posting an empty formal review. Only
# a reaction on the exact-head request marker counts; unrelated PR reactions do not.
$codexRequests = @($comments | Where-Object { [string]$_.body -like "*ai-review-request:codex:$headSha*" })
foreach ($request in $codexRequests) {
  $reactions = @(Get-Paged "repos/$Repo/issues/comments/$($request.id)/reactions?per_page=100")
  foreach ($reaction in $reactions) {
    if ((Get-MachineReviewProvider -Login ([string]$reaction.user.login)) -eq 'codex' -and
        $reaction.content -eq '+1' -and $acceptedProviders -contains 'codex') {
      $passes.Add('Codex thumbs-up on exact-head review request')
    }
  }
}

if ($failures.Count -gt 0) {
  Set-AiReviewCheck -HeadSha $headSha -Conclusion failure -Summary ("Material machine-review finding(s): " + ($failures -join '; '))
  exit 0
}
if ($passes.Count -eq 0) {
  Set-AiReviewCheck -HeadSha $headSha -Conclusion failure -Summary ("Awaiting exact-head machine review. Accepted reviewer(s): " + ($acceptedProviders -join ', '))
  exit 0
}

Set-AiReviewCheck -HeadSha $headSha -Conclusion success -Summary ("Exact head $headSha passed machine review: " + (($passes | Select-Object -Unique) -join '; '))
