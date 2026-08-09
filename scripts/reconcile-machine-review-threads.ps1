param(
  [Parameter(Mandatory)][string]$Repo,
  [Parameter(Mandatory)][int]$Pr,
  [string]$HeadSha = ''
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib/review-policy.ps1')

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw 'GitHub CLI (gh) is required.' }
$parts = $Repo -split '/',2
if ($parts.Count -ne 2) { throw 'Repo must be owner/name.' }
$owner = $parts[0]
$name = $parts[1]

if (-not $HeadSha) {
  $prRaw = & gh api "repos/$Repo/pulls/$Pr" 2>&1
  if ($LASTEXITCODE -ne 0) { throw ($prRaw -join "`n") }
  $HeadSha = [string](($prRaw -join "`n") | ConvertFrom-Json).head.sha
}

$encoded = [uri]::EscapeDataString('AI Review')
$checkRaw = & gh api -H 'Accept: application/vnd.github+json' "repos/$Repo/commits/$HeadSha/check-runs?check_name=$encoded" 2>&1
if ($LASTEXITCODE -ne 0) { throw ($checkRaw -join "`n") }
$checks = (($checkRaw -join "`n") | ConvertFrom-Json).check_runs
$latest = @($checks | Where-Object { $_.name -eq 'AI Review' -and $_.app.slug -eq 'github-actions' } | Sort-Object id | Select-Object -Last 1)
if ($latest.Count -eq 0 -or $latest[0].conclusion -ne 'success') {
  Write-Host "MACHINE THREAD RECONCILIATION: skipped; AI Review is not successful for $HeadSha"
  exit 0
}

$query = @'
query($owner:String!, $name:String!, $number:Int!, $after:String) {
  repository(owner:$owner, name:$name) {
    pullRequest(number:$number) {
      reviewThreads(first:100, after:$after) {
        nodes {
          id
          isResolved
          comments(first:100) {
            nodes {
              author { login }
              pullRequestReview { commit { oid } }
            }
          }
        }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
'@
$mutation = @'
mutation($threadId:ID!) {
  resolveReviewThread(input:{threadId:$threadId}) {
    thread { id isResolved }
  }
}
'@

$after = $null
$resolved = 0
$kept = 0

do {
  $args = @('api','graphql','-f',"query=$query",'-F',"owner=$owner",'-F',"name=$name",'-F',"number=$Pr")
  if ($after) { $args += @('-f',"after=$after") }
  $raw = & gh @args 2>&1
  if ($LASTEXITCODE -ne 0) { throw ($raw -join "`n") }
  $threads = (($raw -join "`n") | ConvertFrom-Json).data.repository.pullRequest.reviewThreads

  foreach ($thread in @($threads.nodes)) {
    if ([bool]$thread.isResolved) { continue }
    $comments = @($thread.comments.nodes)
    if ($comments.Count -eq 0) { $kept++; continue }

    $nonMachine = @($comments | Where-Object {
      -not (Get-MachineReviewProvider -Login ([string]$_.author.login))
    })
    $currentHead = @($comments | Where-Object {
      [string]$_.pullRequestReview.commit.oid -eq $HeadSha
    })
    if ($nonMachine.Count -gt 0 -or $currentHead.Count -gt 0) {
      $kept++
      continue
    }

    $mutationRaw = & gh api graphql -f "query=$mutation" -f "threadId=$($thread.id)" 2>&1
    if ($LASTEXITCODE -ne 0) { throw ($mutationRaw -join "`n") }
    $resolved++
  }

  $after = if ([bool]$threads.pageInfo.hasNextPage) { [string]$threads.pageInfo.endCursor } else { $null }
} while ($after)

Write-Host "MACHINE THREAD RECONCILIATION: resolved=$resolved kept=$kept head=$HeadSha" -ForegroundColor Green
