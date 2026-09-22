"""Stage 59a Standard half: independent review and bounded remediation.

Trusted provider-separated evidence-bound review with
deterministic verdicts plus a bounded fix/rebut/recheck loop —
one input to the existing PR Gate, never a second authority.
The reviewer runs pinned (model plus prompt digests), separate
from the builder family, evidence-bound (every finding cites
an acceptance criterion or AGENTS.md section), and verdicts
PASS / BLOCK (P0/P1 only) / INCONCLUSIVE / INFRASTRUCTURE_FAIL
/ POLICY_FAIL deterministically with stable fingerprints.
Remediation is bounded: FIXED or DISPUTE routed through the
original criterion with recheck; non-engaging repeats,
verdict shopping, scope creep, and stale heads refuse.
``review`` maps one review request to its verdict;
``remediate`` maps one remediation round to FIXED / DISPUTE /
RECHECK / REFUSE; ``validate_review_corpus`` checks the frozen
oracle. Requests are plain data; missing keys fall back to
total defaults, never a crash.

Frozen verdicts: PASS, BLOCK, INCONCLUSIVE, INFRASTRUCTURE_FAIL,
POLICY_FAIL.

Frozen remediation outcomes: FIXED, DISPUTE, RECHECK, REFUSE.

Frozen rules, in check order (first hit decides)::

  clean              — no material finding: PASS.
  p1-block           — P0/P1 evidence-grounded finding: BLOCK.
  p2-advisory        — P2 finding: advisory only, PASS with
                       notes.
  fake-citation      — citation names no real criterion: BLOCK
                       the review as untrustworthy (INCONCLUSIVE
                       when reviewer-side malformed).
  oracle-weakening   — finding asks to weaken an oracle: BLOCK
                       (POLICY_FAIL when policy-targeted).
  prompt-injection   — injected content in review scope: BLOCK
                       the tainted scope (INCONCLUSIVE when the
                       review itself is tainted).
  malformed-input    — malformed review input: INCONCLUSIVE.
  reviewer-outage    — reviewer unavailable: INFRASTRUCTURE_FAIL.
  stale-head         — review of a stale head: INCONCLUSIVE,
                       recheck at live head.
  same-provider      — reviewer family equals builder: POLICY_FAIL.
  verdict-shopping   — second review seeking a softer verdict:
                       REFUSE the round.
  scope-creep        — remediation widens scope: REFUSE the round.
  dispute            — evidence-grounded dispute through the
                       original criterion: DISPUTE.
  repeat-non-engage  — repeat round not engaging the finding:
                       REFUSE the round.
  owner-override     — explicit owner override: FIXED with
                       override provenance.

P0/P1 block; P2 advises. Scope locks to the reviewed diff.
Findings use the standard five keys via ``FINDING_FIELDS``;
``SEVERITIES`` names the allowed severities;
``validate_finding`` returns repair strings (empty means
valid). Pure functions: no I/O, no subprocess, no network —
requests in, verdicts out. Conflicting native review authority
is removed where the standard installs this lane.
"""

from typing import Any, Dict, List, Optional, Tuple

import hashlib
import json
import re as _re

# Frozen review verdicts.
VERDICTS = (
    "PASS",
    "BLOCK",
    "INCONCLUSIVE",
    "INFRASTRUCTURE_FAIL",
    "POLICY_FAIL",
)

# Frozen remediation outcomes.
REMEDIATION = (
    "FIXED",
    "DISPUTE",
    "RECHECK",
    "REFUSE",
)

SEVERITIES = ("blocker", "major", "minor")

FINDING_FIELDS = ("id", "rule", "finding", "severity", "excerpt")

# Severities that block the merge (P0/P1); P2 (minor) advises.
BLOCKING_SEVERITIES = ("blocker", "major")

