"""Stage 40b Standard half: the post-GREEN simplifier pilot gate.

An existing reputable simplifier runs as an on-demand role AFTER
a qualified Mold is GREEN — never as an always-loaded resident
plugin, never before GREEN, never without a fresh Verifier
full-Mold rerun plus quality-gate rerun afterwards. ``decide``
maps one simplification proposal to its verdict (PROCEED with
scope limits, or REFUSE with repair guidance);
``validate_simplifier_corpus`` checks the frozen oracle.
Proposal fields are plain data; missing keys fall back to total
defaults, never a crash.

Frozen gate rules, in check order (first hit refuses)::

  pre-green        — Mold not GREEN (activation only after GREEN)
  resident-plugin  — resident/always-loaded activation refused
  scope-breach     — write scope exceeds Builder diff or size cap
  contract-change  — public contract or semantics changed
  unevidenced      — new abstraction without reduction evidence
  no-rerun         — no fresh Verifier full-Mold + quality rerun

A proposal clearing every rule is PROCEED with before/after
evidence recorded (logical LOC, complexity, duplication, review
effort, regressions, model/context cost). Findings are repair
guidance (rule + message + excerpt), never an error:
``FINDING_FIELDS`` names the five required keys,
``SEVERITIES`` names the allowed severities, and
``validate_finding`` returns repair strings (empty means
valid). Pure functions: no I/O, no subprocess, no network —
proposals in, verdicts out. Advisory pilot only: promotion or
eject requires owner review after a representative sample.
"""

from typing import Any, Dict, List, Optional, Tuple

import re as _re

# Frozen gate rules, in check order.
RULES = (
    "pre-green",
    "resident-plugin",
    "scope-breach",
    "contract-change",
    "unevidenced",
    "no-rerun",
)

VERDICTS = ("PROCEED", "REFUSE")

SEVERITIES = ("blocker", "major", "minor")

FINDING_FIELDS = ("id", "rule", "finding", "severity", "excerpt")

EVIDENCE_FIELDS = ("loc_before", "loc_after", "complexity_before",
                   "complexity_after", "duplication_before",
                   "duplication_after", "regressions",
                   "model_cost_note")

# Max added lines the simplifier may touch beyond the Builder diff.
DIFF_SIZE_CAP = 200

# Entry-ID shape for the frozen oracle.
_ENTRY_ID_RE = _re.compile(r"^simplifier-pilot\.[a-z-]+\.\d{2}$")


def _make_finding(rule: str, message: str, excerpt: str,
                  severity: str = "major") -> Dict[str, str]:
    """Build one structured simplifier finding dict."""
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
        repairs.append("finding rule %r is not a frozen Stage 40b "
                       "simplifier rule" % (rule,))
    if "severity" in finding and finding.get("severity") not in SEVERITIES:
        repairs.append("finding severity %r must be "
                       "blocker|major|minor" % (finding.get("severity"),))
    return repairs


def _excerpt(proposal: Dict[str, Any]) -> str:
    """Short evidence excerpt naming the target."""
    target = proposal.get("target")
    if isinstance(target, (str, int, float)) and str(target).strip():
        return str(target)[:200]
    return "(proposal)"


def _normalize_proposal(proposal: Any) -> Dict[str, Any]:
    """Fill total defaults so partial input never crashes."""
    proposal = proposal if isinstance(proposal, dict) else {}
    evidence = proposal.get("evidence")
    return {
        "target": str(proposal.get("target", "")),
        "mold_green": bool(proposal.get("mold_green", False)),
        "qualified": bool(proposal.get("qualified", False)),
        "resident": bool(proposal.get("resident", False)),
        "touches_outside_diff": bool(proposal.get(
            "touches_outside_diff", False)),
        "added_lines": int(proposal.get("added_lines") or 0),
        "changes_contract": bool(proposal.get(
            "changes_contract", False)),
        "changes_semantics": bool(proposal.get(
            "changes_semantics", False)),
        "adds_abstraction": bool(proposal.get(
            "adds_abstraction", False)),
        "reduction_evidence": str(proposal.get(
            "reduction_evidence", "") or ""),
        "verifier_reran": bool(proposal.get(
            "verifier_reran", False)),
        "quality_reran": bool(proposal.get(
            "quality_reran", False)),
        "evidence": dict(evidence) if isinstance(evidence, dict)
        else {},
    }


