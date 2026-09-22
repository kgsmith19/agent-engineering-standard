"""Stage 50 Standard half: the deterministic autonomous orchestrator.

Advance authorized work through phases, roles, repairs, merge,
cleanup, and next work without a human continue command. The
orchestrator consumes every Stage 42-49 primitive (events,
checkpoints, replay/wake, HAT/SAT, lease, idempotency,
rotation, SAFE parallelism) and emits one verdict per tick:
NEXT (one bounded authorized action), WAIT (nothing ready),
RECOVER (replay/reconcile/rotate first), ESCALATE (owner
decision required), or COMPLETE (milestone done, hand to the
Release Mold). ``next`` is the pure decision; ``advance``
applies exactly one idempotent transition. Dispatch state is
plain data; missing keys fall back to total defaults, never a
crash.

Frozen verdicts: NEXT, WAIT, RECOVER, ESCALATE, COMPLETE.

Frozen rules, in check order (first hit decides)::

  duplicate-event   — duplicate dispatch event: WAIT (already
                      dispatched, never double-dispatch).
  crash-around      — crash around dispatch: RECOVER first.
  double-worker     — second worker on the slice: RECOVER via
                      lease fencing.
  stale-head        — head moved: RECOVER via reconcile.
  no-ready-work     — nothing authorized and ready: WAIT.
  owner-hold        — owner hold set: ESCALATE, never bypass.
  provider-down     — provider/extension unhealthy: WAIT (or
                      ESCALATE when prolonged — WAIT here).
  budget-exhausted  — budget spent: ESCALATE for owner scope.
  deadlock          — slices wait on each other: ESCALATE with
                      the cycle named.
  review-finding    — validated review finding needs repair:
                      NEXT is the bounded repair action.
  merge-cleanup     — merged work: NEXT is merge cleanup.
  milestone-done    — milestone complete: COMPLETE, hand to the
                      Release Mold.
  clean-next        — authorized ready work: NEXT one action.

``next`` never invents requirements, expands scope,
self-promotes, publishes verdicts, or bypasses the PR Gate:
NEXT carries exactly one bounded action inside existing
authorization. Advisory/dry-run only until canaries pass —
``advance --apply`` stays disabled for real mutation. Findings
use the standard five keys via ``FINDING_FIELDS``;
``SEVERITIES`` names the allowed severities;
``validate_finding`` returns repair strings (empty means
valid). Pure functions: no I/O, no subprocess, no network —
ticks in, verdicts out.
"""

from typing import Any, Dict, List, Optional, Tuple

import re as _re

# Frozen orchestrator verdicts.
VERDICTS = (
    "NEXT",
    "WAIT",
    "RECOVER",
    "ESCALATE",
    "COMPLETE",
)

SEVERITIES = ("blocker", "major", "minor")

FINDING_FIELDS = ("id", "rule", "finding", "severity", "excerpt")

# Frozen orchestrator rules, in check order.
RULES = (
    "duplicate-event",
    "crash-around",
    "double-worker",
    "stale-head",
    "no-ready-work",
    "owner-hold",
    "provider-down",
    "budget-exhausted",
    "deadlock",
    "review-finding",
    "merge-cleanup",
    "milestone-done",
    "clean-next",
)

# Verdict each rule carries.
RULE_VERDICTS = {
    "duplicate-event": "WAIT",
    "crash-around": "RECOVER",
    "double-worker": "RECOVER",
    "stale-head": "RECOVER",
    "no-ready-work": "WAIT",
    "owner-hold": "ESCALATE",
    "provider-down": "WAIT",
    "budget-exhausted": "ESCALATE",
    "deadlock": "ESCALATE",
    "review-finding": "NEXT",
    "merge-cleanup": "NEXT",
    "milestone-done": "COMPLETE",
    "clean-next": "NEXT",
}

# Entry-ID shape for the frozen oracle.
_ENTRY_ID_RE = _re.compile(r"^autonomous-orchestrator\.[a-z-]+\.\d{2}$")


def _make_finding(rule: str, message: str, excerpt: str,
                  severity: str = "major") -> Dict[str, str]:
    """Build one structured orchestrator finding dict."""
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
        repairs.append("finding rule %r is not a frozen Stage 50 "
                       "orchestrator rule" % (rule,))
    if "severity" in finding and finding.get("severity") not in SEVERITIES:
        repairs.append("finding severity %r must be "
                       "blocker|major|minor" % (finding.get("severity"),))
    return repairs


