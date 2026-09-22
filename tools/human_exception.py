"""Stage 51 Standard half: human-by-exception and no default agent councils.

Autonomy stays high and coordination stays low with one
accountable producer plus targeted independent evaluation.
Multi-agent teams/councils are never the default: they need an
explicit task hypothesis, a token budget, an expected quality
gain, and an eval before use. Conversational consensus among
agents is never proof of correctness. The orchestrator never
creates speculative work to stay busy. ``decide`` maps one
topology proposal to PRODUCE / CONSULT / COUNCIL / ESCALATE /
HOLD; ``validate_topology_corpus`` checks the frozen oracle.
Proposals are plain data; missing keys fall back to total
defaults, never a crash.

Frozen verdicts: PRODUCE, CONSULT, COUNCIL, ESCALATE, HOLD.

Frozen rules, in check order (first hit decides)::

  ambiguous-owner    — ambiguous owner decision: ESCALATE, never
                       guess (human-by-exception trigger).
  no-ready-work      — nothing ready: HOLD, never speculative
                       busywork.
  false-escalation   — escalation without a trigger: HOLD the
                       producer on course.
  generic-council    — generic council without hypothesis,
                       budget, gain, and eval: HOLD (token burn
                       refused).
  conflicting-advice — conflicting recommendations: CONSULT
                       one targeted critic, never a council.
  competitive-mold   — competitive implementations under one
                       shared Mold: COUNCIL explicitly approved.
  approved-council   — council with hypothesis, budget, gain,
                       eval: COUNCIL.
  intervention-due   — human-intervention metric breached:
                       ESCALATE to the owner.
  clean-produce      — normal autonomous slice: PRODUCE with
                       one producer plus targeted evaluation.

A normal slice is PRODUCE. Findings use the standard five keys
via ``FINDING_FIELDS``; ``SEVERITIES`` names the allowed
severities; ``validate_finding`` returns repair strings (empty
means valid). Pure functions: no I/O, no subprocess, no
network — proposals in, verdicts out. The owner may always
request teams explicitly; the default stays one producer.
"""

from typing import Any, Dict, List, Optional, Tuple

import re as _re

# Frozen topology verdicts.
VERDICTS = (
    "PRODUCE",
    "CONSULT",
    "COUNCIL",
    "ESCALATE",
    "HOLD",
)

SEVERITIES = ("blocker", "major", "minor")

FINDING_FIELDS = ("id", "rule", "finding", "severity", "excerpt")

# Frozen topology rules, in check order.
RULES = (
    "ambiguous-owner",
    "no-ready-work",
    "false-escalation",
    "generic-council",
    "conflicting-advice",
    "competitive-mold",
    "approved-council",
    "intervention-due",
    "clean-produce",
)

# Verdict each rule carries.
RULE_VERDICTS = {
    "ambiguous-owner": "ESCALATE",
    "no-ready-work": "HOLD",
    "false-escalation": "HOLD",
    "generic-council": "HOLD",
    "conflicting-advice": "CONSULT",
    "competitive-mold": "COUNCIL",
    "approved-council": "COUNCIL",
    "intervention-due": "ESCALATE",
    "clean-produce": "PRODUCE",
}

# Entry-ID shape for the frozen oracle.
_ENTRY_ID_RE = _re.compile(r"^human-exception\.[a-z-]+\.\d{2}$")


def _make_finding(rule: str, message: str, excerpt: str,
                  severity: str = "major") -> Dict[str, str]:
    """Build one structured topology finding dict."""
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
        repairs.append("finding rule %r is not a frozen Stage 51 "
                       "topology rule" % (rule,))
    if "severity" in finding and finding.get("severity") not in SEVERITIES:
        repairs.append("finding severity %r must be "
                       "blocker|major|minor" % (finding.get("severity"),))
    return repairs


def _excerpt(proposal: Dict[str, Any]) -> str:
    """Short evidence excerpt naming the task."""
    for key in ("task", "slice", "council"):
        value = proposal.get(key)
        if isinstance(value, (str, int, float)) and str(value).strip():
            return str(value)[:200]
    return "(topology)"


def _normalize_proposal(proposal: Any) -> Dict[str, Any]:
    """Fill total defaults so partial input never crashes."""
    proposal = proposal if isinstance(proposal, dict) else {}
    return {
        "task": str(proposal.get("task", "")),
        "ready_work": bool(proposal.get("ready_work", False)),
        "owner_ambiguous": bool(proposal.get(
            "owner_ambiguous", False)),
        "escalation_trigger": bool(proposal.get(
            "escalation_trigger", False)),
        "council_proposed": bool(proposal.get(
            "council_proposed", False)),
        "hypothesis": str(proposal.get("hypothesis", "") or ""),
        "budget": int(proposal.get("budget") or 0),
        "expected_gain": str(proposal.get(
            "expected_gain", "") or ""),
        "eval_planned": bool(proposal.get(
            "eval_planned", False)),
        "conflicting_advice": bool(proposal.get(
            "conflicting_advice", False)),
        "shared_mold": bool(proposal.get(
            "shared_mold", False)),
        "competitive": bool(proposal.get(
            "competitive", False)),
        "owner_requested_team": bool(proposal.get(
            "owner_requested_team", False)),
        "interventions": int(proposal.get("interventions") or 0),
        "intervention_budget": int(proposal.get(
            "intervention_budget") or 3),
    }


class TopologyDecision:
    """One topology outcome for one proposal."""

    verdict: str = "HOLD"
    rule: str = "clean-produce"
    findings: List[Dict[str, str]] = []  # type: ignore[assignment]

    def __init__(self, verdict: str = "HOLD",
                 rule: str = "clean-produce",
                 findings: Optional[List[Dict[str, str]]] = None):
        self.verdict = verdict
        self.rule = rule
        self.findings = list(findings or [])


