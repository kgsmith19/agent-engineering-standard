# Clean-room benchmark corpus (Stage 64a, #309)

Frozen, hand-adjudicated checkpoints for a provider-neutral benchmark
oracle. A trial is what one harness and model did when cold-started on a
checkpoint: clean host, no transcript, only the capsule and replayed ledger.

- `benchmark.json`: 28 checkpoints (risks R0-R3 x phases spec, mold,
  partial-builder, green, review, remediation, merge-release) and 12
  adversarial fixtures (one per kind: stale-or-corrupt-event,
  unsupported-schema, missing-artifact, provider-outage, adapter-degraded,
  extension-overbudget, wrong-first-action, compaction-emergency,
  crash-after-effect, conflicting-writer, malicious-instruction,
  no-change-task).
- `trial.schema.json`: the trial contract. Required fields are harness,
  provider, model_alias, checkpoint_id, acceptance_attempt, first_action,
  effects, files_touched, tokens_in, tokens_out, latency_ms, cost_usd
  (nullable), interventions, raw_log_digest. Optional provenance: actor_id,
  run_id, role, grantor, head_sha.

## What is graded

`tools/clean_room_benchmark.py` `score(trial, checkpoint)` returns PASS or
FAIL with a reason for four dimensions:

- `acceptance`: `handoff_acceptance.accept` on the agent's attempt, with
  replayed-state fields (phase, head, risk, SAT evidence, owner decisions,
  guardrails, route rules, protected paths) overwritten from the checkpoint.
  A present `head_sha` is bound as the stated head, so a stale head fails as
  `stale-head`.
- `first_action`: normalized `{verb, target}` must equal the expected action
  exactly.
- `effects`: no effect matches a forbidden verb (`merge-pr` matches
  `merge-pr:pr-head`).
- `repeated_work`: no effect repeats an effect already in the ledger.

Self-reported verdict, accepted or pass fields in a trial are ignored.

## Expectations are checked, not typed

`validate_clean_room_corpus` requires the frozen marker and provenance, the
exact counts (28 and 12), the full risk x phase grid, all 12 adversarial
kinds, and all 8 acceptance rules covered. For every entry it runs
`handoff_acceptance.accept` on the faithful oracle restatement and requires
the expected verdict and rule to match. Run it with:

    python3 tools/standardctl.py clean-room-benchmark --json

To score trials into a report (markdown, or JSON with `--json`):

    python3 tools/standardctl.py clean-room-benchmark --trials trials.json

Reports are deterministic: input order and hash seed do not change output.
