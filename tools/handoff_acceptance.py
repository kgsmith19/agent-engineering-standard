"""Stage 45 Standard half: handoff and standards acceptance (HAT/SAT).

A fresh role/session earns write authority only by proving it
holds the exact task, the reconciled state, the applicable
critical rules, and the next action. HAT (handoff acceptance
test) runs on every handoff; SAT (standards acceptance test)
runs selectively — new provider family, R2/R3 work,
privileged/policy paths, or authority change. R0/compact work
needs only a valid route/capabilities check, never ceremonial
SAT. Comparison is against replayed state and the Standards
route, never prompt prose or model recollection. ``accept``
maps one acceptance attempt to ACCEPT or REFUSE;
``validate_acceptance_corpus`` checks the frozen oracle.
Attempts are plain data; missing keys fall back to total
defaults, never a crash.

Frozen rules, in check order (first hit refuses)::

  wrong-phase        — stated phase != replayed phase.
  stale-head         — stated head != reconciled head.
  missing-decision   — required owner decision not recorded.
  protected-omitted  — protected path missing from the
                       accepted scope.
  guardrail-gap      — provider lacks required guard rails.
  prompt-injection   — malicious prompt content overrides
                       task, state, rules, or action.
  sat-required       — SAT trigger present but SAT not passed
                       (new provider, R2/R3, privileged path,
                       authority change).
  cross-provider     — cross-provider restatement diverges.

A clean attempt is ACCEPT with an acceptance receipt (task,
head, rules, action, HAT/SAT kind) bound into the lease and
evidence chain. Findings use the standard five keys via
``FINDING_FIELDS``; ``SEVERITIES`` names the allowed
severities; ``validate_finding`` returns repair strings (empty
means valid). Pure functions: no I/O, no subprocess, no
network — attempts in, verdicts out. This gates writing; it
never selects which rules apply (Stage 52 owns the route).
"""

from typing import Any, Dict, List, Optional, Tuple

import re as _re

# Frozen acceptance rules, in check order.
RULES = (
    "wrong-phase",
    "stale-head",
    "missing-decision",
    "protected-omitted",
    "guardrail-gap",
    "prompt-injection",
    "sat-required",
    "cross-provider",
)

SEVERITIES = ("blocker", "major", "minor")

FINDING_FIELDS = ("id", "rule", "finding", "severity", "excerpt")

# SAT triggers: any one requires a passed SAT (except R0/compact).
SAT_TRIGGERS = (
    "new-provider",
    "high-risk",
    "privileged-path",
    "authority-change",
)

# Entry-ID shape for the frozen oracle.
_ENTRY_ID_RE = _re.compile(r"^handoff-acceptance\.[a-z-]+\.\d{2}$")

_INJECTION_RE = _re.compile(
    r"(ignore (previous|all) instructions|disregard .*instructions|"
    r"override .*rules?|bypass .*gate|reveal .*prompt|system prompt)",
    _re.IGNORECASE)


def _make_finding(rule: str, message: str, excerpt: str,
                  severity: str = "major") -> Dict[str, str]:
    """Build one structured acceptance finding dict."""
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
        repairs.append("finding rule %r is not a frozen Stage 45 "
                       "acceptance rule" % (rule,))
    if "severity" in finding and finding.get("severity") not in SEVERITIES:
        repairs.append("finding severity %r must be "
                       "blocker|major|minor" % (finding.get("severity"),))
    return repairs


def _excerpt(attempt: Dict[str, Any]) -> str:
    """Short evidence excerpt naming the role/task."""
    for key in ("role", "task", "head"):
        value = attempt.get(key)
        if isinstance(value, (str, int, float)) and str(value).strip():
            return str(value)[:200]
    return "(attempt)"


