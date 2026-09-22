"""Stage 48 Standard half: planned context rotation and zero-compaction
recovery.

Automatically checkpoint and start a clean role/provider before
context compaction or pollution: the rotation sequence is
checkpoint -> lease handoff -> capsule -> fresh session ->
HAT/SAT acceptance -> resume. ``decide`` maps one rotation
signal to ROTATE / HOLD / FREEZE / RECOVER;
``validate_rotation_corpus`` checks the frozen oracle. Signals
are plain data; missing keys fall back to total defaults, never
a crash.

Frozen rotation sequence (each step gates the next)::

  checkpointed -> lease-handed -> capsule-written ->
  session-fresh -> accepted -> resumed

Frozen rules, in check order (first hit decides)::

  compacted          — compaction already occurred: FREEZE
                       mutation until wake proves state (never
                       recover *through* compaction).
  polluted           — polluted history: RECOVER from capsule.
  read-only-bound    — ROTATE_NOW_READ_ONLY footprint: rotate
                       now, read-only until rotated.
  boundary-due       — role/phase boundary: ROTATE at boundary
                       (Spec->Mold, Mold->Builder, GREEN->Verifier,
                       review->Remediator, merge->next-Issue).
  imminent-compact   — imminent provider compaction: ROTATE now.
  overflow-output    — tool-output overflow: ROTATE with a
                       bounded capsule.
  missing-checkpoint — rotation without checkpoint: refuse and
                       checkpoint first.
  provider-switch    — provider switch mid-flight: rotate with
                       cross-provider acceptance.
  canary-missing     — automatic mode without passed
                       provider-specific canaries: HOLD in
                       advisory/controlled mode.
  clean-rotate       — none of the above: ROTATE on plan.

A clean planned rotation is ROTATE. Findings use the standard
five keys via ``FINDING_FIELDS``; ``SEVERITIES`` names the
allowed severities; ``validate_finding`` returns repair strings
(empty means valid). Pure functions: no I/O, no subprocess, no
network — signals in, verdicts out. PreCompress/compaction
hooks are emergency tripwires only; automatic mode waits for
provider canaries (advisory/controlled until then).
"""

from typing import Any, Dict, List, Optional, Tuple

import re as _re

# Frozen rotation sequence steps.
SEQUENCE = (
    "checkpointed",
    "lease-handed",
    "capsule-written",
    "session-fresh",
    "accepted",
    "resumed",
)

VERDICTS = ("ROTATE", "HOLD", "FREEZE", "RECOVER")

SEVERITIES = ("blocker", "major", "minor")

FINDING_FIELDS = ("id", "rule", "finding", "severity", "excerpt")

# Frozen rotation rules, in check order.
RULES = (
    "compacted",
    "polluted",
    "read-only-bound",
    "boundary-due",
    "imminent-compact",
    "overflow-output",
    "missing-checkpoint",
    "provider-switch",
    "canary-missing",
    "clean-rotate",
)

# Verdict each rule carries.
RULE_VERDICTS = {
    "compacted": "FREEZE",
    "polluted": "RECOVER",
    "read-only-bound": "ROTATE",
    "boundary-due": "ROTATE",
    "imminent-compact": "ROTATE",
    "overflow-output": "ROTATE",
    "missing-checkpoint": "HOLD",
    "provider-switch": "ROTATE",
    "canary-missing": "HOLD",
    "clean-rotate": "ROTATE",
}

# Entry-ID shape for the frozen oracle.
_ENTRY_ID_RE = _re.compile(r"^context-rotation\.[a-z-]+\.\d{2}$")


def _make_finding(rule: str, message: str, excerpt: str,
                  severity: str = "major") -> Dict[str, str]:
    """Build one structured rotation finding dict."""
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
        repairs.append("finding rule %r is not a frozen Stage 48 "
                       "rotation rule" % (rule,))
    if "severity" in finding and finding.get("severity") not in SEVERITIES:
        repairs.append("finding severity %r must be "
                       "blocker|major|minor" % (finding.get("severity"),))
    return repairs


def _excerpt(signal: Dict[str, Any]) -> str:
    """Short evidence excerpt naming the transition."""
    for key in ("transition", "phase", "slice"):
        value = signal.get(key)
        if isinstance(value, (str, int, float)) and str(value).strip():
            return str(value)[:200]
    return "(rotation)"


def _normalize_signal(signal: Any) -> Dict[str, Any]:
    """Fill total defaults so partial input never crashes."""
    signal = signal if isinstance(signal, dict) else {}
    steps = signal.get("steps_done")
    return {
        "transition": str(signal.get("transition", "")),
        "footprint_status": str(signal.get(
            "footprint_status", "") or ""),
        "boundary": bool(signal.get("boundary", False)),
        "compaction_imminent": bool(signal.get(
            "compaction_imminent", False)),
        "compaction_done": bool(signal.get(
            "compaction_done", False)),
        "polluted": bool(signal.get("polluted", False)),
        "tool_overflow": bool(signal.get("tool_overflow", False)),
        "checkpointed": bool(signal.get(
            "checkpointed", False)),
        "provider_switch": bool(signal.get(
            "provider_switch", False)),
        "canaries_passed": bool(signal.get(
            "canaries_passed", False)),
        "automatic": bool(signal.get("automatic", False)),
        "steps_done": list(steps) if isinstance(steps, list)
        else [],
    }