def _decide(rule: str, message: str, tag: str,
            severity: str = "major") -> TopologyDecision:
    return TopologyDecision(
        verdict=RULE_VERDICTS[rule], rule=rule,
        findings=[_make_finding(rule, message, tag,
                                severity=severity)])


def _council_approved(item: Dict[str, Any]) -> bool:
    """True when the council carries hypothesis, budget, gain,
    eval — or the owner explicitly requested the team."""
    if item["owner_requested_team"]:
        return True
    return bool(item["hypothesis"].strip()) and item["budget"] > 0 \
        and bool(item["expected_gain"].strip()) \
        and item["eval_planned"]


def decide(proposal: Any) -> TopologyDecision:
    """Map one topology proposal to PRODUCE / CONSULT / COUNCIL /
    ESCALATE / HOLD.

    Ambiguous owners escalate; empty queues hold; triggerless
    escalations hold; generic councils hold; conflicting advice
    consults one critic; competitive shared-Mold work and fully
    justified councils convene; breached intervention budgets
    escalate; normal slices produce. Pure function: no I/O,
    deterministic in its input. This decides; it never spawns
    agents, never counts consensus as proof.
    """
    item = _normalize_proposal(proposal)
    tag = _excerpt(item)
    if item["owner_ambiguous"]:
        return _decide(
            "ambiguous-owner",
            "owner decision ambiguous: ESCALATE to the owner, "
            "never guess",
            tag, severity="blocker")
    if not item["ready_work"]:
        return _decide(
            "no-ready-work",
            "no ready work: HOLD, never speculative busywork",
            tag, severity="minor")
    if item["escalation_trigger"] and not item["owner_ambiguous"] \
            and not item["conflicting_advice"] \
            and not item["council_proposed"] \
            and item["interventions"] <= item["intervention_budget"]:
        return _decide(
            "false-escalation",
            "escalation without a trigger: HOLD the producer "
            "on course",
            tag, severity="minor")
    if item["council_proposed"] and not _council_approved(item):
        return _decide(
            "generic-council",
            "generic council without hypothesis, budget, gain, "
            "and eval: HOLD (token burn refused)",
            tag)
    if item["conflicting_advice"]:
        return _decide(
            "conflicting-advice",
            "conflicting recommendations: CONSULT one targeted "
            "critic, never a council",
            tag)
    if item["competitive"] and item["shared_mold"]:
        return _decide(
            "competitive-mold",
            "competitive implementations under one shared Mold: "
            "COUNCIL explicitly approved",
            tag)
    if item["council_proposed"] and _council_approved(item):
        return _decide(
            "approved-council",
            "council with hypothesis, budget, gain, eval: "
            "COUNCIL",
            tag)
    if item["interventions"] > item["intervention_budget"]:
        return _decide(
            "intervention-due",
            "human-intervention metric breached (%d over "
            "budget %d): ESCALATE to the owner"
            % (item["interventions"],
               item["intervention_budget"]),
            tag)
    return _decide(
        "clean-produce",
        "normal autonomous slice: PRODUCE with one producer "
        "plus targeted evaluation",
        tag, severity="minor")


def clean_proposal() -> Dict[str, Any]:
    """One clean topology proposal (PRODUCE).

    Ready work, unambiguous owner, no council, no conflicts,
    interventions within budget. Callers mutate one dimension
    per test.
    """
    return {
        "task": "slice-1",
        "ready_work": True,
        "owner_ambiguous": False,
        "escalation_trigger": False,
        "council_proposed": False,
        "hypothesis": "",
        "budget": 0,
        "expected_gain": "",
        "eval_planned": False,
        "conflicting_advice": False,
        "shared_mold": False,
        "competitive": False,
        "owner_requested_team": False,
        "interventions": 0,
        "intervention_budget": 3,
    }


def _entries_of(corpus: Any) -> List[Dict[str, Any]]:
    if isinstance(corpus, dict):
        entries = corpus.get("entries")
    else:
        entries = corpus
    if not isinstance(entries, list):
        return []
    return entries


def validate_topology_corpus(corpus: Any) -> Tuple[List[str],
                                                   List[Dict[str, Any]]]:
    """Validate the frozen topology fixture oracle.

    Returns (findings, entries); an empty findings list means
    the corpus is a valid frozen oracle: frozen marker set,
    stable provenance, at least 9 entries, unique well-formed
    IDs, every entry computing its expected rule and verdict,
    and all 9 topology rules covered.
    """
    if isinstance(corpus, dict):
        if corpus.get("_frozen") is not True:
            return (["topology corpus is not frozen: set "
                     "\"_frozen\": true"], [])
        provenance = str(corpus.get("_provenance", ""))
        if "Stage 51 #142" not in provenance:
            return (["topology corpus provenance must name "
                      "\"Stage 51 #142\""], [])
    elif not isinstance(corpus, list):
        return (["topology corpus must be a JSON object with an "
                 "'entries' array (or a bare array)"], [])
    entries = _entries_of(corpus)
    findings: List[str] = []
    if len(entries) < 9:
        findings.append("topology corpus holds %d entries, want "
                        "at least 9" % len(entries))
    seen: Dict[str, int] = {}
    covered = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            findings.append("entries[%d] is not a mapping" % index)
            continue
        cid = str(entry.get("id", ""))
        if not _ENTRY_ID_RE.match(cid):
            findings.append("entry %r: id is not "
                            "human-exception.<class>.<nn>" % cid)
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
                            "frozen Stage 51 topology rule"
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
        result = decide(entry.get("proposal", {}))
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
            findings.append("rule %r has no entries (all 9 "
                            "topology rules are required)"
                            % rule)
    return findings, entries
