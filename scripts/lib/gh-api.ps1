# Canonical `gh api` helpers shared by every automation script. Consolidated
# under #61: three call sites had silently diverged (two Invoke-GhJson depths,
# one raw-text vs. parsed-object return) and Get-Paged was duplicated
# verbatim across eight files plus a minified inline copy. Depth 20 is chosen
# because every payload in this codebase is written once and only ever
# discarded (`| Out-Null`) or read back as a parsed object — Depth 10 truncated
# nothing observed, but 20 is the safer ceiling for future nested payloads.
# Parsed-object return is chosen because every real call site consumes the
# result as an object (`.id`, property access) or discards it; none depend on
# raw JSON text.

function Invoke-GhJson {
  param([string]$Method,[string]$Endpoint,$Body)
  $tmp = [System.IO.Path]::GetTempFileName()
  try {
    $Body | ConvertTo-Json -Depth 20 | Set-Content $tmp -Encoding utf8 -NoNewline
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