def _check_green(proposal: Dict[str, Any]) -> List[Dict[str, str]]:
    """Activation gate: only after qualified GREEN."""
    if not proposal["mold_green"] or not proposal["qualified"]:
        return [_make_finding(
            "pre-green",
            "Mold not qualified-GREEN: the simplifier activates "
            "only after GREEN, never before",
            _excerpt(proposal), severity="blocker")]
    return []


def _check_resident(proposal: Dict[str, Any]) -> List[Dict[str, str]]:
    """Residency gate: on-demand role only, never resident."""
    if proposal["resident"]:
        return [_make_finding(
            "resident-plugin",
            "resident always-loaded simplifier refused: run the "
            "simplifier as an on-demand role only",
            _excerpt(proposal), severity="blocker")]
    return []


def _check_scope(proposal: Dict[str, Any]) -> List[Dict[str, str]]:
    """Scope gate: inside the Builder diff and under the cap."""
    if proposal["touches_outside_diff"]:
        return [_make_finding(
            "scope-breach",
            "simplifier touches outside the Builder diff: stay "
            "inside the produced diff",
            _excerpt(proposal))]
    if proposal["added_lines"] > DIFF_SIZE_CAP:
        return [_make_finding(
            "scope-breach",
            "simplifier adds %d lines over the %d-line cap: "
            "narrow the simplification" % (proposal["added_lines"],
                                           DIFF_SIZE_CAP),
            _excerpt(proposal))]
    return []


def _check_contract(proposal: Dict[str, Any]) -> List[Dict[str, str]]:
    """Contract gate: semantics and public contracts preserved."""
    if proposal["changes_semantics"] or proposal["changes_contract"]:
        return [_make_finding(
            "contract-change",
            "simplification changes semantics or a public "
            "contract: preserve both",
            _excerpt(proposal), severity="blocker")]
    return []


def _check_evidence(proposal: Dict[str, Any]) -> List[Dict[str, str]]:
    """Evidence gate: new abstractions need reduction evidence."""
    if proposal["adds_abstraction"] and not proposal[
            "reduction_evidence"].strip():
        return [_make_finding(
            "unevidenced",
            "new abstraction without reduction evidence: record "
            "before/after LOC, complexity, and duplication",
            _excerpt(proposal))]
    return []


def _check_rerun(proposal: Dict[str, Any]) -> List[Dict[str, str]]:
    """Rerun gate: fresh Verifier full-Mold + quality rerun."""
    if not proposal["verifier_reran"] or not proposal["quality_reran"]:
        return [_make_finding(
            "no-rerun",
            "no fresh Verifier full-Mold and quality-gate rerun: "
            "rerun both after simplification",
            _excerpt(proposal), severity="blocker")]
    return []


_CHECKS = (
    _check_green,
    _check_resident,
    _check_scope,
    _check_contract,
    _check_evidence,
    _check_rerun,
)


class SimplifierDecision:
    """One simplifier pilot outcome for one proposal."""

    verdict: str = "REFUSE"
    findings: List[Dict[str, str]] = []  # type: ignore[assignment]

    def __init__(self, verdict: str = "REFUSE",
                 findings: Optional[List[Dict[str, str]]] = None):
        self.verdict = verdict
        self.findings = list(findings or [])


def decide(proposal: Any) -> SimplifierDecision:
    """Map one simplification proposal to its verdict.

    All six frozen gates run in check order; the first hit
    refuses. A proposal clearing every gate is PROCEED with its
    before/after evidence recorded. Pure function: no I/O,
    deterministic in its input. This decides; it never
    simplifies, never edits, never promotes.
    """
    normalized = _normalize_proposal(proposal)
    for check in _CHECKS:
        findings = check(normalized)
        if findings:
            return SimplifierDecision(
                verdict="REFUSE", findings=findings)
    return SimplifierDecision(verdict="PROCEED", findings=[])


