"""Stage 58 Standard half: the operational recovery loop and systematic
debugging router.

Every unexpected failure becomes preserved evidence, an explicit
class, and the smallest responsible recovery route — never a
blind retry loop. The ten-class taxonomy separates product
defects from infrastructure flakes, external-dependency faults,
idempotency blocks, budget exhaustion, and unknown causes;
every route runs reproduce -> one hypothesis -> test -> root
cause -> repair (systematic-debugging). Retry needs an
explicit transient hypothesis plus a budget on unchanged
state; non-idempotent state never retries blind; partial green
never counts as complete. ``triage`` maps one failure report
to its class plus recovery route; ``validate_failure_corpus``
checks the frozen oracle. Reports are plain data; missing keys
fall back to total defaults, never a crash.

Frozen failure classes::

  product-defect / infra-flake / external-dependency /
  idempotency-block / budget-exhausted / lease-conflict /
  stale-state / policy-deny / tool-overflow / unknown

Frozen recovery routes::

  repair / retry-bounded / reconcile / escalate / recover-capsule

Frozen rules, in check order (first hit decides)::

  blind-rerun        — retry with no hypothesis: refuse, route
                       systematic-debugging first.
  non-idempotent     — retry on non-idempotent state: refuse
                       without explicit confirmation.
  partial-green      — partial green treated as complete:
                       refuse the verdict.
  misclassified      — infra flake filed as product defect (or
                       reverse): reclassify before routing.
  exhausted-budget   — retry budget spent: escalate, never
                       loop.
  infra-as-product   — infrastructure fault routed to product
                       repair: reroute to infra recovery.
  unknown-mutation   — UNKNOWN cause with mutation proposed:
                       refuse mutation until known.
  unowned-lane       — failure with no owning lane: escalate
                       with the lane named.
  historical-replay  — historical workflow failure reproduces
                       the route: repair from history.
  clean-triage       — classified with evidence and a bounded
                       route: triage complete.

A clean product defect triages to repair with evidence
preserved. Findings use the standard five keys via
``FINDING_FIELDS``; ``SEVERITIES`` names the allowed
severities; ``validate_finding`` returns repair strings (empty
means valid). Pure functions: no I/O, no subprocess, no
network — reports in, classes plus routes out.
``standardctl triage`` ships the router; failure artifacts
carry exact recovery acceptance evidence.
"""

from typing import Any, Dict, List, Optional, Tuple

import re as _re

# Frozen failure classes.
CLASSES = (
    "product-defect",
    "infra-flake",
    "external-dependency",
    "idempotency-block",
    "budget-exhausted",
    "lease-conflict",
    "stale-state",
    "policy-deny",
    "tool-overflow",
    "unknown",
)

# Frozen recovery routes.
ROUTES = (
    "repair",
    "retry-bounded",
    "reconcile",
    "escalate",
    "recover-capsule",
)

SEVERITIES = ("blocker", "major", "minor")

FINDING_FIELDS = ("id", "rule", "finding", "severity", "excerpt")

# Frozen triage rules, in check order.
RULES = (
    "blind-rerun",
    "non-idempotent",
    "partial-green",
    "misclassified",
    "exhausted-budget",
    "infra-as-product",
    "unknown-mutation",
    "unowned-lane",
    "historical-replay",
    "clean-triage",
)

# Route each rule carries (historical-replay carries repair).
RULE_ROUTES = {
    "blind-rerun": "repair",
    "non-idempotent": "escalate",
    "partial-green": "repair",
    "misclassified": "reconcile",
    "exhausted-budget": "escalate",
    "infra-as-product": "reconcile",
    "unknown-mutation": "escalate",
    "unowned-lane": "escalate",
    "historical-replay": "repair",
    "clean-triage": "repair",
}

# Entry-ID shape for the frozen oracle.
_ENTRY_ID_RE = _re.compile(r"^recovery-loop\.[a-z-]+\.\d{2}$")


def _make_finding(rule: str, message: str, excerpt: str,
                  severity: str = "major") -> Dict[str, str]:
    """Build one structured triage finding dict."""
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
        repairs.append("finding rule %r is not a frozen Stage 58 "
                       "triage rule" % (rule,))
    if "severity" in finding and finding.get("severity") not in SEVERITIES:
        repairs.append("finding severity %r must be "
                       "blocker|major|minor" % (finding.get("severity"),))
    return repairs


