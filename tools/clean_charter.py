"""Stage 36 Standard half: the Clean Implementation Charter.

A concise, reviewable contract stating what minimum correct, clear,
tidy implementation means for every Builder change — without a
resident, always-loaded generic clean-code skill. The charter is a
checklist, not taste: each rule names the forbidden shape, the
allowed exception, and (where checkable in this repo) the
Stage 37-owned stack tooling that enforces it. Rules NEVER
authorize unrelated cleanup riding a behavior-focused change.

Charter rule IDs (frozen, first listed first checked)::

  CLEAN-1  no wrapper layer without a behavioral reason
  CLEAN-2  no duplicate implementation of one behavior
  CLEAN-3  no speculative configuration or option
  CLEAN-4  no mixed-responsibility unit (split by behavior)
  CLEAN-5  no dead code (unreached, unused, commented-out)
  CLEAN-6  no unrelated cleanup riding a behavior change
  CLEAN-7  abstractions stay tiny and justified (exception path)

A finding is repair guidance (rule + message + excerpt), never an
error: ``FINDING_FIELDS`` names the five required keys,
``SEVERITIES`` names the allowed severities, and
``validate_finding`` returns repair strings (empty means valid).
``classify`` maps one change description to its rule hits as
plain data; ``validate_charter_corpus`` checks the frozen oracle.
Pure functions: no I/O, deterministic in their inputs.
"""

from typing import Any, Dict, List, Optional, Tuple

import re as _re

# Frozen charter rule IDs, in check order.
RULES = (
    "CLEAN-1",
    "CLEAN-2",
    "CLEAN-3",
    "CLEAN-4",
    "CLEAN-5",
    "CLEAN-6",
    "CLEAN-7",
)

SEVERITIES = ("blocker", "major", "minor")

FINDING_FIELDS = ("id", "rule", "finding", "severity", "excerpt")

# Stack tooling that enforces each rule lives in Stage 37; the
# charter names the owner so no rule is mistaken for taste.
RULE_TOOLING = {
    "CLEAN-1": "Stage 37 architecture tests (dependency direction)",
    "CLEAN-2": "Stage 37 duplication scanner",
    "CLEAN-3": "Stage 37 dead-option scan + Stage 39 dependency contract",
    "CLEAN-4": "Stage 37 architecture tests + size-profile ratchet",
    "CLEAN-5": "Stage 37 dead-code scan (dead export/unreached)",
    "CLEAN-6": "review checklist (no tooling; human confirms scope)",
    "CLEAN-7": "review checklist (exception path, never a bypass)",
}

_ENTRY_ID_RE = _re.compile(r"^clean-charter\.[a-z-]+\.\d{2}$")


def _make_finding(rule: str, message: str, excerpt: str,
                  severity: str = "major") -> Dict[str, str]:
    """Build one structured charter finding dict."""
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
        repairs.append("finding rule %r is not a frozen Stage 36 "
                       "charter rule" % (rule,))
    if "severity" in finding and finding.get("severity") not in SEVERITIES:
        repairs.append("finding severity %r must be "
                       "blocker|major|minor" % (finding.get("severity"),))
    return repairs


def _excerpt(change: Dict[str, Any]) -> str:
    """Short evidence excerpt naming the touched unit."""
    for key in ("unit", "file", "name", "claim"):
        value = change.get(key)
        if isinstance(value, (str, int, float)) and str(value).strip():
            return str(value)[:200]
    return "(change)"


def _is_justified(change: Dict[str, Any]) -> bool:
    """True when the change carries an explicit behavioral reason.

    Justification is data, not prose sentiment: a non-empty
    ``reason`` naming the behavior (or ``safety_layer`` True for
    a necessary safety boundary) exempts the shape from its
    rule. An empty or missing reason never exempts.
    """
    if change.get("safety_layer") is True:
        return True
    reason = change.get("reason")
    return isinstance(reason, str) and bool(reason.strip())


