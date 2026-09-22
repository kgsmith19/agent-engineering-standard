# Writer lease corpus (Stage 46, #137)

Frozen, hand-adjudicated lease operations. Every entry's
`expected_rule` must equal `tools/writer_lease.decide(entry.operation).rule`
and `expected_verdict` the verdict.
`standardctl writer-lease` validates the set on every run.

## What the lease proves

Stage 46 keeps one mutable writer per slice across provider,
process, host, and context changes with fencing-generation CAS:

- `concurrent-claim` — second claimants refuse (blocker).
- `stale-generation` — old generations fence (blocker).
- `expired-lease` — dead heartbeats re-acquire via CAS.
- `late-heartbeat` — only the current generation heartbeats.
- `provider-transfer` — moves transfer forward explicitly
  (GRANT on transfer, REFUSE without).
- `workspace-lost` / `partition-split` / `process-dead` —
  RECOVER via reconcile, never silent takeover.
- `owner-recovery` — explicit owner release only; no silent
  override.
- `clean-release` — holder release frees the slice.
- `no-lease` — clean GRANT anchor (and required-lease guard).

## No central service

Git/GitHub branch/commit/report state plus the CAS record is
the coordinator. Read-only agents never hold a lease.
