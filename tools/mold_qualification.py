"""Stage 31 Standard half: mold qualification gate with digest-bound receipts.

A Verification Mold earns trust only by proving its tests reject
untrustworthy evidence before implementation is authorized: each
test names the claims it evidences, whether it asserts an
externally observable result, and a set of frozen boolean flags
describing how it could cheat (hard-coded example, omitted
state, swallowed error, mock-only assertion, setup
self-assertion, structural failure, equivalent mutant, valid
alternative accepted, coverage kind). The gate is load-bearing
for Stage 31 (Risk R3): it authorizes production implementation
to begin, so a defect lets an untrustworthy Mold pass and
silently corrupt every downstream evidence claim.

Run shape (plain data; missing keys fall back to total defaults,
never a crash)::

    {"mold": str,                        # mold name
     "mold_digest": str,                # sha256 hex of the Mold payload
     "risk": "R0"|"R1"|"R2"|"R3",
     "tests": [{"id": str, "claims": [str, ...],
                "status": "passed"|"failed"|"skipped"|"filtered"|"error",
                "red_reason": str,
                "asserts_observable": bool,
                "swallows_errors": bool,
                "asserts_mock_only": bool,
                "asserts_setup_state": bool,
                "hard_codes_example": bool,
                "omits_relevant_state": bool,
                "is_structural_failure": bool,
                "is_equivalent_mutant": bool,
                "alternative_impl_ok": bool,
                "coverage_kind": "full"|"empty"|"placeholder"}, ...],
     "provider": str,                    # executing provider label
     "head": str}                        # exact head the run executed at

Deterministic rejection rules (frozen precedence, first listed
first checked; findings appended in this order, so output order
is stable). Every finding names the offending test id:

1. ``skipped_or_filtered`` — a test with ``status`` skipped or
   filtered never qualifies (no empty-green) -> blocker.
2. ``empty_or_placeholder`` — a test with ``coverage_kind``
   empty or placeholder never qualifies -> blocker.
3. ``hard_coded_example`` — asserts one literal example with no
   variation or boundary -> blocker.
4. ``omitted_state`` — leaves a failure-shape-relevant
   dimension unexercised -> blocker.
5. ``swallowed_error`` — try/except-pass around the behavior
   under test hides failures -> blocker.
6. ``mock_only_assertion`` — asserts only mock state, never the
   real subject -> blocker.
7. ``setup_self_assertion`` — asserts state the fixture itself
   just wrote -> blocker.
8. ``structural_failure_not_red`` — a failed test with
   ``is_structural_failure`` true is an import error or fixture
   crash, never RED-for-the-right-reason -> blocker.
9. ``equivalent_mutant`` — the oracle cannot distinguish the
   mutant from the reference -> blocker.
10. ``no_alternative_acceptance`` — no test carries
    ``alternative_impl_ok`` true on an R2/R3 mold, so nothing
    proves the oracle accepts a genuinely valid alternative
    implementation -> blocker.
11. ``no_true_red`` — no test carries ``status`` failed with a
    non-empty ``red_reason`` and ``is_structural_failure``
    false, so RED-for-the-right-reason was never shown ->
    blocker.

Flag semantics (frozen): each boolean flag defaults to False
except ``asserts_observable`` (defaults True); a missing flag
is the honest value, never a crash. ``alternative_impl_ok``
counts only on a test that trips no other rule — a cheating
test that also accepts an alternative proves nothing. Risk
defaults to R1 when unknown; only R2/R3 require alternative
acceptance, because only they authorize production work.

Receipts bind the verdict to the exact Mold and run:
``issue_receipt`` mints ``("mold", "mold_digest", "head",
"provider", "verdict", "run_digest", "qualified_by")`` where
``run_digest`` is the sha256 hex of the canonical JSON of the
normalized run (stdlib ``json.dumps`` with ``sort_keys=True``
encoded as UTF-8, so key order and whitespace are fixed and the
same run always hashes the same). ``verify_receipt`` recomputes
that digest and compares, and reports mold_digest and head
mismatches. The digest binding IS the trust mechanism at this
stage — there are no signatures or keys, by explicit decision;
a signed variant is a later-stage concern.

Findings are repair guidance (what to fix, with an excerpt),
never an error: ``FINDING_FIELDS`` names the five required keys,
``SEVERITIES`` names the allowed severities, and
``validate_finding`` returns repair strings (empty means valid).
``qualify`` is a pure function of its input (no I/O anywhere):
the same run always yields the same verdict and receipt.
``validate_adversarial`` checks the frozen rejection/acceptance
fixture oracle.

This module consumes runs as plain data and performs no
filesystem access itself.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

RISKS = ("R0", "R1", "R2", "R3")

FINDING_FIELDS = ("id", "rule", "finding", "severity", "excerpt")

SEVERITIES = ("blocker", "major", "minor")

RULES = (
    "skipped_or_filtered",
    "empty_or_placeholder",
    "hard_coded_example",
    "omitted_state",
    "swallowed_error",
    "mock_only_assertion",
    "setup_self_assertion",
    "structural_failure_not_red",
    "equivalent_mutant",
    "no_alternative_acceptance",
    "no_true_red",
)

ABSOLUTE_STATUSES = ("skipped", "filtered")

ABSOLUTE_COVERAGES = ("empty", "placeholder")

REQUIRES_ALTERNATIVE_RISKS = ("R2", "R3")

RECEIPT_FIELDS = ("mold", "mold_digest", "head", "provider",
                  "verdict", "run_digest", "qualified_by")

QUALIFIED_BY = "mold_qualification.qualify"

STATUSES = ("passed", "failed", "skipped", "filtered", "error")

COVERAGE_KINDS = ("full", "empty", "placeholder")

DEFAULT_TEST: Dict[str, Any] = {
    "id": "",
    "claims": [],
    "status": "passed",
    "red_reason": "",
    "asserts_observable": True,
    "swallows_errors": False,
    "asserts_mock_only": False,
    "asserts_setup_state": False,
    "hard_codes_example": False,
    "omits_relevant_state": False,
    "is_structural_failure": False,
    "is_equivalent_mutant": False,
    "alternative_impl_ok": False,
    "coverage_kind": "full",
}

DEFAULT_RUN: Dict[str, Any] = {
    "mold": "",
    "mold_digest": "",
    "risk": "R1",
    "tests": [],
    "provider": "",
    "head": "",
}

_ENTRY_ID_RE = re.compile(r"^mold-qual\.[a-z-]+\.\d{2}$")


@dataclass
class QualifyResult:
    """One mold qualification outcome for one qualification run."""

    verdict: str = "rejected"
    receipt: Optional[Dict[str, Any]] = None
    findings: List[Dict[str, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.verdict == "qualified" and not any(
            f.get("severity") == "blocker" for f in self.findings)


def _make_finding(rule: str, message: str, excerpt: str,
                  severity: str = "blocker") -> Dict[str, str]:
    """Build one structured finding dict for a rejected run."""
    return {
        "id": "%s-1" % rule,
        "rule": rule,
        "finding": message,
        "severity": severity,
        "excerpt": excerpt[:200],
    }


def validate_finding(finding: Any) -> List[str]:
    """Return repair strings for one finding; empty means valid."""
    if not isinstance(finding, dict):
        return ["finding must be a mapping of plain data, not %s"
                % type(finding).__name__]
    repairs: List[str] = []
    for field_name in FINDING_FIELDS:
        if field_name not in finding:
            repairs.append("missing field %r: add it to the finding"
                           % field_name)
        elif not str(finding[field_name]).strip():
            repairs.append("field %r must be a non-empty string"
                           % field_name)
    for key in finding:
        if key not in FINDING_FIELDS:
            repairs.append("unknown field %r: remove it from the finding"
                           % key)
    severity = finding.get("severity")
    if severity is not None and severity not in SEVERITIES:
        repairs.append("unknown severity %r: severity is one of %s"
                       % (severity, ", ".join(SEVERITIES)))
    rule = finding.get("rule")
    if rule is not None and rule not in RULES:
        repairs.append("unknown rule %r: rule is one of %s"
                       % (rule, ", ".join(RULES)))
    return repairs


def _normalize_test(entry: Any) -> Dict[str, Any]:
    """Fill total test defaults so partial input never crashes."""
    entry = entry if isinstance(entry, dict) else {}
    claims = entry.get("claims")
    if isinstance(claims, list):
        claim_list = [str(v) for v in claims
                      if isinstance(v, (str, int, float))]
    else:
        claim_list = []
    status = str(entry.get("status", DEFAULT_TEST["status"])
                 or DEFAULT_TEST["status"]).strip().lower()
    if status not in STATUSES:
        status = DEFAULT_TEST["status"]
    coverage = str(entry.get("coverage_kind",
                             DEFAULT_TEST["coverage_kind"])
                   or DEFAULT_TEST["coverage_kind"]).strip().lower()
    if coverage not in COVERAGE_KINDS:
        coverage = DEFAULT_TEST["coverage_kind"]
    return {
        "id": str(entry.get("id", DEFAULT_TEST["id"])),
        "claims": claim_list,
        "status": status,
        "red_reason": str(entry.get("red_reason", "")),
        "asserts_observable": bool(entry.get(
            "asserts_observable",
            DEFAULT_TEST["asserts_observable"])),
        "swallows_errors": bool(entry.get("swallows_errors", False)),
        "asserts_mock_only": bool(entry.get("asserts_mock_only",
                                            False)),
        "asserts_setup_state": bool(entry.get("asserts_setup_state",
                                              False)),
        "hard_codes_example": bool(entry.get("hard_codes_example",
                                             False)),
        "omits_relevant_state": bool(entry.get(
            "omits_relevant_state", False)),
        "is_structural_failure": bool(entry.get(
            "is_structural_failure", False)),
        "is_equivalent_mutant": bool(entry.get(
            "is_equivalent_mutant", False)),
        "alternative_impl_ok": bool(entry.get("alternative_impl_ok",
                                              False)),
        "coverage_kind": coverage,
    }


def _normalize_run(run: Any) -> Dict[str, Any]:
    """Fill total run defaults so partial input never crashes."""
    run = run if isinstance(run, dict) else {}
    risk = str(run.get("risk", DEFAULT_RUN["risk"])
               or DEFAULT_RUN["risk"]).upper()
    if risk not in RISKS:
        risk = DEFAULT_RUN["risk"]
    tests_raw = run.get("tests")
    if isinstance(tests_raw, list):
        tests = [_normalize_test(entry) for entry in tests_raw]
    else:
        tests = []
    return {
        "mold": str(run.get("mold", DEFAULT_RUN["mold"])),
        "mold_digest": str(run.get("mold_digest",
                                   DEFAULT_RUN["mold_digest"])),
        "risk": risk,
        "tests": tests,
        "provider": str(run.get("provider", DEFAULT_RUN["provider"])),
        "head": str(run.get("head", DEFAULT_RUN["head"])),
    }


def _numbered(rule: str, message: str, excerpt: str,
              index: int) -> Dict[str, str]:
    """Build one finding with a stable per-rule sequence id."""
    item = _make_finding(rule, message, excerpt)
    item["id"] = "%s-%d" % (rule, index + 1)
    return item


def _check_skipped_filtered(
        run: Dict[str, Any]) -> List[Dict[str, str]]:
    findings: List[Dict[str, str]] = []
    for test in run["tests"]:
        if test["status"] not in ABSOLUTE_STATUSES:
            continue
        findings.append(_numbered(
            "skipped_or_filtered",
            "test %r has status %r: skipped and filtered tests "
            "never qualify — remove the skip or filter so the "
            "test actually runs" % (test["id"][:60],
                                    test["status"]),
            test["id"] or "(unnamed test)", len(findings)))
    return findings


def _check_empty_placeholder(
        run: Dict[str, Any]) -> List[Dict[str, str]]:
    findings: List[Dict[str, str]] = []
    for test in run["tests"]:
        if test["coverage_kind"] not in ABSOLUTE_COVERAGES:
            continue
        findings.append(_numbered(
            "empty_or_placeholder",
            "test %r has coverage %r: empty and placeholder "
            "coverage never qualify — exercise the behavior "
            "for real" % (test["id"][:60],
                           test["coverage_kind"]),
            test["id"] or "(unnamed test)", len(findings)))
    return findings


def _check_hard_coded(
        run: Dict[str, Any]) -> List[Dict[str, str]]:
    findings: List[Dict[str, str]] = []
    for test in run["tests"]:
        if not test["hard_codes_example"]:
            continue
        findings.append(_numbered(
            "hard_coded_example",
            "test %r asserts one literal example with no "
            "variation or boundary: vary the input so the "
            "oracle must generalize" % test["id"][:60],
            test["id"] or "(unnamed test)", len(findings)))
    return findings


def _check_omitted_state(
        run: Dict[str, Any]) -> List[Dict[str, str]]:
    findings: List[Dict[str, str]] = []
    for test in run["tests"]:
        if not test["omits_relevant_state"]:
            continue
        findings.append(_numbered(
            "omitted_state",
            "test %r leaves a failure-shape-relevant dimension "
            "unexercised: cover the omitted state so the "
            "failure shape cannot hide" % test["id"][:60],
            test["id"] or "(unnamed test)", len(findings)))
    return findings


def _check_swallowed_error(
        run: Dict[str, Any]) -> List[Dict[str, str]]:
    findings: List[Dict[str, str]] = []
    for test in run["tests"]:
        if not test["swallows_errors"]:
            continue
        findings.append(_numbered(
            "swallowed_error",
            "test %r wraps the behavior under test in "
            "try/except-pass: let the error fail the test so "
            "failures stay visible" % test["id"][:60],
            test["id"] or "(unnamed test)", len(findings)))
    return findings


def _check_mock_only(
        run: Dict[str, Any]) -> List[Dict[str, str]]:
    findings: List[Dict[str, str]] = []
    for test in run["tests"]:
        if not test["asserts_mock_only"]:
            continue
        findings.append(_numbered(
            "mock_only_assertion",
            "test %r asserts only mock state, never the real "
            "subject: assert the externally observable result "
            "of the real subject" % test["id"][:60],
            test["id"] or "(unnamed test)", len(findings)))
    return findings


def _check_setup_self(
        run: Dict[str, Any]) -> List[Dict[str, str]]:
    findings: List[Dict[str, str]] = []
    for test in run["tests"]:
        if not test["asserts_setup_state"]:
            continue
        findings.append(_numbered(
            "setup_self_assertion",
            "test %r asserts state the fixture itself just "
            "wrote: assert behavior the fixture did not "
            "preordain" % test["id"][:60],
            test["id"] or "(unnamed test)", len(findings)))
    return findings


def _check_structural_not_red(
        run: Dict[str, Any]) -> List[Dict[str, str]]:
    findings: List[Dict[str, str]] = []
    for test in run["tests"]:
        if test["status"] != "failed":
            continue
        if not test["is_structural_failure"]:
            continue
        findings.append(_numbered(
            "structural_failure_not_red",
            "test %r is a structural failure (import error or "
            "fixture crash), not RED: fix the harness, then "
            "show RED for the right reason" % test["id"][:60],
            ("%s: %s" % (test["id"],
                          test["red_reason"])) or "(unnamed test)",
            len(findings)))
    return findings


def _check_equivalent_mutant(
        run: Dict[str, Any]) -> List[Dict[str, str]]:
    findings: List[Dict[str, str]] = []
    for test in run["tests"]:
        if not test["is_equivalent_mutant"]:
            continue
        findings.append(_numbered(
            "equivalent_mutant",
            "test %r cannot distinguish the mutant from the "
            "reference: strengthen the oracle until the "
            "mutant fails" % test["id"][:60],
            test["id"] or "(unnamed test)", len(findings)))
    return findings


def _has_clean_alternative(run: Dict[str, Any]) -> bool:
    """True when a rule-clean test accepts a valid alternative.

    A test that trips any cheating flag proves nothing about
    alternatives, so only a test with ``alternative_impl_ok``
    and no tripped flag counts.
    """
    for test in run["tests"]:
        if not test["alternative_impl_ok"]:
            continue
        if test["status"] in ABSOLUTE_STATUSES:
            continue
        if test["coverage_kind"] in ABSOLUTE_COVERAGES:
            continue
        if test["hard_codes_example"]:
            continue
        if test["omits_relevant_state"]:
            continue
        if test["swallows_errors"]:
            continue
        if test["asserts_mock_only"]:
            continue
        if test["asserts_setup_state"]:
            continue
        if test["status"] == "failed" and \
                test["is_structural_failure"]:
            continue
        if test["is_equivalent_mutant"]:
            continue
        return True
    return False


def _has_true_red(run: Dict[str, Any]) -> bool:
    """True when a failed test shows RED for the right reason."""
    for test in run["tests"]:
        if test["status"] != "failed":
            continue
        if test["is_structural_failure"]:
            continue
        if not test["red_reason"].strip():
            continue
        return True
    return False


def _check_no_alternative(
        run: Dict[str, Any]) -> List[Dict[str, str]]:
    if run["risk"] not in REQUIRES_ALTERNATIVE_RISKS:
        return []
    if _has_clean_alternative(run):
        return []
    return [_make_finding(
        "no_alternative_acceptance",
        "no test accepts a genuinely valid alternative "
        "implementation at %s: add one alternative_impl_ok "
        "test so the oracle proves it is not overfitted"
        % run["risk"],
        run["mold"] or "(unnamed mold)")]


def _check_no_true_red(
        run: Dict[str, Any]) -> List[Dict[str, str]]:
    if _has_true_red(run):
        return []
    return [_make_finding(
        "no_true_red",
        "no test shows RED for the right reason (failed with "
        "a non-empty red_reason and no structural failure): "
        "demonstrate the failing behavior before claiming "
        "GREEN",
        run["mold"] or "(unnamed mold)")]


def _run_digest(normalized_run: Dict[str, Any]) -> str:
    """Sha256 hex of the canonical JSON of one normalized run.

    Canonicalization is stdlib ``json.dumps`` with
    ``sort_keys=True`` encoded as UTF-8: key order and
    separators are fixed, so the same run always hashes the
    same and any content change hashes differently.
    """
    canonical = json.dumps(normalized_run, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def issue_receipt(mold: str, mold_digest: str, head: str,
                  provider: str, verdict: str,
                  run_digest: str) -> Dict[str, Any]:
    """Mint one qualification receipt as plain data (no I/O)."""
    return {
        "mold": str(mold),
        "mold_digest": str(mold_digest),
        "head": str(head),
        "provider": str(provider),
        "verdict": str(verdict),
        "run_digest": str(run_digest),
        "qualified_by": QUALIFIED_BY,
    }


def verify_receipt(receipt: Any, run: Any) -> List[str]:
    """Return repair strings for one receipt; empty means bound."""
    if not isinstance(receipt, dict):
        return ["receipt must be a mapping of plain data, not %s"
                % type(receipt).__name__]
    if not isinstance(run, dict):
        return ["run must be a mapping of plain data, not %s"
                % type(run).__name__]
    repairs: List[str] = []
    if str(receipt.get("mold_digest", "")) != \
            str(run.get("mold_digest", "")):
        repairs.append(
            "mold_digest mismatch: receipt %r != run %r; the "
            "receipt is bound to its exact Mold"
            % (str(receipt.get("mold_digest", ""))[:32],
               str(run.get("mold_digest", ""))[:32]))
    if str(receipt.get("head", "")) != str(run.get("head", "")):
        repairs.append(
            "head mismatch: receipt %r != run %r; re-qualify at "
            "the exact head" % (str(receipt.get("head", "")),
                                str(run.get("head", ""))))
    recomputed = _run_digest(_normalize_run(run))
    if str(receipt.get("run_digest", "")) != recomputed:
        repairs.append(
            "run_digest mismatch: receipt %r != recomputed %r; "
            "the run content changed after qualification"
            % (str(receipt.get("run_digest", ""))[:32],
               recomputed[:32]))
    return repairs


def qualify(run: Any) -> QualifyResult:
    """Qualify one mold run as plain data in, plain data out.

    Runs the eleven frozen rules in precedence order. A run
    with zero findings is qualified and gets a digest-bound
    receipt; any finding rejects the whole run. Pure function:
    no I/O, deterministic in its input.
    """
    normalized = _normalize_run(run)
    findings: List[Dict[str, str]] = []
    findings.extend(_check_skipped_filtered(normalized))
    findings.extend(_check_empty_placeholder(normalized))
    findings.extend(_check_hard_coded(normalized))
    findings.extend(_check_omitted_state(normalized))
    findings.extend(_check_swallowed_error(normalized))
    findings.extend(_check_mock_only(normalized))
    findings.extend(_check_setup_self(normalized))
    findings.extend(_check_structural_not_red(normalized))
    findings.extend(_check_equivalent_mutant(normalized))
    findings.extend(_check_no_alternative(normalized))
    findings.extend(_check_no_true_red(normalized))
    if findings:
        return QualifyResult(verdict="rejected", receipt=None,
                             findings=findings)
    receipt = issue_receipt(
        normalized["mold"], normalized["mold_digest"],
        normalized["head"], normalized["provider"], "qualified",
        _run_digest(normalized))
    return QualifyResult(verdict="qualified", receipt=receipt,
                         findings=[])


def _entries_of(corpus: Any) -> List[Dict[str, Any]]:
    if isinstance(corpus, dict):
        entries = corpus.get("entries")
    else:
        entries = corpus
    if not isinstance(entries, list):
        return []
    return entries


def validate_adversarial(
        corpus: Any) -> Tuple[List[str], List[Dict[str, Any]]]:
    """Validate the frozen qualification fixture oracle.

    Returns (findings, entries); an empty findings list means
    the corpus is a valid frozen oracle: frozen marker set,
    stable provenance, at least 10 entries, unique well-formed
    IDs, every entry computing its expected rules and verdict,
    and all 11 qualification rules covered.
    """
    if isinstance(corpus, dict):
        if corpus.get("_frozen") is not True:
            return (["adversarial corpus is not frozen: set "
                     "\"_frozen\": true"], [])
        provenance = str(corpus.get("_provenance", ""))
        if "Stage 31 #122" not in provenance:
            return (["adversarial corpus provenance must name "
                      "\"Stage 31 #122\""], [])
    elif not isinstance(corpus, list):
        return (["adversarial corpus must be a JSON object with an "
                 "'entries' array (or a bare array)"], [])
    entries = _entries_of(corpus)
    findings: List[str] = []
    if len(entries) < 10:
        findings.append("adversarial corpus holds %d entries, want "
                        "at least 10" % len(entries))
    seen: Dict[str, int] = {}
    covered = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            findings.append("entries[%d] is not a mapping" % index)
            continue
        cid = str(entry.get("id", ""))
        if not _ENTRY_ID_RE.match(cid):
            findings.append("entry %r: id is not "
                            "mold-qual.<class>.<nn>" % cid)
        if cid in seen:
            findings.append("duplicate entry id %s (entries %d "
                            "and %d)" % (cid, seen[cid], index))
        else:
            seen[cid] = index
        if not str(entry.get("note", "")).strip():
            findings.append("entry %s: a one-line adjudication note "
                            "is required" % cid)
        expected = entry.get("expected_rules")
        if not isinstance(expected, list):
            findings.append("entry %s: expected_rules must be a list"
                            % cid)
            continue
        for rule in expected:
            if rule not in RULES:
                findings.append("entry %s: unknown expected rule %r"
                                % (cid, rule))
        covered.update(str(r) for r in expected
                       if isinstance(r, str))
        expected_verdict = entry.get("expected_verdict")
        if expected_verdict not in ("qualified", "rejected"):
            findings.append("entry %s: expected_verdict must be "
                            "qualified|rejected" % cid)
            continue
        result = qualify(entry.get("run", {}))
        computed = sorted({f["rule"] for f in result.findings})
        if sorted(str(r) for r in expected) != computed:
            findings.append("entry %s: expected_rules %r != "
                            "qualify %r"
                            % (cid, sorted(str(r)
                                           for r in expected),
                               computed))
        if result.verdict != expected_verdict:
            findings.append("entry %s: expected_verdict %r != "
                            "qualify %r" % (cid, expected_verdict,
                                            result.verdict))
    for rule in RULES:
        if rule not in covered:
            findings.append("rule %r has no entries (all 11 "
                            "qualification rules are required)"
                            % rule)
    return findings, entries