# Frozen review/remediation rules, in check order.
RULES = (
    "clean",
    "p1-block",
    "p2-advisory",
    "fake-citation",
    "oracle-weakening",
    "prompt-injection",
    "malformed-input",
    "reviewer-outage",
    "stale-head",
    "same-provider",
    "verdict-shopping",
    "scope-creep",
    "dispute",
    "repeat-non-engage",
    "owner-override",
)

# Entry-ID shape for the frozen oracle.
_ENTRY_ID_RE = _re.compile(r"^independent-review\.[a-z-]+\.\d{2}$")

_INJECTION_RE = _re.compile(
    r"(ignore (previous|all) instructions|disregard .*instructions|"
    r"override .*rules?|bypass .*gate|reveal .*prompt)",
    _re.IGNORECASE)


def _make_finding(rule: str, message: str, excerpt: str,
                  severity: str = "major") -> Dict[str, str]:
    """Build one structured review finding dict."""
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
    repairs = []
    for key in FINDING_FIELDS:
        if key not in finding:
            repairs.append("finding is missing required key %r" % key)
    rule = finding.get("rule")
    if "rule" in finding and rule not in RULES:
        repairs.append("finding rule %r is not a frozen Stage 59a "
                       "review rule" % (rule,))
    if "severity" in finding and finding.get("severity") not in SEVERITIES:
        repairs.append("finding severity %r must be "
                       "blocker|major|minor" % (finding.get("severity"),))
    return repairs


def fingerprint(citations: List[str], verdict: str,
                head: str) -> str:
    """Stable review fingerprint: sha256 over sorted citations
    plus verdict plus head (16 hex). Deterministic citations
    produce stable fingerprints across reruns."""
    canonical = json.dumps(
        {"citations": sorted(citations), "verdict": verdict,
         "head": str(head)},
        sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode(
        "utf-8")).hexdigest()[:16]


class ReviewDecision:
    """One review outcome for one request."""

    verdict: str = "PASS"
    rule: str = "clean"
    findings: List[Dict[str, str]] = []  # type: ignore[assignment]

    def __init__(self, verdict: str = "PASS",
                 rule: str = "clean",
                 findings: Optional[List[Dict[str, str]]] = None):
        self.verdict = verdict
        self.rule = rule
        self.findings = list(findings or [])


class RemediationDecision:
    """One remediation outcome for one round."""

    outcome: str = "RECHECK"
    rule: str = "dispute"
    findings: List[Dict[str, str]] = []  # type: ignore[assignment]

    def __init__(self, outcome: str = "RECHECK",
                 rule: str = "dispute",
                 findings: Optional[List[Dict[str, str]]] = None):
        self.outcome = outcome
        self.rule = rule
        self.findings = list(findings or [])


def _normalize_request(request: Any) -> Dict[str, Any]:
    """Fill total defaults so partial input never crashes."""
    request = request if isinstance(request, dict) else {}
    findings = request.get("findings")
    return {
        "head": str(request.get("head", "")),
        "live_head": str(request.get("live_head", "") or ""),
        "builder_family": str(request.get(
            "builder_family", "") or ""),
        "reviewer_family": str(request.get(
            "reviewer_family", "") or ""),
        "reviewer_available": bool(request.get(
            "reviewer_available", True)),
        "malformed": bool(request.get("malformed", False)),
        "tainted": bool(request.get("tainted", False)),
        "findings": [dict(f) for f in findings
                     if isinstance(f, dict)]
        if isinstance(findings, list) else [],
        "criteria": [str(c) for c in request.get("criteria", [])
                     if isinstance(c, (str, int, float))]
        if isinstance(request.get("criteria"), list) else [],
    }


def _finding_severity(finding: Dict[str, Any]) -> str:
    severity = str(finding.get("severity", "") or "")
    return severity if severity in SEVERITIES else "minor"


def _citation_valid(finding: Dict[str, Any],
                    criteria: List[str]) -> bool:
    citation = str(finding.get("citation", "") or "")
    return bool(citation) and citation in criteria