def _excerpt(tick: Dict[str, Any]) -> str:
    """Short evidence excerpt naming the slice/milestone."""
    for key in ("slice", "milestone", "issue"):
        value = tick.get(key)
        if isinstance(value, (str, int, float)) and str(value).strip():
            return str(value)[:200]
    return "(orchestrator)"


def _normalize_tick(tick: Any) -> Dict[str, Any]:
    """Fill total defaults so partial input never crashes."""
    tick = tick if isinstance(tick, dict) else {}
    return {
        "slice": str(tick.get("slice", "")),
        "milestone": str(tick.get("milestone", "") or ""),
        "duplicate_dispatch": bool(tick.get(
            "duplicate_dispatch", False)),
        "crashed": bool(tick.get("crashed", False)),
        "second_worker": bool(tick.get(
            "second_worker", False)),
        "head_moved": bool(tick.get("head_moved", False)),
        "ready_work": bool(tick.get("ready_work", False)),
        "owner_hold": bool(tick.get("owner_hold", False)),
        "provider_healthy": bool(tick.get(
            "provider_healthy", True)),
        "budget_left": int(tick.get("budget_left", 1)),
        "deadlocked": bool(tick.get("deadlocked", False)),
        "deadlock_cycle": str(tick.get(
            "deadlock_cycle", "") or ""),
        "review_repair": bool(tick.get(
            "review_repair", False)),
        "merged_pending_cleanup": bool(tick.get(
            "merged_pending_cleanup", False)),
        "milestone_complete": bool(tick.get(
            "milestone_complete", False)),
        "action": str(tick.get("action", "") or ""),
    }


class OrchestratorDecision:
    """One orchestrator outcome for one tick."""

    verdict: str = "WAIT"
    rule: str = "clean-next"
    action: str = ""
    findings: List[Dict[str, str]] = []  # type: ignore[assignment]

    def __init__(self, verdict: str = "WAIT",
                 rule: str = "clean-next", action: str = "",
                 findings: Optional[List[Dict[str, str]]] = None):
        self.verdict = verdict
        self.rule = rule
        self.action = action
        self.findings = list(findings or [])


def _decide(rule: str, message: str, tag: str, action: str = "",
            severity: str = "major") -> OrchestratorDecision:
    return OrchestratorDecision(
        verdict=RULE_VERDICTS[rule], rule=rule, action=action,
        findings=[_make_finding(rule, message, tag,
                                severity=severity)])


def next(tick: Any) -> OrchestratorDecision:  # noqa: A001 - frozen Stage 50 name
    """Map one orchestrator tick to its verdict.

    Duplicate dispatches wait; crashes, second workers, and
    moved heads recover; empty queues wait; holds, exhausted
    budgets, and deadlocks escalate; unhealthy providers wait;
    validated repairs and merge cleanups dispatch one bounded
    NEXT action; completed milestones hand COMPLETE to the
    Release Mold. Pure function: no I/O, deterministic in its
    input. This decides; ``advance`` applies one transition.
    """
    item = _normalize_tick(tick)
    tag = _excerpt(item)
    if item["duplicate_dispatch"]:
        return _decide(
            "duplicate-event",
            "duplicate dispatch event: already dispatched, "
            "never double-dispatch",
            tag, severity="minor")
    if item["crashed"]:
        return _decide(
            "crash-around",
            "crash around dispatch: RECOVER via replay and "
            "reconcile before dispatching",
            tag)
    if item["second_worker"]:
        return _decide(
            "double-worker",
            "second worker on the slice: RECOVER via lease "
            "fencing",
            tag, severity="blocker")
    if item["head_moved"]:
        return _decide(
            "stale-head",
            "head moved: RECOVER via reconcile before "
            "dispatching",
            tag)
    if item["owner_hold"]:
        return _decide(
            "owner-hold",
            "owner hold set: ESCALATE, never bypass",
            tag, severity="blocker")
    if not item["provider_healthy"]:
        return _decide(
            "provider-down",
            "provider/extension unhealthy: WAIT for health",
            tag)
    if item["budget_left"] <= 0:
        return _decide(
            "budget-exhausted",
            "budget exhausted: ESCALATE for owner scope",
            tag)
    if item["deadlocked"]:
        return _decide(
            "deadlock",
            "slices wait on each other%s: ESCALATE with the "
            "cycle named" % (" (%s)" % item["deadlock_cycle"]
                             if item["deadlock_cycle"] else ""),
            tag, severity="blocker")
    if item["review_repair"]:
        return _decide(
            "review-finding",
            "validated review finding needs repair: NEXT is "
            "the one bounded repair action",
            tag, action="bounded-repair")
    if item["merged_pending_cleanup"]:
        return _decide(
            "merge-cleanup",
            "merged work pending cleanup: NEXT is merge "
            "cleanup",
            tag, action="merge-cleanup", severity="minor")
    if item["milestone_complete"]:
        return _decide(
            "milestone-done",
            "milestone complete: COMPLETE, hand to the Release "
            "Mold",
            tag, action="release-handoff", severity="minor")
    if not item["ready_work"]:
        return _decide(
            "no-ready-work",
            "nothing authorized and ready: WAIT",
            tag, severity="minor")
    return _decide(
        "clean-next",
        "authorized ready work: NEXT is one bounded action "
        "inside existing authorization",
        tag, action=item["action"] or "bounded-next",
        severity="minor")


