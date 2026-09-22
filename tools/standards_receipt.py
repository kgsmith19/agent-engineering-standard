"""Stage 53 Standard half: selective standards receipts and acceptance.

Prove applicable standards were supplied and correctly
acknowledged where risk justifies it — without low-risk
compliance theater. The Standards Context Receipt binds
route, receipt, and SAT hashes into Work State and evidence:
R0/R1 work needs receipt plus capability/tests only (never a
structured SAT quiz); new providers, R2/R3 work,
privileged/policy/control-plane scope, and authority changes
always require structured SAT. ``issue`` maps one receipt
attempt to ISSUED / QUIZ / REFUSE; ``validate_receipt_corpus``
checks the frozen oracle. Attempts are plain data; missing
keys fall back to total defaults, never a crash.

Frozen verdicts: ISSUED, QUIZ, REFUSE.

Frozen rules, in check order (first hit decides)::

  wrong-ack          — acknowledgement diverges from the
                       routed rule text: refuse.
  missing-critical   — routed critical rule absent from the
                       receipt: refuse.
  stale-spec         — Spec changed since routing: refuse and
                       re-route.
  stale-path         — touched paths changed since routing:
                       refuse and re-route.
  stale-phase        — phase changed since routing: refuse and
                       re-route.
  stale-standard     — standard hash moved since routing:
                       refuse and re-route.
  r0-no-quiz         — R0/R1 without triggers: ISSUED without
                       any quiz (no theater).
  r3-required        — new provider, R2/R3, privileged scope,
                       or authority change: QUIZ (structured
                       SAT required).
  adapter-omitted    — required adapter capability omitted:
                       refuse.
  own-receipt        — subagent's self-issued receipt as
                       independent proof: refuse.
  lower-trust        — malicious lower-trust instruction to
                       skip or weaken: refuse (blocker).
  clean-receipt      — complete routed acknowledgement: ISSUED.

A complete R0 receipt is ISSUED; a triggered attempt is QUIZ
until SAT passes. Findings use the standard five keys via
``FINDING_FIELDS``; ``SEVERITIES`` names the allowed
severities; ``validate_finding`` returns repair strings (empty
means valid). Pure functions: no I/O, no subprocess, no
network — attempts in, verdicts out. Receipts embed in Work
State and evidence for every later enforcement stage.
"""

from typing import Any, Dict, List, Optional, Tuple

import hashlib
import json
import re as _re

# Frozen receipt verdicts.
VERDICTS = (
    "ISSUED",
    "QUIZ",
    "REFUSE",
)

SEVERITIES = ("blocker", "major", "minor")

FINDING_FIELDS = ("id", "rule", "finding", "severity", "excerpt")

# Frozen receipt rules, in check order.
RULES = (
    "wrong-ack",
    "missing-critical",
    "stale-spec",
    "stale-path",
    "stale-phase",
    "stale-standard",
    "r0-no-quiz",
    "r3-required",
    "adapter-omitted",
    "own-receipt",
    "lower-trust",
    "clean-receipt",
)

# Verdict each rule carries.
RULE_VERDICTS = {
    "wrong-ack": "REFUSE",
    "missing-critical": "REFUSE",
    "stale-spec": "REFUSE",
    "stale-path": "REFUSE",
    "stale-phase": "REFUSE",
    "stale-standard": "REFUSE",
    "r0-no-quiz": "ISSUED",
    "r3-required": "QUIZ",
    "adapter-omitted": "REFUSE",
    "own-receipt": "REFUSE",
    "lower-trust": "REFUSE",
    "clean-receipt": "ISSUED",
}

# SAT triggers: any one requires structured SAT.
SAT_TRIGGERS = (
    "new-provider",
    "high-risk",
    "privileged-scope",
    "authority-change",
)

# Entry-ID shape for the frozen oracle.
_ENTRY_ID_RE = _re.compile(r"^standards-receipt\.[a-z-]+\.\d{2}$")

_LOWER_TRUST_RE = _re.compile(
    r"(skip (the |this )?(quiz|sat|receipt|check)|weaken .*receipt|"
    r"self-?certify|lower-?trust .*approv|ignore .*standards?)",
    _re.IGNORECASE)


def _make_finding(rule: str, message: str, excerpt: str,
                  severity: str = "major") -> Dict[str, str]:
    """Build one structured receipt finding dict."""
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
        repairs.append("finding rule %r is not a frozen Stage 53 "
                       "receipt rule" % (rule,))
    if "severity" in finding and finding.get("severity") not in SEVERITIES:
        repairs.append("finding severity %r must be "
                       "blocker|major|minor" % (finding.get("severity"),))
    return repairs


