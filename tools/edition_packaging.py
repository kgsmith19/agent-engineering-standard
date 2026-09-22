"""T10 Standard half: edition UX and Premium packaging with release VERIFY.

Full packages everything (today plus all delivered amendment
features, no silently dropped capability); lite is the safety
net (thin issues, atomic claim, policy/lint/unit gate, ready
PRs, basic evidence — without R2/R3 extras, strict review
separation, mutation/fuzz/e2e/property, continuity governor, or
deep evidence). Lite omits llm_review entirely (deleted from
needs/EXPECTED_JOBS, never stubbed; verify skips the separation
check under lite, reported as skipped). init/doctor are
edition-seamless (sensible edition:/flags: starter, redacted
status, keyless = today). Release VERIFY runs green for both
editions at the exact head with the PR Gate green on the same
SHA. Any deferral from Full scope is explicit and
owner-approved, never a quiet omission.

Pure functions: no I/O, no network — data in, violations out.
Frozen rules, stable output order.
"""

from typing import Any, Dict, List, Optional, Set, Tuple

# Full runs everything; lite runs the safety net only. Frozen
# lite-off set mirrors EDITION_LITE_OFF in standardctl.
LITE_OFF = ("llm_review_strict", "extensions_catalog")

# Safety-net checks that MUST run under lite.
LITE_REQUIRED = (
    "check_template_pairs",
    "check_harness_edition",
    "check_gate_aggregator",
    "check_gate_noop_stages",
)

# Deep-evidence checks that MUST NOT run under lite.
LITE_FORBIDDEN = (
    "check_review_always_comments",
    "check_no_native_review_gating",
    "check_capability_registry",
)


def check_full_completeness(running: Any, known: Any) -> List[str]:
    """Return violations when full drops a capability.

    Under edition full, every known check runs: a full run
    missing any known check fails naming the drop, so no
    capability is silently dropped from Full scope.
    """
    violations: List[str] = []
    running_set = set(running) if isinstance(running, list) else set()
    known_list = list(known) if isinstance(known, list) else []
    for name in known_list:
        if name not in running_set:
            violations.append(
                "full drops capability %r: full packages "
                "everything, no silently dropped capability"
                % (name,))
    return violations


def check_lite_safety_net(running: Any) -> List[str]:
    """Return violations when lite misses safety-net coverage.

    Under edition lite, every LITE_REQUIRED check runs and no
    LITE_FORBIDDEN check runs; a missing safety-net check or a
    present deep check fails naming the check.
    """
    violations: List[str] = []
    running_set = set(running) if isinstance(running, list) else set()
    for name in LITE_REQUIRED:
        if name not in running_set:
            violations.append(
                "lite misses safety-net check %r" % (name,))
    for name in LITE_FORBIDDEN:
        if name in running_set:
            violations.append(
                "lite runs deep-evidence check %r: R2/R3 extras "
                "do not run under lite" % (name,))
    return violations


def check_lite_omits_review(render: Any) -> List[str]:
    """Return violations when lite keeps any llm_review trace.

    The llm_review gate job is absent from the lite render's
    needs and EXPECTED_JOBS (deleted, never stubbed); any stub
    entry or surviving reference fails naming it.
    """
    violations: List[str] = []
    if not isinstance(render, dict):
        return ["lite render must be a mapping"]
    for key in ("needs", "expected_jobs"):
        jobs = render.get(key) or []
        for job in jobs:
            if "llm_review" in str(job):
                violations.append(
                    "lite render keeps %r in %s: delete, never "
                    "stub" % (job, key))
    for stub in render.get("stubs") or []:
        violations.append(
            "lite render stubs %r: delete, never stub" % (stub,))
    return violations