class RotationDecision:
    """One rotation outcome for one signal."""

    verdict: str = "HOLD"
    rule: str = "clean-rotate"
    findings: List[Dict[str, str]] = []  # type: ignore[assignment]

    def __init__(self, verdict: str = "HOLD",
                 rule: str = "clean-rotate",
                 findings: Optional[List[Dict[str, str]]] = None):
        self.verdict = verdict
        self.rule = rule
        self.findings = list(findings or [])


def _decide(rule: str, message: str, tag: str,
            severity: str = "major") -> RotationDecision:
    return RotationDecision(
        verdict=RULE_VERDICTS[rule], rule=rule,
        findings=[_make_finding(rule, message, tag,
                                severity=severity)])


def decide(signal: Any) -> RotationDecision:
    """Map one rotation signal to ROTATE / HOLD / FREEZE /
    RECOVER.

    Compaction-done freezes; pollution recovers; read-only
    bounds, boundaries, imminent compaction, overflows, and
    provider switches rotate; missing checkpoints and missing
    canaries hold; a clean plan rotates. The sequence gates
    order: resume requires every prior step. Pure function: no
    I/O, deterministic in its input. This decides; it never
    rotates, never checkpoints, never resumes.
    """
    item = _normalize_signal(signal)
    tag = _excerpt(item)
    if item["compaction_done"]:
        return _decide(
            "compacted",
            "compaction already occurred: FREEZE mutation until "
            "wake/reconciliation proves state",
            tag, severity="blocker")
    if item["polluted"]:
        return _decide(
            "polluted",
            "polluted history: RECOVER from the capsule, never "
            "summarize",
            tag)
    if item["footprint_status"] == "ROTATE_NOW_READ_ONLY":
        return _decide(
            "read-only-bound",
            "footprint at the read-only bound: rotate now, "
            "read-only until rotated",
            tag)
    if item["boundary"]:
        return _decide(
            "boundary-due",
            "role/phase boundary %r: rotate at the boundary "
            "with checkpoint, lease, capsule, acceptance"
            % item["transition"],
            tag)
    if item["compaction_imminent"]:
        return _decide(
            "imminent-compact",
            "provider compaction imminent: rotate now before "
            "the tripwire fires",
            tag)
    if item["tool_overflow"]:
        return _decide(
            "overflow-output",
            "tool-output overflow: rotate with a bounded "
            "capsule",
            tag)
    if not item["checkpointed"]:
        return _decide(
            "missing-checkpoint",
            "rotation without checkpoint: checkpoint first, "
            "then rotate",
            tag)
    if item["provider_switch"]:
        return _decide(
            "provider-switch",
            "provider switch mid-flight: rotate with "
            "cross-provider acceptance",
            tag)
    if item["automatic"] and not item["canaries_passed"]:
        return _decide(
            "canary-missing",
            "automatic mode without passed provider canaries: "
            "HOLD in advisory/controlled mode",
            tag)
    return _decide(
        "clean-rotate",
        "planned rotation: checkpoint, lease, capsule, fresh "
        "session, acceptance, resume",
        tag, severity="minor")


def clean_signal() -> Dict[str, Any]:
    """One clean rotation signal (ROTATE).

    Checkpointed plan with canaries passed, no compaction,
    no pollution, no switch. Callers mutate one dimension per
    test.
    """
    return {
        "transition": "mold-to-builder",
        "footprint_status": "HEALTHY",
        "boundary": False,
        "compaction_imminent": False,
        "compaction_done": False,
        "polluted": False,
        "tool_overflow": False,
        "checkpointed": True,
        "provider_switch": False,
        "canaries_passed": True,
        "automatic": False,
        "steps_done": list(SEQUENCE),
    }


def _entries_of(corpus: Any) -> List[Dict[str, Any]]:
    if isinstance(corpus, dict):
        entries = corpus.get("entries")
    else:
        entries = corpus
    if not isinstance(entries, list):
        return []
    return entries


def validate_rotation_corpus(corpus: Any) -> Tuple[List[str],
                                                   List[Dict[str, Any]]]:
    """Validate the frozen rotation fixture oracle.

    Returns (findings, entries); an empty findings list means
    the corpus is a valid frozen oracle: frozen marker set,
    stable provenance, at least 10 entries, unique well-formed
    IDs, every entry computing its expected rule and verdict,
    and all 10 rotation rules covered.
    """
    if isinstance(corpus, dict):
        if corpus.get("_frozen") is not True:
            return (["rotation corpus is not frozen: set "
                     "\"_frozen\": true"], [])
        provenance = str(corpus.get("_provenance", ""))
        if "Stage 48 #139" not in provenance:
            return (["rotation corpus provenance must name "
                      "\"Stage 48 #139\""], [])
    elif not isinstance(corpus, list):
        return (["rotation corpus must be a JSON object with an "
                 "'entries' array (or a bare array)"], [])
    entries = _entries_of(corpus)
    findings: List[str] = []
    if len(entries) < 10:
        findings.append("rotation corpus holds %d entries, want "
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
                            "context-rotation.<class>.<nn>" % cid)
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
                            "frozen Stage 48 rotation rule"
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
        result = decide(entry.get("signal", {}))
        if result.rule != rule:
            findings.append("entry %s: expected_rule %r != "
                            "decide %r" % (cid, rule, result.rule))
        if result.verdict != entry.get("expected_verdict"):
            findings.append("entry %s: expected_verdict %r != "
                            "decide %r" % (cid, entry.get(
                                "expected_verdict"),
                                result.verdict))
    for rule in RULES:
        if rule not in covered:
            findings.append("rule %r has no entries (all 10 "
                            "rotation rules are required)"
                            % rule)
    return findings, entries