def _excerpt(report: Dict[str, Any]) -> str:
    """Short evidence excerpt naming the failure."""
    for key in ("failure", "test", "workflow"):
        value = report.get(key)
        if isinstance(value, (str, int, float)) and str(value).strip():
            return str(value)[:200]
    return "(failure)"


def _normalize_report(report: Any) -> Dict[str, Any]:
    """Fill total defaults so partial input never crashes."""
    report = report if isinstance(report, dict) else {}
    return {
        "failure": str(report.get("failure", "")),
        "filed_class": str(report.get("filed_class", "") or ""),
        "true_class": str(report.get("true_class", "") or ""),
        "hypothesis": str(report.get("hypothesis", "") or ""),
        "retry_proposed": bool(report.get(
            "retry_proposed", False)),
        "idempotent": bool(report.get("idempotent", True)),
        "confirmed": bool(report.get("confirmed", False)),
        "partial_green": bool(report.get(
            "partial_green", False)),
        "retries_left": int(report.get("retries_left", 1)),
        "owning_lane": str(report.get("owning_lane", "") or ""),
        "evidence_preserved": bool(report.get(
            "evidence_preserved", True)),
        "unknown_mutation": bool(report.get(
            "unknown_mutation", False)),
        "historical_match": bool(report.get(
            "historical_match", False)),
        "infra_signal": bool(report.get("infra_signal", False)),
    }


class TriageDecision:
    """One triage outcome for one failure report."""

    failure_class: str = "unknown"
    route: str = "escalate"
    rule: str = "clean-triage"
    findings: List[Dict[str, str]] = []  # type: ignore[assignment]

    def __init__(self, failure_class: str = "unknown",
                 route: str = "escalate",
                 rule: str = "clean-triage",
                 findings: Optional[List[Dict[str, str]]] = None):
        self.failure_class = failure_class
        self.route = route
        self.rule = rule
        self.findings = list(findings or [])


def _decide(rule: str, failure_class: str, message: str,
            tag: str, severity: str = "major") -> TriageDecision:
    return TriageDecision(
        failure_class=failure_class, route=RULE_ROUTES[rule],
        rule=rule,
        findings=[_make_finding(rule, message, tag,
                                severity=severity)])


def triage(report: Any) -> TriageDecision:
    """Map one failure report to its class plus recovery route.

    Blind reruns route debugging first; non-idempotent retries
    need confirmation; partial green never completes;
    misclassifications reclassify; spent budgets escalate; infra
    faults reroute to infra recovery; UNKNOWN never mutates;
    unowned lanes escalate named; historical matches repair from
    history; clean reports triage with evidence preserved. Pure
    function: no I/O, deterministic in its input. This triages;
    it never retries, never repairs, never mutates.
    """
    item = _normalize_report(report)
    tag = _excerpt(item)
    filed = item["filed_class"] or item["true_class"] or "unknown"
    true = item["true_class"] or item["filed_class"] or "unknown"
    if true not in CLASSES:
        true = "unknown"
    if filed not in CLASSES:
        filed = "unknown"
    if item["retry_proposed"] and not item["hypothesis"].strip():
        return _decide(
            "blind-rerun", filed,
            "retry with no hypothesis: reproduce, hypothesize, "
            "test, root-cause, then repair — never a blind loop",
            tag, severity="blocker")
    if item["retry_proposed"] and not item["idempotent"] \
            and not item["confirmed"]:
        return _decide(
            "non-idempotent", filed,
            "retry on non-idempotent state without explicit "
            "confirmation: refuse",
            tag, severity="blocker")
    if item["partial_green"]:
        return _decide(
            "partial-green", filed,
            "partial green is not complete: finish or repair, "
            "never declare done",
            tag, severity="blocker")
    if item["filed_class"] and item["true_class"] \
            and item["filed_class"] != item["true_class"]:
        return _decide(
            "misclassified", true,
            "filed as %r but evidence shows %r: reclassify "
            "before routing" % (filed, true),
            tag)
    if item["retry_proposed"] and item["retries_left"] <= 0:
        return _decide(
            "exhausted-budget", filed,
            "retry budget spent: escalate, never loop",
            tag)
    if filed == "product-defect" and item["infra_signal"]:
        return _decide(
            "infra-as-product", "infra-flake",
            "infrastructure fault filed as product defect: "
            "reroute to infra recovery",
            tag)
    if true == "unknown" and item["unknown_mutation"]:
        return _decide(
            "unknown-mutation", "unknown",
            "UNKNOWN cause with mutation proposed: refuse "
            "mutation until the class is known",
            tag, severity="blocker")
    if not item["owning_lane"].strip():
        return _decide(
            "unowned-lane", filed,
            "failure with no owning lane: escalate with the "
            "lane named",
            tag)
    if item["historical_match"]:
        return _decide(
            "historical-replay", filed,
            "historical workflow failure reproduces the route: "
            "repair from history",
            tag, severity="minor")
    if not item["evidence_preserved"]:
        return _decide(
            "clean-triage", filed,
            "evidence not preserved: preserve evidence, then "
            "triage",
            tag, severity="blocker")
    return TriageDecision(
        failure_class=filed, route="repair", rule="clean-triage",
        findings=[_make_finding(
            "clean-triage",
            "classified as %r with evidence preserved: route "
            "%s" % (filed, RULE_ROUTES["clean-triage"]),
            tag, severity="minor")])