def review(request: Any) -> ReviewDecision:
    """Map one review request to its verdict.

    Clean diffs pass; P0/P1 evidence-grounded findings block;
    P2 advises; fake citations, oracle-weakening asks, and
    injected scopes block (or inconclusive when reviewer-side);
    malformed inputs, outages, stale heads, and same-provider
    pairs return their non-pass verdicts. Deterministic in the
    input: same citations plus head fingerprint identically.
    Pure function: no I/O. This reviews; it never merges.
    """
    item = _normalize_request(request)
    tag = str(item["head"] or "(review)")[:200]
    if item["malformed"]:
        return ReviewDecision(
            verdict="INCONCLUSIVE", rule="malformed-input",
            findings=[_make_finding(
                "malformed-input",
                "malformed review input: INCONCLUSIVE, fix the "
                "input and re-review",
                tag)])
    if not item["reviewer_available"]:
        return ReviewDecision(
            verdict="INFRASTRUCTURE_FAIL",
            rule="reviewer-outage",
            findings=[_make_finding(
                "reviewer-outage",
                "reviewer unavailable: INFRASTRUCTURE_FAIL, "
                "retry the lane",
                tag, severity="blocker")])
    if item["live_head"] and item["head"] \
            and item["live_head"] != item["head"]:
        return ReviewDecision(
            verdict="INCONCLUSIVE", rule="stale-head",
            findings=[_make_finding(
                "stale-head",
                "review of a stale head: INCONCLUSIVE, recheck "
                "at the live head",
                tag)])
    if item["builder_family"] and item["reviewer_family"] \
            and item["builder_family"] == item["reviewer_family"]:
        return ReviewDecision(
            verdict="POLICY_FAIL", rule="same-provider",
            findings=[_make_finding(
                "same-provider",
                "reviewer family equals builder: POLICY_FAIL, "
                "reselect a separated reviewer",
                tag, severity="blocker")])
    if item["tainted"]:
        return ReviewDecision(
            verdict="INCONCLUSIVE", rule="prompt-injection",
            findings=[_make_finding(
                "prompt-injection",
                "review scope tainted by injection: "
                "INCONCLUSIVE, sanitize and re-review",
                tag, severity="blocker")])
    blockers: List[Dict[str, str]] = []
    advisories: List[Dict[str, str]] = []
    for finding in item["findings"]:
        text = str(finding.get("finding", "")) + " " + str(
            finding.get("excerpt", ""))
        if _INJECTION_RE.search(text):
            return ReviewDecision(
                verdict="BLOCK", rule="prompt-injection",
                findings=[_make_finding(
                    "prompt-injection",
                    "injected content in review scope: BLOCK "
                    "the tainted scope",
                    tag, severity="blocker")])
        if "weaken" in text.lower() and "oracle" in text.lower():
            if "policy" in text.lower():
                return ReviewDecision(
                    verdict="POLICY_FAIL",
                    rule="oracle-weakening",
                    findings=[_make_finding(
                        "oracle-weakening",
                        "finding asks to weaken a policy oracle: "
                        "POLICY_FAIL",
                        tag, severity="blocker")])
            return ReviewDecision(
                verdict="BLOCK", rule="oracle-weakening",
                findings=[_make_finding(
                    "oracle-weakening",
                    "finding asks to weaken an oracle: BLOCK",
                    tag, severity="blocker")])
        if not _citation_valid(finding, item["criteria"]):
            return ReviewDecision(
                verdict="BLOCK", rule="fake-citation",
                findings=[_make_finding(
                    "fake-citation",
                    "citation names no real criterion: BLOCK "
                    "the review as untrustworthy",
                    tag, severity="blocker")])
        if _finding_severity(finding) in BLOCKING_SEVERITIES:
            blockers.append(_make_finding(
                "p1-block",
                "P0/P1 evidence-grounded finding: BLOCK",
                tag, severity="blocker"))
        else:
            advisories.append(_make_finding(
                "p2-advisory",
                "P2 finding: advisory only",
                tag, severity="minor"))
    if blockers:
        return ReviewDecision(verdict="BLOCK", rule="p1-block",
                              findings=blockers)
    if advisories:
        return ReviewDecision(verdict="PASS", rule="p2-advisory",
                              findings=advisories)
    return ReviewDecision(
        verdict="PASS", rule="clean",
        findings=[_make_finding(
            "clean",
            "no material finding: PASS",
            tag, severity="minor")])