def _check_wrapper(change: Dict[str, Any]) -> List[Dict[str, str]]:
    """CLEAN-1: a layer that adds no behavior needs a reason."""
    if change.get("adds_layer") is True and not change.get("adds_behavior", False):
        if not _is_justified(change):
            return [_make_finding(
                "CLEAN-1",
                "wrapper layer adds no behavior: name the behavioral "
                "reason or remove the layer",
                _excerpt(change))]
    return []


def _check_duplicate(change: Dict[str, Any]) -> List[Dict[str, str]]:
    """CLEAN-2: one behavior keeps one implementation."""
    if change.get("duplicates_behavior") is True:
        if not _is_justified(change):
            return [_make_finding(
                "CLEAN-2",
                "duplicate implementation of one behavior: reuse the "
                "canonical implementation or name the behavioral "
                "reason for a second one",
                _excerpt(change))]
    return []


def _check_speculative(change: Dict[str, Any]) -> List[Dict[str, str]]:
    """CLEAN-3: options and configuration need a current caller."""
    if change.get("adds_option") is True and not change.get("has_caller", False):
        if not _is_justified(change):
            return [_make_finding(
                "CLEAN-3",
                "speculative configuration with no current caller: "
                "add the option with its caller or not at all",
                _excerpt(change))]
    return []


def _check_mixed(change: Dict[str, Any]) -> List[Dict[str, str]]:
    """CLEAN-4: mixed responsibilities split by behavior."""
    responsibilities = change.get("responsibilities")
    if isinstance(responsibilities, list) and len(responsibilities) > 1:
        if not _is_justified(change):
            return [_make_finding(
                "CLEAN-4",
                "mixed-responsibility unit %r: split by behavior so "
                "each unit owns one outcome"
                % (sorted(str(r) for r in responsibilities),),
                _excerpt(change))]
    return []


def _check_dead(change: Dict[str, Any]) -> List[Dict[str, str]]:
    """CLEAN-5: dead code is removed, never shipped alongside."""
    if change.get("is_dead") is True:
        return [_make_finding(
            "CLEAN-5",
            "dead code (unreached, unused, or commented-out): "
            "delete it; version history keeps the record",
            _excerpt(change))]
    return []


def _check_rider(change: Dict[str, Any]) -> List[Dict[str, str]]:
    """CLEAN-6: unrelated cleanup never rides a behavior change."""
    if change.get("touches_unrelated") is True:
        return [_make_finding(
            "CLEAN-6",
            "unrelated cleanup rides a behavior-focused change: "
            "move it to its own thin Issue",
            _excerpt(change))]
    return []


def _check_abstraction(change: Dict[str, Any]) -> List[Dict[str, str]]:
    """CLEAN-7: tiny abstractions need a stated reason; the safety
    layer is the always-allowed exception path, never a bypass."""
    if change.get("adds_abstraction") is True:
        if not _is_justified(change):
            return [_make_finding(
                "CLEAN-7",
                "abstraction without a stated behavioral reason: "
                "name the shared behavior or inline the code",
                _excerpt(change))]
    return []


_CHECKS = (
    _check_wrapper,
    _check_duplicate,
    _check_speculative,
    _check_mixed,
    _check_dead,
    _check_rider,
    _check_abstraction,
)


def _normalize_change(change: Any) -> Dict[str, Any]:
    """Fill total defaults so partial input never crashes."""
    change = change if isinstance(change, dict) else {}
    return {
        "unit": str(change.get("unit", "")),
        "adds_layer": bool(change.get("adds_layer", False)),
        "adds_behavior": bool(change.get("adds_behavior", False)),
        "duplicates_behavior": bool(change.get(
            "duplicates_behavior", False)),
        "adds_option": bool(change.get("adds_option", False)),
        "has_caller": bool(change.get("has_caller", False)),
        "responsibilities": list(change.get("responsibilities") or [])
        if isinstance(change.get("responsibilities"), list) else [],
        "is_dead": bool(change.get("is_dead", False)),
        "touches_unrelated": bool(change.get(
            "touches_unrelated", False)),
        "adds_abstraction": bool(change.get(
            "adds_abstraction", False)),
        "reason": change.get("reason", ""),
        "safety_layer": bool(change.get("safety_layer", False)),
    }