def advance(tick: Any, dry_run: bool = True) -> OrchestratorDecision:
    """Apply exactly one idempotent orchestrator transition.

    Advisory/dry-run by default: returns the ``next`` verdict
    without mutating. ``dry_run=False`` is refused until
    canaries pass — this stage ships dry-run only, so apply
    always reports the transition without performing it.
    """
    decision = next(tick)
    if not dry_run:
        decision.findings.append(_make_finding(
            "clean-next",
            "advance --apply refused: canaries have not passed; "
            "dry-run only in this stage",
            _excerpt(_normalize_tick(tick)), severity="blocker"))
        decision.verdict = "WAIT"
        decision.rule = "clean-next"
        decision.action = ""
    return decision


def clean_tick() -> Dict[str, Any]:
    """One clean orchestrator tick (NEXT).

    Authorized ready work, healthy provider, budget left, no
    holds, crashes, or duplicates. Callers mutate one
    dimension per test.
    """
    return {
        "slice": "slice-1",
        "milestone": "v5",
        "duplicate_dispatch": False,
        "crashed": False,
        "second_worker": False,
        "head_moved": False,
        "ready_work": True,
        "owner_hold": False,
        "provider_healthy": True,
        "budget_left": 5,
        "deadlocked": False,
        "deadlock_cycle": "",
        "review_repair": False,
        "merged_pending_cleanup": False,
        "milestone_complete": False,
        "action": "implement-claim-2",
    }


def _entries_of(corpus: Any) -> List[Dict[str, Any]]:
    if isinstance(corpus, dict):
        entries = corpus.get("entries")
    else:
        entries = corpus
    if not isinstance(entries, list):
        return []
    return entries


def validate_orchestrator_corpus(corpus: Any) -> Tuple[List[str],
                                                       List[Dict[str, Any]]]:
    """Validate the frozen orchestrator fixture oracle.

    Returns (findings, entries); an empty findings list means
    the corpus is a valid frozen oracle: frozen marker set,
    stable provenance, at least 13 entries, unique well-formed
    IDs, every entry computing its expected rule and verdict,
    and all 13 orchestrator rules covered.
    """
    if isinstance(corpus, dict):
        if corpus.get("_frozen") is not True:
            return (["orchestrator corpus is not frozen: set "
                     "\"_frozen\": true"], [])
        provenance = str(corpus.get("_provenance", ""))
        if "Stage 50 #141" not in provenance:
            return (["orchestrator corpus provenance must name "
                      "\"Stage 50 #141\""], [])
    elif not isinstance(corpus, list):
        return (["orchestrator corpus must be a JSON object with an "
                 "'entries' array (or a bare array)"], [])
    entries = _entries_of(corpus)
    findings: List[str] = []
    if len(entries) < 13:
        findings.append("orchestrator corpus holds %d entries, want "
                        "at least 13" % len(entries))
    seen: Dict[str, int] = {}
    covered = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            findings.append("entries[%d] is not a mapping" % index)
            continue
        cid = str(entry.get("id", ""))
        if not _ENTRY_ID_RE.match(cid):
            findings.append("entry %r: id is not "
                            "autonomous-orchestrator.<class>.<nn>"
                            % cid)
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
                            "frozen Stage 50 orchestrator rule"
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
        result = next(entry.get("tick", {}))
        if result.rule != rule:
            findings.append("entry %s: expected_rule %r != "
                            "next %r" % (cid, rule, result.rule))
        if result.verdict != entry.get("expected_verdict"):
            findings.append("entry %s: expected_verdict %r != "
                            "next %r" % (cid, entry.get(
                                "expected_verdict"),
                                result.verdict))
    for rule in RULES:
        if rule not in covered:
            findings.append("rule %r has no entries (all 13 "
                            "orchestrator rules are required)"
                            % rule)
    return findings, entries