def _normalize_round(round_: Any) -> Dict[str, Any]:
    """Fill total defaults so partial input never crashes."""
    round_ = round_ if isinstance(round_, dict) else {}
    return {
        "original_rule": str(round_.get("original_rule", "")
                             or ""),
        "fixes": bool(round_.get("fixes", False)),
        "disputes": bool(round_.get("disputes", False)),
        "dispute_grounded": bool(round_.get(
            "dispute_grounded", False)),
        "shopping": bool(round_.get("shopping", False)),
        "widens_scope": bool(round_.get("widens_scope", False)),
        "engages": bool(round_.get("engages", True)),
        "repeat": bool(round_.get("repeat", False)),
        "owner": str(round_.get("owner", "") or ""),
        "owner_explicit": bool(round_.get(
            "owner_explicit", False)),
        "criterion": str(round_.get("criterion", "") or ""),
    }


def remediate(round_: Any) -> RemediationDecision:
    """Map one remediation round to FIXED / DISPUTE / RECHECK /
    REFUSE.

    Verdict shopping, scope creep, and non-engaging repeats
    refuse; evidence-grounded disputes route through the
    original criterion; explicit owner overrides fix with
    provenance; engaging fixes recheck. Pure function: no I/O.
    """
    item = _normalize_round(round_)
    tag = str(item["criterion"] or "(remediation)")[:200]
    if item["shopping"]:
        return RemediationDecision(
            outcome="REFUSE", rule="verdict-shopping",
            findings=[_make_finding(
                "verdict-shopping",
                "second review seeking a softer verdict: "
                "REFUSE the round",
                tag, severity="blocker")])
    if item["widens_scope"]:
        return RemediationDecision(
            outcome="REFUSE", rule="scope-creep",
            findings=[_make_finding(
                "scope-creep",
                "remediation widens scope: REFUSE the round, "
                "scope locks to the reviewed diff",
                tag, severity="blocker")])
    if item["repeat"] and not item["engages"]:
        return RemediationDecision(
            outcome="REFUSE", rule="repeat-non-engage",
            findings=[_make_finding(
                "repeat-non-engage",
                "repeat round not engaging the finding: "
                "REFUSE the round",
                tag, severity="blocker")])
    if item["disputes"] and item["dispute_grounded"] \
            and item["criterion"]:
        return RemediationDecision(
            outcome="DISPUTE", rule="dispute",
            findings=[_make_finding(
                "dispute",
                "evidence-grounded dispute through %r: route "
                "to the original criterion" % item["criterion"],
                tag)])
    if item["owner"] == "kgsmith19" and item["owner_explicit"]:
        return RemediationDecision(
            outcome="FIXED", rule="owner-override",
            findings=[_make_finding(
                "owner-override",
                "explicit owner override: FIXED with override "
                "provenance",
                tag, severity="minor")])
    return RemediationDecision(
        outcome="RECHECK", rule="dispute",
        findings=[_make_finding(
            "dispute",
            "recheck through the original criterion",
            tag, severity="minor")])


def clean_request() -> Dict[str, Any]:
    """One clean review request (PASS).

    No findings, separated providers, live head. Callers mutate
    one dimension per test.
    """
    head = "a" * 40
    return {
        "head": head,
        "live_head": head,
        "builder_family": "anthropic",
        "reviewer_family": "openai",
        "reviewer_available": True,
        "malformed": False,
        "tainted": False,
        "findings": [],
        "criteria": ["AC-1"],
    }


