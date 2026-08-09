function Get-StandardLockRevisionMatch {
  param([Parameter(Mandatory)][string]$Content)

  $revisionPattern = '(?m)^(?<prefix>[ \t]*(?:sha|commit|standard_commit):[ \t]*)(?<value>[0-9a-fA-F]{40})(?<suffix>[ \t]*(?:#.*)?\r?)$'
  $revisionMatches = [regex]::Matches($Content, $revisionPattern)
  if ($revisionMatches.Count -ne 1) {
    throw "standard.lock must contain exactly one sha, commit, or standard_commit field; found $($revisionMatches.Count)."
  }
  return $revisionMatches[0]
}

function Get-StandardLockRevision {
  param([Parameter(Mandatory)][string]$Content)

  return (Get-StandardLockRevisionMatch -Content $Content).Groups['value'].Value
}

function Update-StandardLockContent {
  param(
    [Parameter(Mandatory)][string]$Content,
    [Parameter(Mandatory)][string]$StandardSha,
    [Parameter(Mandatory)][string]$PinnedAt
  )

  if ($StandardSha -notmatch '^[0-9a-fA-F]{40}$') {
    throw 'StandardSha must be a full 40-character commit SHA.'
  }
  if ($PinnedAt -notmatch '^\d{4}-\d{2}-\d{2}$') {
    throw 'PinnedAt must use YYYY-MM-DD.'
  }

  $revision = Get-StandardLockRevisionMatch -Content $Content
  $revisionReplacement = $revision.Groups['prefix'].Value + $StandardSha + $revision.Groups['suffix'].Value
  $updated = $Content.Substring(0, $revision.Index) + $revisionReplacement + $Content.Substring($revision.Index + $revision.Length)

  $pinnedAtPattern = '(?m)^(?<prefix>[ \t]*pinned_at:[ \t]*)(?<value>[^#\r\n]*?)(?<suffix>[ \t]*(?:#.*)?\r?)$'
  $pinnedAtMatches = [regex]::Matches($updated, $pinnedAtPattern)
  if ($pinnedAtMatches.Count -ne 1) {
    throw "standard.lock must contain exactly one pinned_at field; found $($pinnedAtMatches.Count)."
  }

  $pinnedAtMatch = $pinnedAtMatches[0]
  $pinnedAtReplacement = $pinnedAtMatch.Groups['prefix'].Value + '"' + $PinnedAt + '"' + $pinnedAtMatch.Groups['suffix'].Value
  return $updated.Substring(0, $pinnedAtMatch.Index) + $pinnedAtReplacement + $updated.Substring($pinnedAtMatch.Index + $pinnedAtMatch.Length)
}

function Update-StandardProjectContent {
  param(
    [Parameter(Mandatory)][string]$Content,
    [Parameter(Mandatory)][string]$PreviousStandardSha,
    [Parameter(Mandatory)][string]$StandardSha
  )

  foreach ($candidate in @($PreviousStandardSha, $StandardSha)) {
    if ($candidate -notmatch '^[0-9a-fA-F]{40}$') {
      throw 'Project standard revisions must be full 40-character commit SHAs.'
    }
  }

  $escapedPreviousSha = [regex]::Escape($PreviousStandardSha)
  $pattern = "(?m)^(?<prefix>\s*(?:sha|standard_sha|standard_commit|commit):\s*)$escapedPreviousSha(?<suffix>\s*(?:#.*)?\r?)$"
  $matches = [regex]::Matches($Content, $pattern)
  if ($matches.Count -gt 1) {
    throw "project.yaml contains more than one reference to the previous standard revision; found $($matches.Count)."
  }
  if ($matches.Count -eq 0) { return $Content }

  $match = $matches[0]
  $replacement = $match.Groups['prefix'].Value + $StandardSha + $match.Groups['suffix'].Value
  return $Content.Substring(0, $match.Index) + $replacement + $Content.Substring($match.Index + $match.Length)
}

function Update-ProjectWorkTrackingContent {
  param(
    [Parameter(Mandatory)][AllowEmptyString()][string]$Content,
    [Parameter(Mandatory)][string]$ProjectTitle
  )

  if ([string]::IsNullOrWhiteSpace($ProjectTitle) -or $ProjectTitle -match '[\r\n"]') {
    throw 'ProjectTitle must be a non-empty single-line value without double quotes.'
  }

  $newline = if ($Content.Contains("`r`n")) { "`r`n" } else { "`n" }
  $desired = [ordered]@{
    system = 'github-projects'
    project = '"' + $ProjectTitle + '"'
    backing_record = 'github-issues'
  }

  $blockPattern = '(?ms)^(?<header>work_tracking:[ \t]*(?:#.*)?\r?\n)(?<body>(?:[ \t]+[^\r\n]*(?:\r?\n|$))*)'
  $block = [regex]::Match($Content, $blockPattern)
  if (-not $block.Success) {
    $prefix = $Content
    if ($prefix.Length -gt 0 -and -not ($prefix.EndsWith("`n") -or $prefix.EndsWith("`r"))) { $prefix += $newline }
    if ($prefix.Length -gt 0 -and -not $prefix.EndsWith($newline + $newline)) { $prefix += $newline }
    $body = @($desired.GetEnumerator() | ForEach-Object { "  $($_.Key): $($_.Value)" }) -join $newline
    return $prefix + 'work_tracking:' + $newline + $body + $newline
  }

  $body = $block.Groups['body'].Value
  foreach ($entry in $desired.GetEnumerator()) {
    $keyPattern = "(?m)^(?<prefix>[ \t]+$([regex]::Escape($entry.Key)):[ \t]*)(?<value>[^#\r\n]*?)(?<suffix>[ \t]*(?:#.*)?\r?)$"
    $matches = [regex]::Matches($body, $keyPattern)
    if ($matches.Count -gt 1) { throw "project.yaml work_tracking contains duplicate '$($entry.Key)' fields." }
    if ($matches.Count -eq 1) {
      $match = $matches[0]
      $replacement = $match.Groups['prefix'].Value + $entry.Value + $match.Groups['suffix'].Value
      $body = $body.Substring(0, $match.Index) + $replacement + $body.Substring($match.Index + $match.Length)
    }
    else {
      if ($body.Length -gt 0 -and -not $body.EndsWith("`n")) { $body += $newline }
      $body += "  $($entry.Key): $($entry.Value)$newline"
    }
  }

  $replacementBlock = $block.Groups['header'].Value + $body
  return $Content.Substring(0, $block.Index) + $replacementBlock + $Content.Substring($block.Index + $block.Length)
}