def _normalize_attempt(attempt: Any) -> Dict[str, Any]:
    """Fill total defaults so partial input never crashes."""
    attempt = attempt if isinstance(attempt, dict) else {}
    triggers = attempt.get("sat_triggers")
    return {
        "role": str(attempt.get("role", "")),
        "risk": str(attempt.get("risk", "") or ""),
        "compact": bool(attempt.get("compact", False)),
        "stated_phase": str(attempt.get("stated_phase", "")),
        "replayed_phase": str(attempt.get(
            "replayed_phase", "")),
        "stated_head": str(attempt.get("stated_head", "")),
        "reconciled_head": str(attempt.get(
            "reconciled_head", "")),
        "owner_decision_recorded": bool(attempt.get(
            "owner_decision_recorded", False)),
        "owner_decision_required": bool(attempt.get(
            "owner_decision_required", False)),
        "protected_paths": list(attempt.get("protected_paths")
                                or []) if isinstance(attempt.get(
                                    "protected_paths"), list) else [],
        "accepted_scope": list(attempt.get("accepted_scope")
                               or []) if isinstance(attempt.get(
                                   "accepted_scope"), list) else [],
        "provider_guardrails": bool(attempt.get(
            "provider_guardrails", False)),
        "prompt_text": str(attempt.get("prompt_text", "") or ""),
        "stated_rules": list(attempt.get("stated_rules")
                             or []) if isinstance(attempt.get(
                                 "stated_rules"), list) else [],
        "route_rules": list(attempt.get("route_rules")
                            or []) if isinstance(attempt.get(
                                "route_rules"), list) else [],
        "sat_triggers": list(triggers)
        if isinstance(triggers, list) else [],
        "sat_passed": bool(attempt.get("sat_passed", False)),
        "restatement": str(attempt.get("restatement", "") or ""),
        "task_summary": str(attempt.get("task_summary", "") or ""),
    }


class AcceptanceDecision:
    """One acceptance outcome for one attempt."""

    accepted: bool = False
    kind: str = "HAT"
    findings: List[Dict[str, str]] = []  # type: ignore[assignment]

    def __init__(self, accepted: bool = False, kind: str = "HAT",
                 findings: Optional[List[Dict[str, str]]] = None):
        self.accepted = accepted
        self.kind = kind
        self.findings = list(findings or [])


def _sat_needed(item: Dict[str, Any]) -> bool:
    """True when a SAT trigger is present and SAT is not waived.

    R0/compact work never needs ceremonial SAT: only the
    route/capabilities check applies.
    """
    if item["compact"] or item["risk"] == "R0":
        return False
    return any(t in SAT_TRIGGERS for t in item["sat_triggers"])


def accept(attempt: Any) -> AcceptanceDecision:
    """Map one acceptance attempt to ACCEPT or REFUSE.

    All eight frozen rules run in order; the first hit
    refuses. A clean attempt is ACCEPT with kind HAT, or SAT
    when a trigger required and passed it. Pure function: no
    I/O, deterministic in its input. This gates writing; it
    never selects rules and never mints authority.
    """
    item = _normalize_attempt(attempt)
    tag = _excerpt(item)
    if item["stated_phase"] != item["replayed_phase"] \
            or not item["stated_phase"]:
        return AcceptanceDecision(
            accepted=False, kind="HAT", findings=[_make_finding(
                "wrong-phase",
                "stated phase %r != replayed phase %r: prove "
                "the exact task from replayed state"
                % (item["stated_phase"], item["replayed_phase"]),
                tag, severity="blocker")])
    if item["stated_head"] != item["reconciled_head"] \
            or not item["stated_head"]:
        return AcceptanceDecision(
            accepted=False, kind="HAT", findings=[_make_finding(
                "stale-head",
                "stated head != reconciled head: prove the exact "
                "state before writing",
                tag, severity="blocker")])
    if item["owner_decision_required"] \
            and not item["owner_decision_recorded"]:
        return AcceptanceDecision(
            accepted=False, kind="HAT", findings=[_make_finding(
                "missing-decision",
                "required owner decision not recorded: record it "
                "before writing",
                tag, severity="blocker")])
    for protected in item["protected_paths"]:
        if protected not in item["accepted_scope"]:
            return AcceptanceDecision(
                accepted=False, kind="HAT", findings=[_make_finding(
                    "protected-omitted",
                    "protected path %r missing from the accepted "
                    "scope: accept the full scope" % (protected,),
                    tag, severity="blocker")])
    if not item["provider_guardrails"]:
        return AcceptanceDecision(
            accepted=False, kind="HAT", findings=[_make_finding(
                "guardrail-gap",
                "provider lacks required guard rails: only "
                "guard-railed providers write",
                tag, severity="blocker")])
    if _INJECTION_RE.search(item["prompt_text"]):
        return AcceptanceDecision(
            accepted=False, kind="HAT", findings=[_make_finding(
                "prompt-injection",
                "prompt content overrides task, state, rules, or "
                "action: reject injected instructions",
                tag, severity="blocker")])
    needed = _sat_needed(item)
    if needed and not item["sat_passed"]:
        return AcceptanceDecision(
            accepted=False, kind="HAT", findings=[_make_finding(
                "sat-required",
                "SAT trigger %r present but SAT not passed: pass "
                "SAT before writing"
                % ([t for t in item["sat_triggers"]
                    if t in SAT_TRIGGERS][0]
                   if [t for t in item["sat_triggers"]
                       if t in SAT_TRIGGERS] else "(trigger)"),
                tag, severity="blocker")])
    route = set(item["route_rules"])
    stated = set(item["stated_rules"])
    if route and (stated != route):
        return AcceptanceDecision(
            accepted=False,
            kind="SAT" if needed else "HAT",
            findings=[_make_finding(
                "cross-provider",
                "cross-provider restatement diverges from the "
                "Standards route: restate exactly",
                tag)])
    kind = "SAT" if (needed and item["sat_passed"]) or (
        item["sat_passed"] and item["sat_triggers"]) else "HAT"
    if item["sat_triggers"] and not item["compact"] \
            and item["risk"] != "R0" and not item["sat_passed"]:
        kind = "HAT"
    return AcceptanceDecision(accepted=True, kind=kind, findings=[])