def check_explicit_deferral(deferrals: Any) -> List[str]:
    """Return violations for quiet omissions from Full scope.

    Every deferral names the capability and its owner approval;
    a deferral without approval fails, so no capability is ever
    quietly omitted (plan W6 rule).
    """
    violations: List[str] = []
    if not isinstance(deferrals, list):
        return ["deferrals must be a list"]
    for item in deferrals:
        if not isinstance(item, dict):
            violations.append("deferral must be a mapping: %r"
                              % (item,))
            continue
        if not item.get("capability"):
            violations.append("deferral names no capability")
        if not item.get("owner_approved"):
            violations.append(
                "deferral of %r lacks owner approval: quiet "
                "omissions forbidden" % (
                    item.get("capability", "?"),))
    return violations


def check_verify_receipt(receipt: Any) -> List[str]:
    """Return violations for an incomplete release VERIFY receipt.

    The receipt records both editions' verify runs green at the
    exact head with the PR Gate green on the same SHA: commands,
    editions, and heads all present and consistent. A missing leg
    or a head mismatch fails naming the gap.
    """
    violations: List[str] = []
    if not isinstance(receipt, dict):
        return ["verify receipt must be a mapping"]
    for edition in ("full", "lite"):
        leg = receipt.get(edition)
        if not isinstance(leg, dict):
            violations.append(
                "verify receipt missing %r leg" % (edition,))
            continue
        if leg.get("result") != "pass":
            violations.append(
                "verify receipt %r leg is not green" % (edition,))
        if not leg.get("head"):
            violations.append(
                "verify receipt %r leg names no head" % (edition,))
    full = receipt.get("full") or {}
    lite = receipt.get("lite") or {}
    if (isinstance(full, dict) and isinstance(lite, dict)
            and full.get("head") and lite.get("head")
            and full.get("head") != lite.get("head")):
        violations.append(
            "verify receipt head mismatch: full %r != lite %r" % (
                full.get("head"), lite.get("head")))
    if receipt.get("gate") != "pass":
        violations.append(
            "verify receipt needs the PR Gate green on the same "
            "SHA")
    if receipt.get("head") and isinstance(full, dict) and full.get(
            "head") and receipt.get("head") != full.get("head"):
        violations.append(
            "verify receipt head %r != full-leg head %r" % (
                receipt.get("head"), full.get("head")))
    return violations


def check_stale_sha_refusal(tested: Any, head: Any) -> List[str]:
    """Return violations when a stale SHA would be accepted.

    Tested SHA != PR head refuses with both named; equality
    passes. The VERIFY path never gates a moved head.
    """
    if str(tested) != str(head):
        return ["stale SHA refused: tested %r != head %r" % (
            tested, head)]
    return []


def validate_edition_corpus(corpus: Any) -> Tuple[List[str], List[Any]]:
    """Validate the frozen edition-UX fixture oracle.

    Returns (findings, entries). Every entry carries an id, a
    target surface (full, lite, review, deferral, receipt,
    stale), a record, and the expected violation fragment (""
    means clean). Full entries carry known alongside record;
    receipt/stale entries use record dicts.
    """
    if not isinstance(corpus, dict):
        return (["edition corpus must be a mapping"], [])
    if corpus.get("_frozen") is not True:
        return (["edition corpus is not frozen: set "
                 "\"_frozen\": true"], [])
    entries = corpus.get("entries")
    if not isinstance(entries, list):
        return (["edition corpus entries must be a list"], [])
    findings: List[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            findings.append("corpus entry is not a mapping: %r"
                            % (entry,))
            continue
        entry_id = entry.get("id", "?")
        target = entry.get("target")
        record = entry.get("record")
        expected = entry.get("expected_violation_fragment", "")
        if target == "full":
            violations = check_full_completeness(
                record, entry.get("known", []))
        elif target == "lite":
            violations = check_lite_safety_net(record)
        elif target == "review":
            violations = check_lite_omits_review(record)
        elif target == "deferral":
            violations = check_explicit_deferral(record)
        elif target == "receipt":
            violations = check_verify_receipt(record)
        elif target == "stale":
            violations = check_stale_sha_refusal(
                (record or {}).get("tested"),
                (record or {}).get("head"))
        else:
            findings.append(
                "entry %s has unknown target %r" % (entry_id, target))
            continue
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
