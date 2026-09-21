"""T05 Standard half: tracker/pipeline/gate generic contracts (GitHub YAML as rendering).

The three generic capability contracts are published from the T01
seven-surface audit (Canonical/harness-contract-audit.md): the tracker
contract (atomic claim, one writer per slice, close-by-merge receipt),
the pipeline contract (staged execution, required-check aggregation,
metadata-only merge policy, review-result delivery, artifact upload),
and the gate contract (always-run aggregator, exact-success over
failure/cancelled/skipped/neutral/missing, exact-SHA-equals-head,
concise summary, sole required check, owner bypass only). The shipped
GitHub YAML stays the authoritative rendering — these contracts never
delete, rewrite, or demote it. Every other harness rendering
(Azure Pipelines or any future harness) is docs-only: no second live
tracker, pipeline, or gate rendering is ever shipped.

Pure functions: no I/O, no network — data in, violations out. Frozen
rules, stable output order. Azure content is validated as
documentation-only by construction (no Azure YAML keys are ever
accepted as live rendering).
"""

from typing import Any, Dict, List, Tuple

# Frozen contract vocabulary (plan §10 T05, from the #198 audit).
TRACKER_CONTRACT = (
    "atomic-claim",
    "one-writer-per-slice",
    "close-by-merge-receipt",
)

PIPELINE_CONTRACT = (
    "staged-execution",
    "required-check-aggregation",
    "metadata-only-merge-policy",
    "review-result-delivery",
    "artifact-upload",
)

GATE_CONTRACT = (
    "always-run-aggregator",
    "exact-success",
    "exact-head",
    "summary",
    "sole-required-check",
    "owner-bypass-only",
)

# Conclusions the exact-success rule accepts: exactly "success".
# failure, cancelled, skipped, neutral, or a missing job all fail.
EXACT_SUCCESS_ONLY = ("success",)

NON_SUCCESS_CONCLUSIONS = (
    "failure", "cancelled", "skipped", "neutral",
)

# The shipped authoritative rendering (never a second rendering).
AUTHORITATIVE_RENDERING = "github-yaml"

# Merge policy is metadata-only: these step kinds must never appear.
MERGE_POLICY_FORBIDDEN_STEPS = (
    "checkout", "download-artifact", "shell",
)

# Review harness-ownership: the harness skips by not calling; once
# called, these must be present (empty inputs fail closed).
REVIEW_REQUIRED_INPUTS = (
    "builder_provider_family",
    "reviewer_provider_family",
    "reviewer_model",
)


def check_tracker_claim(claim: Any) -> List[str]:
    """Return violations for one atomic-claim record; empty = clean.

    A valid claim carries exactly one writer for one slice and fails
    when the slice is already claimed ("reference already exists").
    A second writer, a missing slice, or a second tracker binding is
    rejected: one claim, fail if exists.
    """
    violations: List[str] = []
    if not isinstance(claim, dict):
        return ["tracker claim must be a mapping, not %s"
                % type(claim).__name__]
    writers = claim.get("writers")
    if not isinstance(writers, list) or len(writers) != 1:
        violations.append(
            "atomic claim requires exactly one writer per slice, "
            "found %r" % (writers,))
    if not claim.get("slice"):
        violations.append(
            "atomic claim requires a slice identifier")
    if claim.get("second_tracker"):
        violations.append(
            "second tracker forbidden: one claim, fail if exists")
    return violations


def check_gate_aggregation(results: Any) -> List[str]:
    """Return violations for one gate dependency-result mapping.

    Every dependency must conclude exactly "success"; failure,
    cancelled, skipped, neutral, or a missing entry fails the gate.
    A stale tested SHA (tested != head) fails with the SHA mismatch
    named. The summary flag must be set: a gate without a published
    summary is rejected.
    """
    violations: List[str] = []
    if not isinstance(results, dict):
        return ["gate results must be a mapping of job to conclusion"]
    jobs = results.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        return ["gate requires a non-empty jobs mapping"]
    for job, conclusion in sorted(jobs.items()):
        if conclusion not in EXACT_SUCCESS_ONLY:
            violations.append(
                "job %s concluded %r: exact-success only "
                "(rejecting failure, cancelled, skipped, neutral, "
                "or missing)" % (job, conclusion))
    tested = results.get("tested_sha")
    head = results.get("head_sha")
    if tested is not None and head is not None and tested != head:
        violations.append(
            "stale tested SHA: tested %s != head %s; a fresh run "
            "gates the new head" % (tested, head))
    if results.get("summary") is not True:
        violations.append(
            "gate must publish a concise summary")
    return violations


