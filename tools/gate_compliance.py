"""Stage 57 Standard half: the Standards Compliance lane feeding the existing
PR Gate.

Missing/stale/bypassed standards evidence blocks merge — without
creating a second required GitHub context. The lane is read-only:
it evaluates route freshness, receipt presence, SAT standing,
GUARD/VERIFY/GATE evidence, adapter health, head equality, and
self-certification, then reports PASS / FAIL to the existing
single final aggregator (which stays the sole required check).
``evaluate`` maps one lane observation to PASS / FAIL;
``validate_lane_corpus`` checks the frozen oracle. Observations
are plain data; missing keys fall back to total defaults, never
a crash.

Frozen verdicts: PASS, FAIL.

Frozen rules, in check order (first hit decides)::

  missing-receipt    — product tests green but no Standards
                       Context Receipt: FAIL.
  stale-route        — route stale after path expansion: FAIL
                       and re-route.
  adapter-degraded   — adapter DEGRADED: FAIL until healthy.
  mold-violation     — unauthorized Mold write: FAIL.
  self-certify       — policy-PR self-certifying its own
                       control-plane change: FAIL (blocker).
  compact-valid      — low-risk valid compact work: PASS (no
                       theater).
  lane-skipped       — lane missing/skipped: FAIL (the lane
                       never silently absents).
  head-moved         — exact head moved since evidence: FAIL
                       and re-verify at the live head.

A fully evidenced lane is PASS. Findings use the standard five
keys via ``FINDING_FIELDS``; ``SEVERITIES`` names the allowed
severities; ``validate_finding`` returns repair strings (empty
means valid). Pure functions: no I/O, no subprocess, no
network — observations in, verdicts out. The lane reports; the
aggregator blocks. Simple and monorepo fixture profiles ship;
the one-final-Gate principle never changes.
"""

from typing import Any, Dict, List, Optional, Tuple

import re as _re

# Frozen lane verdicts.
VERDICTS = (
    "PASS",
    "FAIL",
)

SEVERITIES = ("blocker", "major", "minor")

FINDING_FIELDS = ("id", "rule", "finding", "severity", "excerpt")

# Frozen lane rules, in check order.
RULES = (
    "missing-receipt",
    "stale-route",
    "adapter-degraded",
    "mold-violation",
    "self-certify",
    "compact-valid",
    "lane-skipped",
    "head-moved",
)

# Verdict each rule carries.
RULE_VERDICTS = {
    "missing-receipt": "FAIL",
    "stale-route": "FAIL",
    "adapter-degraded": "FAIL",
    "mold-violation": "FAIL",
    "self-certify": "FAIL",
    "compact-valid": "PASS",
    "lane-skipped": "FAIL",
    "head-moved": "FAIL",
}

# Fixture profiles: simple (single package) vs monorepo.
PROFILES = (
    "simple",
    "monorepo",
)

# Entry-ID shape for the frozen oracle.
_ENTRY_ID_RE = _re.compile(r"^gate-compliance\.[a-z-]+\.\d{2}$")


def _make_finding(rule: str, message: str, excerpt: str,
                  severity: str = "major") -> Dict[str, str]:
    """Build one structured lane finding dict."""
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
        repairs.append("finding rule %r is not a frozen Stage 57 "
                       "lane rule" % (rule,))
    if "severity" in finding and finding.get("severity") not in SEVERITIES:
        repairs.append("finding severity %r must be "
                       "blocker|major|minor" % (finding.get("severity"),))
    return repairs


def _excerpt(observation: Dict[str, Any]) -> str:
    """Short evidence excerpt naming the PR."""
    for key in ("pr", "head", "profile"):
        value = observation.get(key)
        if isinstance(value, (str, int, float)) and str(value).strip():
            return str(value)[:200]
    return "(lane)"


def _normalize_observation(observation: Any) -> Dict[str, Any]:
    """Fill total defaults so partial input never crashes."""
    observation = observation if isinstance(observation, dict) else {}
    return {
        "pr": str(observation.get("pr", "")),
        "profile": str(observation.get("profile", "") or ""),
        "tests_green": bool(observation.get(
            "tests_green", False)),
        "receipt_present": bool(observation.get(
            "receipt_present", False)),
        "route_fresh": bool(observation.get(
            "route_fresh", True)),
        "adapter_healthy": bool(observation.get(
            "adapter_healthy", True)),
        "mold_authorized": bool(observation.get(
            "mold_authorized", True)),
        "policy_pr": bool(observation.get("policy_pr", False)),
        "self_certified": bool(observation.get(
            "self_certified", False)),
        "risk": str(observation.get("risk", "") or ""),
        "receipt_valid": bool(observation.get(
            "receipt_valid", True)),
        "lane_present": bool(observation.get(
            "lane_present", True)),
        "evidence_head": str(observation.get(
            "evidence_head", "") or ""),
        "live_head": str(observation.get("live_head", "") or ""),
    }


class LaneDecision:
    """One lane outcome for one observation."""

    verdict: str = "FAIL"
    rule: str = "missing-receipt"
    findings: List[Dict[str, str]] = []  # type: ignore[assignment]

    def __init__(self, verdict: str = "FAIL",
                 rule: str = "missing-receipt",
                 findings: Optional[List[Dict[str, str]]] = None):
        self.verdict = verdict
        self.rule = rule
        self.findings = list(findings or [])


def _decide(rule: str, message: str, tag: str,
            severity: str = "major") -> LaneDecision:
    return LaneDecision(
        verdict=RULE_VERDICTS[rule], rule=rule,
        findings=[_make_finding(rule, message, tag,
                                severity=severity)])