def _entries_of(corpus: Any) -> List[Dict[str, Any]]:
    if isinstance(corpus, dict):
        entries = corpus.get("entries")
    else:
        entries = corpus
    if not isinstance(entries, list):
        return []
    return entries


def validate_review_corpus(corpus: Any) -> Tuple[List[str],
                                                 List[Dict[str, Any]]]:
    """Validate the frozen review fixture oracle.

    Returns (findings, entries); an empty findings list means
    the corpus is a valid frozen oracle: frozen marker set,
    stable provenance, at least 15 entries, unique well-formed
    IDs, every entry computing its expected rule and verdict
    (plus remediation outcomes where present), and all 15
    review rules covered.
    """
    if isinstance(corpus, dict):
        if corpus.get("_frozen") is not True:
            return (["review corpus is not frozen: set "
                     "\"_frozen\": true"], [])
        provenance = str(corpus.get("_provenance", ""))
        if "Stage 59a #150" not in provenance:
            return (["review corpus provenance must name "
                      "\"Stage 59a #150\""], [])
    elif not isinstance(corpus, list):
        return (["review corpus must be a JSON object with an "
                 "'entries' array (or a bare array)"], [])
    entries = _entries_of(corpus)
    findings: List[str] = []
    if len(entries) < 15:
        findings.append("review corpus holds %d entries, want "
                        "at least 15" % len(entries))
    seen: Dict[str, int] = {}
    covered = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            findings.append("entries[%d] is not a mapping" % index)
            continue
        cid = str(entry.get("id", ""))
        if not _ENTRY_ID_RE.match(cid):
            findings.append("entry %r: id is not "
                            "independent-review.<class>.<nn>" % cid)
        if cid in seen:
            findings.append("duplicate entry id %s (entries %d "
                            "and %d)" % (cid, seen[cid], index))
        else:
            seen[cid] = index
        if not str(entry.get("note", "")).strip():
            findings.append("entry %s: a one-line adjudication note "
                            "is required" % cid)
        for key in ("expected_rule", "expected_verdict"):
            if key not in entry:
                findings.append("entry %s: %s is required"
                                % (cid, key))
        rule = entry.get("expected_rule")
        if rule not in RULES:
            findings.append("entry %s: expected_rule %r is not a "
                            "frozen Stage 59a review rule"
                            % (cid, rule))
            continue
        covered.add(str(rule))
        round_ = entry.get("remediation")
        expected_outcome = entry.get("expected_outcome")
        if round_ is not None or expected_outcome is not None:
            if not isinstance(round_, dict):
                findings.append("entry %s: remediation must be a "
                                "mapping" % cid)
                continue
            if expected_outcome not in REMEDIATION:
                findings.append("entry %s: expected_outcome %r is "
                                "not frozen" % (cid,
                                                expected_outcome))
                continue
            remediation = remediate(round_)
            if remediation.rule != rule:
                findings.append("entry %s: expected_rule %r != "
                                "remediate %r"
                                % (cid, rule, remediation.rule))
            if remediation.outcome != expected_outcome:
                findings.append("entry %s: expected_outcome %r != "
                                "remediate %r" % (cid,
                                                  expected_outcome,
                                                  remediation.outcome))
            continue
        result = review(entry.get("request", {}))
        if result.rule != rule:
            findings.append("entry %s: expected_rule %r != "
                            "review %r" % (cid, rule, result.rule))
        if result.verdict != entry.get("expected_verdict"):
            findings.append("entry %s: expected_verdict %r != "
                            "review %r" % (cid, entry.get(
                                "expected_verdict"),
                                result.verdict))
    for rule in RULES:
        if rule not in covered:
            findings.append("rule %r has no entries (all 15 "
                            "review rules are required)"
                            % rule)
    return findings, entries