def receipt_hash(route: List[str], ack: List[str],
                 standard_hash: str) -> str:
    """Bind route, acknowledgement, and standard hash into one
    receipt digest (sha256, 16 hex). Work State and evidence
    carry this digest; any drift invalidates it."""
    canonical = json.dumps(
        {"route": sorted(route), "ack": sorted(ack),
         "standard": str(standard_hash)},
        sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _excerpt(attempt: Dict[str, Any]) -> str:
    """Short evidence excerpt naming the slice."""
    for key in ("slice", "task", "route"):
        value = attempt.get(key)
        if isinstance(value, (str, int, float)) and str(value).strip():
            return str(value)[:200]
    items = attempt.get("routed")
    if isinstance(items, list) and items:
        return str(items[0])[:200]
    return "(receipt)"


def _normalize_attempt(attempt: Any) -> Dict[str, Any]:
    """Fill total defaults so partial input never crashes."""
    attempt = attempt if isinstance(attempt, dict) else {}

    def _strs(value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(v) for v in value
                    if isinstance(v, (str, int, float))]
        return []

    triggers = attempt.get("sat_triggers")
    return {
        "slice": str(attempt.get("slice", "")),
        "risk": str(attempt.get("risk", "") or ""),
        "routed": _strs(attempt.get("routed")),
        "critical": _strs(attempt.get("critical")),
        "acknowledged": _strs(attempt.get("acknowledged")),
        "ack_text": str(attempt.get("ack_text", "") or ""),
        "route_text": str(attempt.get("route_text", "") or ""),
        "spec_hash": str(attempt.get("spec_hash", "") or ""),
        "routed_spec": str(attempt.get("routed_spec", "") or ""),
        "paths": _strs(attempt.get("paths")),
        "routed_paths": _strs(attempt.get("routed_paths")),
        "phase": str(attempt.get("phase", "") or ""),
        "routed_phase": str(attempt.get("routed_phase", "")
                            or ""),
        "standard_hash": str(attempt.get(
            "standard_hash", "") or ""),
        "routed_standard": str(attempt.get(
            "routed_standard", "") or ""),
        "sat_triggers": list(triggers)
        if isinstance(triggers, list) else [],
        "sat_passed": bool(attempt.get("sat_passed", False)),
        "adapter_present": bool(attempt.get(
            "adapter_present", True)),
        "adapter_required": bool(attempt.get(
            "adapter_required", False)),
        "self_issued": bool(attempt.get("self_issued", False)),
        "instruction": str(attempt.get("instruction", "") or ""),
    }


class ReceiptDecision:
    """One receipt outcome for one attempt."""

    verdict: str = "REFUSE"
    rule: str = "clean-receipt"
    digest: str = ""
    findings: List[Dict[str, str]] = []  # type: ignore[assignment]

    def __init__(self, verdict: str = "REFUSE",
                 rule: str = "clean-receipt", digest: str = "",
                 findings: Optional[List[Dict[str, str]]] = None):
        self.verdict = verdict
        self.rule = rule
        self.digest = digest
        self.findings = list(findings or [])


def _decide(rule: str, message: str, tag: str,
            digest: str = "",
            severity: str = "major") -> ReceiptDecision:
    return ReceiptDecision(
        verdict=RULE_VERDICTS[rule], rule=rule, digest=digest,
        findings=[_make_finding(rule, message, tag,
                                severity=severity)])


def _triggered(item: Dict[str, Any]) -> bool:
    """True when structured SAT is required."""
    if item["risk"] in ("R2", "R3"):
        return True
    return any(t in SAT_TRIGGERS for t in item["sat_triggers"])


def issue(attempt: Any) -> ReceiptDecision:
    """Map one receipt attempt to ISSUED / QUIZ / REFUSE.

    Acknowledgements must match, critical rules must ride,
    routing inputs must be fresh, adapters must be present,
    self-issued receipts never count, lower-trust skip orders
    refuse. R0/R1 untriggered attempts issue without a quiz;
    triggered attempts quiz until SAT passes; complete
    triggered attempts with passed SAT issue. Pure function:
    no I/O, deterministic in its input. This issues receipts;
    it never weakens to skip.
    """
    item = _normalize_attempt(attempt)
    tag = _excerpt(item)
    if item["ack_text"] and item["route_text"] \
            and item["ack_text"] != item["route_text"]:
        return _decide(
            "wrong-ack",
            "acknowledgement diverges from the routed rule "
            "text: acknowledge exactly",
            tag, severity="blocker")
    for critical in item["critical"]:
        if critical not in item["acknowledged"]:
            return _decide(
                "missing-critical",
                "routed critical rule %r absent from the "
                "receipt: acknowledge every critical rule"
                % (critical,),
                tag, severity="blocker")
    if item["routed_spec"] and item["spec_hash"] \
            and item["routed_spec"] != item["spec_hash"]:
        return _decide(
            "stale-spec",
            "Spec changed since routing: re-route before "
            "issuing",
            tag)
    if item["routed_paths"] and sorted(item["paths"]) != sorted(
            item["routed_paths"]):
        return _decide(
            "stale-path",
            "touched paths changed since routing: re-route "
            "before issuing",
            tag)
    if item["routed_phase"] and item["phase"] \
            and item["routed_phase"] != item["phase"]:
        return _decide(
            "stale-phase",
            "phase changed since routing: re-route before "
            "issuing",
            tag)
    if item["routed_standard"] and item["standard_hash"] \
            and item["routed_standard"] != item["standard_hash"]:
        return _decide(
            "stale-standard",
            "standard hash moved since routing: re-route "
            "before issuing",
            tag)
    if _LOWER_TRUST_RE.search(item["instruction"]):
        return _decide(
            "lower-trust",
            "lower-trust instruction to skip or weaken the "
            "receipt: refuse",
            tag, severity="blocker")
    if item["adapter_required"] and not item["adapter_present"]:
        return _decide(
            "adapter-omitted",
            "required adapter capability omitted: attach it "
            "before issuing",
            tag, severity="blocker")
    if item["self_issued"]:
        return _decide(
            "own-receipt",
            "subagent self-issued receipt is not independent "
            "proof: obtain independent acknowledgement",
            tag, severity="blocker")
    digest = receipt_hash(item["routed"], item["acknowledged"],
                          item["standard_hash"])
    triggered = _triggered(item)
    low_risk = item["risk"] in ("R0", "R1", "")
    if low_risk and not triggered:
        if item["sat_passed"] or True:
            first = _decide(
                "r0-no-quiz",
                "R0/R1 receipt issued without a quiz: receipt "
                "plus capability/tests suffice",
                tag, digest=digest, severity="minor")
            return first
    if triggered and not item["sat_passed"]:
        return _decide(
            "r3-required",
            "structured SAT required (new provider, R2/R3, "
            "privileged scope, or authority change): pass SAT "
            "before issuing",
            tag, severity="blocker")
    return _decide(
        "clean-receipt",
        "complete routed acknowledgement: receipt issued with "
        "route/receipt/SAT hashes",
        tag, digest=digest, severity="minor")


def clean_attempt() -> Dict[str, Any]:
    """One clean receipt attempt (ISSUED).

    R0 slice, routed rules acknowledged, fresh inputs,
    adapter present, independent acknowledgement. Callers
    mutate one dimension per test.
    """
    return {
        "slice": "slice-1",
        "risk": "R0",
        "routed": ["route-minimal", "thin-outcome"],
        "critical": [],
        "acknowledged": ["route-minimal", "thin-outcome"],
        "ack_text": "same",
        "route_text": "same",
        "spec_hash": "spec-1",
        "routed_spec": "spec-1",
        "paths": ["tools/a.py"],
        "routed_paths": ["tools/a.py"],
        "phase": "implement",
        "routed_phase": "implement",
        "standard_hash": "std-1",
        "routed_standard": "std-1",
        "sat_triggers": [],
        "sat_passed": False,
        "adapter_present": True,
        "adapter_required": False,
        "self_issued": False,
        "instruction": "acknowledge the routed rules",
    }


def _entries_of(corpus: Any) -> List[Dict[str, Any]]:
    if isinstance(corpus, dict):
        entries = corpus.get("entries")
    else:
        entries = corpus
    if not isinstance(entries, list):
        return []
    return entries


def validate_receipt_corpus(corpus: Any) -> Tuple[List[str],
                                                  List[Dict[str, Any]]]:
    """Validate the frozen receipt fixture oracle.

    Returns (findings, entries); an empty findings list means
    the corpus is a valid frozen oracle: frozen marker set,
    stable provenance, at least 12 entries, unique well-formed
    IDs, every entry computing its expected rule and verdict,
    and all 12 receipt rules covered.
    """
    if isinstance(corpus, dict):
        if corpus.get("_frozen") is not True:
            return (["receipt corpus is not frozen: set "
                     "\"_frozen\": true"], [])
        provenance = str(corpus.get("_provenance", ""))
        if "Stage 53 #144" not in provenance:
            return (["receipt corpus provenance must name "
                      "\"Stage 53 #144\""], [])
    elif not isinstance(corpus, list):
        return (["receipt corpus must be a JSON object with an "
                 "'entries' array (or a bare array)"], [])
    entries = _entries_of(corpus)
    findings: List[str] = []
    if len(entries) < 12:
        findings.append("receipt corpus holds %d entries, want "
                        "at least 12" % len(entries))
    seen: Dict[str, int] = {}
    covered = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            findings.append("entries[%d] is not a mapping" % index)
            continue
        cid = str(entry.get("id", ""))
        if not _ENTRY_ID_RE.match(cid):
            findings.append("entry %r: id is not "
                            "standards-receipt.<class>.<nn>" % cid)
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
                            "frozen Stage 53 receipt rule"
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
        result = issue(entry.get("attempt", {}))
        if result.rule != rule:
            findings.append("entry %s: expected_rule %r != "
                            "issue %r" % (cid, rule, result.rule))
        if result.verdict != entry.get("expected_verdict"):
            findings.append("entry %s: expected_verdict %r != "
                            "issue %r" % (cid, entry.get(
                                "expected_verdict"),
                                result.verdict))
    for rule in RULES:
        if rule not in covered:
            findings.append("rule %r has no entries (all 12 "
                            "receipt rules are required)"
                            % rule)
    return findings, entries