def evaluate(observation: Any) -> LaneDecision:
    """Map one lane observation to PASS / FAIL.

    Green tests without a receipt fail; stale routes fail;
    degraded adapters fail; unauthorized Mold writes fail;
    self-certifying policy PRs fail as blockers; valid compact
    work passes without theater; a skipped lane fails; a moved
    head fails. A fully evidenced lane passes. Pure function:
    no I/O, deterministic in its input. This reports; the
    single aggregator blocks.
    """
    item = _normalize_observation(observation)
    tag = _excerpt(item)
    if item["tests_green"] and not item["receipt_present"]:
        return _decide(
            "missing-receipt",
            "product tests green but no Standards Context "
            "Receipt: FAIL until the receipt lands",
            tag, severity="blocker")
    if not item["route_fresh"]:
        return _decide(
            "stale-route",
            "route stale after path expansion: FAIL and "
            "re-route",
            tag)
    if not item["adapter_healthy"]:
        return _decide(
            "adapter-degraded",
            "adapter DEGRADED: FAIL until the adapter is "
            "healthy",
            tag)
    if not item["mold_authorized"]:
        return _decide(
            "mold-violation",
            "unauthorized Mold write: FAIL",
            tag, severity="blocker")
    if item["policy_pr"] and item["self_certified"]:
        return _decide(
            "self-certify",
            "policy-PR self-certifying its own control-plane "
            "change: FAIL",
            tag, severity="blocker")
    low_risk = item["risk"] in ("R0", "R1", "")
    if low_risk and item["receipt_present"] and item[
            "receipt_valid"] and item["route_fresh"]:
        return _decide(
            "compact-valid",
            "low-risk valid compact work: PASS without theater",
            tag, severity="minor")
    if not item["lane_present"]:
        return _decide(
            "lane-skipped",
            "compliance lane missing/skipped: FAIL (the lane "
            "never silently absents)",
            tag, severity="blocker")
    if item["evidence_head"] and item["live_head"] \
            and item["evidence_head"] != item["live_head"]:
        return _decide(
            "head-moved",
            "exact head moved since evidence: FAIL and "
            "re-verify at the live head",
            tag, severity="blocker")
    if not item["receipt_present"] or not item["receipt_valid"]:
        return _decide(
            "missing-receipt",
            "standards evidence missing or invalid: FAIL",
            tag, severity="blocker")
    return LaneDecision(
        verdict="PASS", rule="compact-valid",
        findings=[_make_finding(
            "compact-valid",
            "fully evidenced lane: PASS to the aggregator",
            tag, severity="minor")])


def clean_observation() -> Dict[str, Any]:
    """One clean lane observation (PASS).

    Evidenced R2 work with a fresh route, healthy adapter,
    authorized Mold, independent certification, lane present,
    heads equal. Callers mutate one dimension per test.
    """
    head = "a" * 40
    return {
        "pr": "PR-1",
        "profile": "simple",
        "tests_green": True,
        "receipt_present": True,
        "route_fresh": True,
        "adapter_healthy": True,
        "mold_authorized": True,
        "policy_pr": False,
        "self_certified": False,
        "risk": "R2",
        "receipt_valid": True,
        "lane_present": True,
        "evidence_head": head,
        "live_head": head,
    }


def _entries_of(corpus: Any) -> List[Dict[str, Any]]:
    if isinstance(corpus, dict):
        entries = corpus.get("entries")
    else:
        entries = corpus
    if not isinstance(entries, list):
        return []
    return entries


def validate_lane_corpus(corpus: Any) -> Tuple[List[str],
                                               List[Dict[str, Any]]]:
    """Validate the frozen lane fixture oracle.

    Returns (findings, entries); an empty findings list means
    the corpus is a valid frozen oracle: frozen marker set,
    stable provenance, at least 8 entries, unique well-formed
    IDs, every entry computing its expected rule and verdict,
    and all 8 lane rules covered.
    """
    if isinstance(corpus, dict):
        if corpus.get("_frozen") is not True:
            return (["lane corpus is not frozen: set "
                     "\"_frozen\": true"], [])
        provenance = str(corpus.get("_provenance", ""))
        if "Stage 57 #148" not in provenance:
            return (["lane corpus provenance must name "
                      "\"Stage 57 #148\""], [])
    elif not isinstance(corpus, list):
        return (["lane corpus must be a JSON object with an "
                 "'entries' array (or a bare array)"], [])
    entries = _entries_of(corpus)
    findings: List[str] = []
    if len(entries) < 8:
        findings.append("lane corpus holds %d entries, want "
                        "at least 8" % len(entries))
    seen: Dict[str, int] = {}
    covered = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            findings.append("entries[%d] is not a mapping" % index)
            continue
        cid = str(entry.get("id", ""))
        if not _ENTRY_ID_RE.match(cid):
            findings.append("entry %r: id is not "
                            "gate-compliance.<class>.<nn>" % cid)
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
                            "frozen Stage 57 lane rule"
                            % (cid, rule))
            continue
        covered.add(str(rule))
        if entry.get("expected_verdict") != RULE_VERDICTS.get(
                str(rule)):
            findings.append("entry %s: expected_verdict %r != "
                            "rule verdict %r" % (cid, entry.get(
                                "expected_verdict"),
                                RULE_VERDICTS.get(str(rule))))
            continue
        result = evaluate(entry.get("observation", {}))
        if result.rule != rule:
            findings.append("entry %s: expected_rule %r != "
                            "evaluate %r"
                            % (cid, rule, result.rule))
        if result.verdict != entry.get("expected_verdict"):
            findings.append("entry %s: expected_verdict %r != "
                            "evaluate %r" % (cid, entry.get(
                                "expected_verdict"),
                                result.verdict))
    for rule in RULES:
        if rule not in covered:
            findings.append("rule %r has no entries (all 8 "
                            "lane rules are required)"
                            % rule)
    return findings, entries