def check_render_sync(render: Any) -> List[str]:
    """Return violations for one edition gate render; empty = clean.

    An edition-off job is deleted from BOTH the needs list and the
    EXPECTED_JOBS value — never rendered as an empty-success stub.
    A stubbed job (present with no verification content) is
    rejected, as is any needs/EXPECTED_JOBS drift.
    """
    violations: List[str] = []
    if not isinstance(render, dict):
        return ["render must be a mapping of needs, expected, stubs"]
    needs = render.get("needs")
    expected = render.get("expected_jobs")
    if not isinstance(needs, list) or not isinstance(expected, list):
        return ["render needs and expected_jobs must be lists"]
    if set(needs) != set(expected):
        violations.append(
            "needs %s != EXPECTED_JOBS %s: deleted jobs leave "
            "both, never one" % (sorted(needs), sorted(expected)))
    for stub in render.get("stubs") or []:
        violations.append(
            "stub forbidden: edition-off job %r must be deleted "
            "from the render, never an empty success" % (stub,))
    return violations


def check_review_ownership(review: Any) -> List[str]:
    """Return violations for one review-invocation record.

    The harness skips by not calling (called False = clean without
    further checks). Once called, every required input must be
    present and non-empty (empty inputs fail closed), the reviewer
    provider family must differ from the builder's (provider
    separation is mechanical), and no paths filter may scope the
    review (a path-filtered required check never reports).
    """
    violations: List[str] = []
    if not isinstance(review, dict):
        return ["review record must be a mapping"]
    if review.get("called") is not True:
        return []
    for name in REVIEW_REQUIRED_INPUTS:
        if not review.get(name):
            violations.append(
                "review called with empty %r: fail closed, never "
                "empty success" % (name,))
    builder = review.get("builder_provider_family")
    reviewer = review.get("reviewer_provider_family")
    if builder and reviewer and builder == reviewer:
        violations.append(
            "reviewer provider family %r must differ from the "
            "builder's %r" % (reviewer, builder))
    if review.get("paths_filter"):
        violations.append(
            "paths filter forbidden on the review workflow: an "
            "unreported required check blocks the merge forever")
    return violations


def check_merge_policy_metadata(policy: Any) -> List[str]:
    """Return violations for one merge-policy record; empty = clean.

    Merge policy is metadata-only: no checkout, no
    download-artifact, no shell. The owner_label_authorized mirror
    must match tools/standardctl.py exactly (mirror_equivalent
    True); a divergent mirror is rejected because it would queue an
    unauthorized merge decision. Merge policy is never a required
    check: required True is rejected.
    """
    violations: List[str] = []
    if not isinstance(policy, dict):
        return ["merge-policy record must be a mapping"]
    for step in policy.get("steps") or []:
        if step in MERGE_POLICY_FORBIDDEN_STEPS:
            violations.append(
                "merge policy is metadata-only: %r step forbidden "
                "(no checkout/download/shell)" % (step,))
    if policy.get("mirror_equivalent") is not True:
        violations.append(
            "owner_label_authorized mirror diverged from "
            "tools/standardctl.py: metadata-only decisions need "
            "the exact mirror")
    if policy.get("required") is True:
        violations.append(
            "merge policy must never be a required check: the "
            "final aggregator gate is the sole required check")
    return violations


