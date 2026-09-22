# SAFE parallelism corpus (Stage 49, #140)

Frozen, hand-adjudicated parallelism proposals. Every entry's
`expected_rule` must equal `tools/safe_parallelism.decide(entry.proposal).rule`
and `expected_verdict` the verdict.
`standardctl safe-parallelism` validates the set on every run.

## What the gate proves

Stage 49 runs parallel autonomy fast only when mutable
independence is mechanically proven — disjoint files, split
schemas, independent outputs, distinct leases:

- `same-files` / `shared-schema` / `dependent-output` —
  SERIALIZE, never parallel.
- `orphan-process` / `unpushed-work` / `closed-unmerged` —
  REFUSE until reconciled.
- `squash-recognized` — SAFE: squash merges recognized.
- `cloud-workspace` / `missing-report` / `classifier-failed`
  — REFUSE: UNKNOWN never defaults SAFE.
- `clean-parallel` — SAFE: proven independence.

## Cleanup policy

Never remove a worktree with an open PR, unpushed commits, or
an active writer. Only explicit SAFE permits parallel
mutation.
