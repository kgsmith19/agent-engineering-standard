function Get-StandardLockRevisionMatch {
  param([Parameter(Mandatory)][string]$Content)

  $revisionPattern = '(?m)^(?<prefix>[ \t]*(?:sha|commit|standard_commit):[ \t]*)(?<value>[0-9a-fA-F]{40})(?<suffix>[ \t]*(?:#.*)?)$'
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

  $pinnedAtPattern = '(?m)^(?<prefix>[ \t]*pinned_at:[ \t]*)(?<value>[^#\r\n]*?)(?<suffix>[ \t]*(?:#.*)?)$'
  $pinnedAtMatches = [regex]::Matches($updated, $pinnedAtPattern)
  if ($pinnedAtMatches.Count -ne 1) {
    throw "standard.lock must contain exactly one pinned_at field; found $($pinnedAtMatches.Count)."
  }

  $pinnedAtMatch = $pinnedAtMatches[0]
  $pinnedAtReplacement = $pinnedAtMatch.Groups['prefix'].Value + '"' + $PinnedAt + '"' + $pinnedAtMatch.Groups['suffix'].Value
  return $updated.Substring(0, $pinnedAtMatch.Index) + $pinnedAtReplacement + $updated.Substring($pinnedAtMatch.Index + $pinnedAtMatch.Length)
}