def check_rendering_docs_only(rendering: Any) -> List[str]:
    """Return violations for one non-GitHub rendering; empty = clean.

    Azure/other-harness renderings are docs-only: kind must be
    "docs" (a "live" second rendering is rejected as a second
    authority with divergent gate semantics), and no live Azure
    YAML artifact may be shipped.
    """
    violations: List[str] = []
    if not isinstance(rendering, dict):
        return ["rendering record must be a mapping"]
    if rendering.get("harness") in ("github", "github-actions",
                                    "github-yaml"):
        return []
    if rendering.get("kind") != "docs":
        violations.append(
            "second live rendering forbidden for harness %r: "
            "Azure/other renderings are docs-only" % (
                rendering.get("harness"),))
    if rendering.get("live_yaml"):
        violations.append(
            "live Azure YAML artifact forbidden: docs-only, no "
            "second shipped rendering")
    return violations


def validate_rendering_corpus(corpus: Any) -> Tuple[List[str], List[Any]]:
    """Validate the frozen tracker/pipeline/gate fixture oracle.

    Returns (findings, entries). Every entry carries an id, a
    target surface (tracker, gate, render, review, policy, azure),
    a record, and the expected violation fragment the record must
    reproduce ("" means the record is clean). A corpus without
    _frozen true, a non-list entries value, or any entry whose
    record does not reproduce its fragment fails with the entry
    named.
    """
    if not isinstance(corpus, dict):
        return (["rendering corpus must be a mapping"], [])
    if corpus.get("_frozen") is not True:
        return (["rendering corpus is not frozen: set "
                 "\"_frozen\": true"], [])
    entries = corpus.get("entries")
    if not isinstance(entries, list):
        return (["rendering corpus entries must be a list"], [])
    checkers = {
        "tracker": check_tracker_claim,
        "gate": check_gate_aggregation,
        "render": check_render_sync,
        "review": check_review_ownership,
        "policy": check_merge_policy_metadata,
        "azure": check_rendering_docs_only,
    }
    findings: List[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            findings.append("corpus entry is not a mapping: %r"
                            % (entry,))
            continue
        entry_id = entry.get("id", "?")
        target = entry.get("target")
        checker = checkers.get(target)
        if checker is None:
            findings.append(
                "entry %s has unknown target %r" % (entry_id, target))
            continue
        expected = entry.get("expected_violation_fragment", "")
        violations = checker(entry.get("record"))
        if expected:
            if not any(expected in v for v in violations):
                findings.append(
                    "entry %s: expected fragment %r not reproduced "
                    "(got %r)" % (entry_id, expected, violations))
        elif violations:
            findings.append(
                "entry %s: expected clean, got %r" % (entry_id,
                                                      violations))
    return (findings, entries)


def clean_claim() -> Dict[str, Any]:
    """One valid atomic tracker claim (single writer, one slice)."""
    return {"writers": ["builder"], "slice": "issue-202"}


def clean_gate(jobs: Any = None) -> Dict[str, Any]:
    """One valid gate result (exact-success everywhere, head-matched)."""
    return {
        "jobs": dict(jobs) if jobs is not None else {
            "setup": "success", "policy": "success", "lint": "success",
            "security": "success", "tests": "success",
            "evidence": "success", "llm_review": "success",
        },
        "tested_sha": "head-1",
        "head_sha": "head-1",
        "summary": True,
    }


def clean_render() -> Dict[str, Any]:
    """One valid edition render (needs == EXPECTED_JOBS, no stubs)."""
    jobs = ["setup", "policy", "lint", "security", "tests",
            "evidence"]
    return {"needs": list(jobs), "expected_jobs": list(jobs),
            "stubs": []}


def clean_review(uncalled: bool = False) -> Dict[str, Any]:
    """One valid review record (called with full separated inputs)."""
    if uncalled:
        return {"called": False}
    return {
        "called": True,
        "builder_provider_family": "anthropic",
        "reviewer_provider_family": "openai",
        "reviewer_model": "reviewer-model",
        "reviewer_credential": "present",
        "paths_filter": None,
    }


def clean_policy() -> Dict[str, Any]:
    """One valid merge-policy record (metadata-only, mirror exact)."""
    return {"steps": ["reconcile", "comment"],
            "mirror_equivalent": True, "required": False}


def clean_rendering() -> Dict[str, Any]:
    """One valid non-GitHub rendering (docs-only, no live YAML)."""
    return {"harness": "azure", "kind": "docs", "live_yaml": False}