def clean_report() -> Dict[str, Any]:
    """One clean failure report (triaged product defect).

    Filed correctly with evidence preserved, an owning lane,
    and no retry proposed. Callers mutate one dimension per
    test.
    """
    return {
        "failure": "test_red_by_construction failed",
        "filed_class": "product-defect",
        "true_class": "product-defect",
        "hypothesis": "",
        "retry_proposed": False,
        "idempotent": True,
        "confirmed": False,
        "partial_green": False,
        "retries_left": 1,
        "owning_lane": "Verification Tests",
        "evidence_preserved": True,
        "unknown_mutation": False,
        "historical_match": False,
        "infra_signal": False,
    }


def _entries_of(corpus: Any) -> List[Dict[str, Any]]:
    if isinstance(corpus, dict):
        entries = corpus.get("entries")
    else:
        entries = corpus
    if not isinstance(entries, list):
        return []
    return entries


def validate_failure_corpus(corpus: Any) -> Tuple[List[str],
                                                  List[Dict[str, Any]]]:
    """Validate the frozen failure fixture oracle.

    Returns (findings, entries); an empty findings list means
    the corpus is a valid frozen oracle: frozen marker set,
    stable provenance, at least 10 entries, unique well-formed
    IDs, every entry computing its expected rule, class, and
    route, and all 10 triage rules covered.
    """
    if isinstance(corpus, dict):
        if corpus.get("_frozen") is not True:
            return (["failure corpus is not frozen: set "
                     "\"_frozen\": true"], [])
        provenance = str(corpus.get("_provenance", ""))
        if "Stage 58 #149" not in provenance:
            return (["failure corpus provenance must name "
                      "\"Stage 58 #149\""], [])
    elif not isinstance(corpus, list):
        return (["failure corpus must be a JSON object with an "
                 "'entries' array (or a bare array)"], [])
    entries = _entries_of(corpus)
    findings: List[str] = []
    if len(entries) < 10:
        findings.append("failure corpus holds %d entries, want "
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
                            "recovery-loop.<class>.<nn>" % cid)
        if cid in seen:
            findings.append("duplicate entry id %s (entries %d "
                            "and %d)" % (cid, seen[cid], index))
        else:
            seen[cid] = index
        if not str(entry.get("note", "")).strip():
            findings.append("entry %s: a one-line adjudication note "
                            "is required" % cid)
        for key in ("expected_rule", "expected_class",
                    "expected_route"):
            if key not in entry:
                findings.append("entry %s: %s is required"
                                % (cid, key))
        rule = entry.get("expected_rule")
        if rule not in RULES:
            findings.append("entry %s: expected_rule %r is not a "
                            "frozen Stage 58 triage rule"
                            % (cid, rule))
            continue
        covered.add(str(rule))
        if entry.get("expected_route") != RULE_ROUTES.get(
                str(rule)):
            findings.append("entry %s: expected_route %r != "
                            "rule route %r" % (cid, entry.get(
                                "expected_route"),
                                RULE_ROUTES.get(str(rule))))
            continue
        result = triage(entry.get("report", {}))
        if result.rule != rule:
            findings.append("entry %s: expected_rule %r != "
                            "triage %r" % (cid, rule, result.rule))
        if result.failure_class != entry.get("expected_class"):
            findings.append("entry %s: expected_class %r != "
                            "triage %r" % (cid, entry.get(
                                "expected_class"),
                                result.failure_class))
        if result.route != entry.get("expected_route"):
            findings.append("entry %s: expected_route %r != "
                            "triage %r" % (cid, entry.get(
                                "expected_route"),
                                result.route))
    for rule in RULES:
        if rule not in covered:
            findings.append("rule %r has no entries (all 10 "
                            "triage rules are required)"
                            % rule)
    return findings, entries