class CharterResult:
    """One charter classification outcome for one change."""

    clean: bool = False
    findings: List[Dict[str, str]] = []  # type: ignore[assignment]

    def __init__(self, clean: bool = False,
                 findings: Optional[List[Dict[str, str]]] = None):
        self.clean = clean
        self.findings = list(findings or [])


def classify(change: Any) -> CharterResult:
    """Map one change description to its charter rule hits.

    All seven frozen rules run in order; any finding means the
    change is not clean. A fully clean change returns
    ``clean=True`` with zero findings. Pure function: no I/O,
    deterministic in its input. This classifies; it never
    rewrites code and never authorizes cleanup.
    """
    normalized = _normalize_change(change)
    findings: List[Dict[str, str]] = []
    for check in _CHECKS:
        findings.extend(check(normalized))
    if findings:
        return CharterResult(clean=False, findings=findings)
    return CharterResult(clean=True, findings=[])


def _entries_of(corpus: Any) -> List[Dict[str, Any]]:
    if isinstance(corpus, dict):
        entries = corpus.get("entries")
    else:
        entries = corpus
    if not isinstance(entries, list):
        return []
    return entries


def validate_charter_corpus(corpus: Any) -> Tuple[List[str],
                                                  List[Dict[str, Any]]]:
    """Validate the frozen charter fixture oracle.

    Returns (findings, entries); an empty findings list means
    the corpus is a valid frozen oracle: frozen marker set,
    stable provenance, at least 8 entries, unique well-formed
    IDs, every entry computing its expected rules and clean
    flag, and all 7 charter rules covered.
    """
    if isinstance(corpus, dict):
        if corpus.get("_frozen") is not True:
            return (["charter corpus is not frozen: set "
                     "\"_frozen\": true"], [])
        provenance = str(corpus.get("_provenance", ""))
        if "Stage 36 #127" not in provenance:
            return (["charter corpus provenance must name "
                      "\"Stage 36 #127\""], [])
    elif not isinstance(corpus, list):
        return (["charter corpus must be a JSON object with an "
                 "'entries' array (or a bare array)"], [])
    entries = _entries_of(corpus)
    findings: List[str] = []
    if len(entries) < 8:
        findings.append("charter corpus holds %d entries, want "
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
                            "clean-charter.<class>.<nn>" % cid)
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
        if "expected_clean" not in entry:
            findings.append("entry %s: expected_clean is required"
                            % cid)
        result = classify(entry.get("change", {}))
        computed = sorted({f["rule"] for f in result.findings})
        if sorted(str(r) for r in expected) != computed:
            findings.append("entry %s: expected_rules %r != "
                            "classify %r"
                            % (cid, sorted(str(r)
                                           for r in expected),
                               computed))
        if bool(entry.get("expected_clean")) != result.clean:
            findings.append("entry %s: expected_clean %r != "
                            "classify %r" % (cid, entry.get(
                                "expected_clean"),
                                result.clean))
    for rule in RULES:
        if rule not in covered:
            findings.append("rule %r has no entries (all 7 "
                            "charter rules are required)"
                            % rule)
    return findings, entries


def clean_change() -> Dict[str, Any]:
    """One clean charter change (CLEAN with zero findings).

    A behavior-focused change that adds behavior in place with
    no extra layer, no duplication, no speculative option, one
    responsibility, live code, no unrelated touch, and no new
    abstraction. Callers mutate one dimension per test.
    """
    return {
        "unit": "tools/example.py",
        "adds_layer": False,
        "adds_behavior": True,
        "duplicates_behavior": False,
        "adds_option": False,
        "has_caller": True,
        "responsibilities": ["one-outcome"],
        "is_dead": False,
        "touches_unrelated": False,
        "adds_abstraction": False,
        "reason": "",
        "safety_layer": False,
    }