def clean_proposal() -> Dict[str, Any]:
    """One clean simplification proposal (PROCEED).

    Qualified-GREEN Mold, on-demand role, inside the diff and
    under the cap, contracts preserved, reduction evidence
    recorded, fresh Verifier and quality reruns done.
    Callers mutate one dimension per test.
    """
    return {
        "target": "tools/demo.py",
        "mold_green": True,
        "qualified": True,
        "resident": False,
        "touches_outside_diff": False,
        "added_lines": 40,
        "changes_contract": False,
        "changes_semantics": False,
        "adds_abstraction": True,
        "reduction_evidence": "LOC 120->90, complexity 9->6, "
                              "duplication 3->0 blocks",
        "verifier_reran": True,
        "quality_reran": True,
        "evidence": {
            "loc_before": 120, "loc_after": 90,
            "complexity_before": 9, "complexity_after": 6,
            "duplication_before": 3, "duplication_after": 0,
            "regressions": 0,
            "model_cost_note": "one on-demand call, 2k tokens",
        },
    }


def _entries_of(corpus: Any) -> List[Dict[str, Any]]:
    if isinstance(corpus, dict):
        entries = corpus.get("entries")
    else:
        entries = corpus
    if not isinstance(entries, list):
        return []
    return entries


def validate_simplifier_corpus(corpus: Any) -> Tuple[List[str],
                                                     List[Dict[str, Any]]]:
    """Validate the frozen simplifier fixture oracle.

    Returns (findings, entries); an empty findings list means
    the corpus is a valid frozen oracle: frozen marker set,
    stable provenance, at least 7 entries, unique well-formed
    IDs, every entry computing its expected rules and verdict,
    and all 6 simplifier rules covered.
    """
    if isinstance(corpus, dict):
        if corpus.get("_frozen") is not True:
            return (["simplifier corpus is not frozen: set "
                     "\"_frozen\": true"], [])
        provenance = str(corpus.get("_provenance", ""))
        if "Stage 40b #131" not in provenance:
            return (["simplifier corpus provenance must name "
                      "\"Stage 40b #131\""], [])
    elif not isinstance(corpus, list):
        return (["simplifier corpus must be a JSON object with an "
                 "'entries' array (or a bare array)"], [])
    entries = _entries_of(corpus)
    findings: List[str] = []
    if len(entries) < 7:
        findings.append("simplifier corpus holds %d entries, want "
                        "at least 7" % len(entries))
    seen: Dict[str, int] = {}
    covered = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            findings.append("entries[%d] is not a mapping" % index)
            continue
        cid = str(entry.get("id", ""))
        if not _ENTRY_ID_RE.match(cid):
            findings.append("entry %r: id is not "
                            "simplifier-pilot.<class>.<nn>" % cid)
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
        if "expected_verdict" not in entry:
            findings.append("entry %s: expected_verdict is required"
                            % cid)
        elif entry.get("expected_verdict") not in VERDICTS:
            findings.append("entry %s: expected_verdict %r is not "
                            "a frozen verdict" % (cid, entry.get(
                                "expected_verdict")))
            continue
        result = decide(entry.get("proposal", {}))
        computed = sorted({f["rule"] for f in result.findings})
        if sorted(str(r) for r in expected) != computed:
            findings.append("entry %s: expected_rules %r != "
                            "decide %r"
                            % (cid, sorted(str(r)
                                           for r in expected),
                               computed))
        if entry.get("expected_verdict") != result.verdict:
            findings.append("entry %s: expected_verdict %r != "
                            "decide %r" % (cid, entry.get(
                                "expected_verdict"),
                                result.verdict))
    for rule in RULES:
        if rule not in covered:
            findings.append("rule %r has no entries (all 6 "
                            "simplifier rules are required)"
                            % rule)
    return findings, entries