def clean_attempt() -> Dict[str, Any]:
    """One clean acceptance attempt (ACCEPT via HAT).

    Exact phase, head, decisions, scope, guardrails, clean
    prompt, exact rule restatement, no SAT trigger. Callers
    mutate one dimension per test.
    """
    head = "a" * 40
    return {
        "role": "builder",
        "risk": "R1",
        "compact": False,
        "stated_phase": "IMPLEMENT",
        "replayed_phase": "IMPLEMENT",
        "stated_head": head,
        "reconciled_head": head,
        "owner_decision_recorded": True,
        "owner_decision_required": False,
        "protected_paths": [],
        "accepted_scope": [],
        "provider_guardrails": True,
        "prompt_text": "implement the recorded next action",
        "stated_rules": ["rule-1"],
        "route_rules": ["rule-1"],
        "sat_triggers": [],
        "sat_passed": False,
        "restatement": "implement the recorded next action",
        "task_summary": "implement the recorded next action",
    }


def _entries_of(corpus: Any) -> List[Dict[str, Any]]:
    if isinstance(corpus, dict):
        entries = corpus.get("entries")
    else:
        entries = corpus
    if not isinstance(entries, list):
        return []
    return entries


def validate_acceptance_corpus(corpus: Any) -> Tuple[List[str],
                                                     List[Dict[str, Any]]]:
    """Validate the frozen acceptance fixture oracle.

    Returns (findings, entries); an empty findings list means
    the corpus is a valid frozen oracle: frozen marker set,
    stable provenance, at least 9 entries, unique well-formed
    IDs, every entry computing its expected rules and accepted
    flag, and all 8 acceptance rules covered.
    """
    if isinstance(corpus, dict):
        if corpus.get("_frozen") is not True:
            return (["acceptance corpus is not frozen: set "
                     "\"_frozen\": true"], [])
        provenance = str(corpus.get("_provenance", ""))
        if "Stage 45 #136" not in provenance:
            return (["acceptance corpus provenance must name "
                      "\"Stage 45 #136\""], [])
    elif not isinstance(corpus, list):
        return (["acceptance corpus must be a JSON object with an "
                 "'entries' array (or a bare array)"], [])
    entries = _entries_of(corpus)
    findings: List[str] = []
    if len(entries) < 9:
        findings.append("acceptance corpus holds %d entries, want "
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
                            "handoff-acceptance.<class>.<nn>" % cid)
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
        if "expected_accepted" not in entry:
            findings.append("entry %s: expected_accepted is "
                            "required" % cid)
        result = accept(entry.get("attempt", {}))
        computed = sorted({f["rule"] for f in result.findings})
        if sorted(str(r) for r in expected) != computed:
            findings.append("entry %s: expected_rules %r != "
                            "accept %r"
                            % (cid, sorted(str(r)
                                           for r in expected),
                               computed))
        if bool(entry.get("expected_accepted")) != result.accepted:
            findings.append("entry %s: expected_accepted %r != "
                            "accept %r" % (cid, entry.get(
                                "expected_accepted"),
                                result.accepted))
    for rule in RULES:
        if rule not in covered:
            findings.append("rule %r has no entries (all 8 "
                            "acceptance rules are required)"
                            % rule)
    return findings, entries
