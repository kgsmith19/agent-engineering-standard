# Verification mold corpus (Stage 29, #120)

Frozen, hand-adjudicated claim-to-evidence bindings for one
implementation slice. Every entry's `expected_rules` (negatives)
must equal the sorted rule set from
`tools/verification_mold.critique(mold)`; positives must validate
with zero findings. `standardctl verification-mold` validates
both sets on every run.

## What a Mold binds

One slice's behavior claims (one observable outcome each, with
failure shape and risk) to evidence tests naming the claims they
cover, the technique used, the oracle, the externally observable
result, what is mocked, and whether internals are reached into.

## Severity semantics

- blocker: binding cannot verify (missing claim evidence,
  mocked subject, unobservable assertion).
- major: weak or coupled evidence to fix (duplicate weak
  evidence, implementation-coupled oracle, overconstrained
  internals).
- minor: reserved; unused by the frozen rules.

## What the negative fixtures reject

A claim with no test (`missing-claim`), two identical-technique
tests with the same observable (`duplicate-weak-evidence`), an
oracle naming storage or library artifacts
(`implementation-coupled-oracle`), a test mocking its own claim
(`mocked-behavior-under-test`), internals views unwarranted by
risk (`overconstrained-internals`), and an assertion of a
private internal (`unobservable-assertion`).
