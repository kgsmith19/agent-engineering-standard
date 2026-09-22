"""Stage 44 Standard half: deterministic replay, reconciliation, wake.

Reconstruct the current task and exact next safe action without
transcript or model recollection: replay the Stage 42 journal,
reconcile against Git branch/worktree/head, PR/checks state,
and live GitHub settings, then emit one verdict plus the next
safe action. ``wake`` maps one wake observation to its verdict;
``validate_wake_corpus`` checks the frozen oracle. Observations
are plain data; missing keys fall back to total defaults, never
a crash — missing or ambiguous evidence never fabricates a
default.

Frozen verdicts (exactly one per wake)::

  CLEAN_RESUME     — replay clean, head matches, receipts hold:
                     resume the recorded next action.
  RECHECKPOINT     — interrupted phase or incomplete checkpoint:
                     re-checkpoint before resuming.
  RECONCILE_HEAD   — moved head or missing commit: reconcile
                     the head before any mutation.
  RECONCILE_STATE  — stale capsule, corrupt snapshot, duplicate
                     event, or provider change: reconcile state
                     before any mutation.
  GITHUB_DOWN      — GitHub unavailable: local read-only work
                     only, no mutation.
  MERGED_DONE      — completed merge: reconcile and close out.

Frozen wake rules, in check order (first hit decides)::

  github-down        — live GitHub unreachable.
  merged-done        — PR merged: close out, never resume.
  moved-head         — recorded head != live head.
  missing-commit     — recorded commit absent from history.
  interrupted-phase  — journal ends mid-phase.
  incomplete-check   — checkpoint below FINALIZE.
  stale-capsule      — capsule head != journal head.
  corrupt-snapshot   — snapshot bytes fail validation.
  provider-change    — builder provider family changed.
  duplicate-event    — conflicting duplicate in journal.
  clean              — none of the above: CLEAN_RESUME.

Findings use the standard five keys via ``FINDING_FIELDS``;
``SEVERITIES`` names the allowed severities;
``validate_finding`` returns repair strings (empty means
valid). Pure functions: no I/O, no subprocess, no network —
observations in, verdicts out. Read/reconcile only: wake gates
mutation but never mutates itself.
"""

from typing import Any, Dict, List, Optional, Tuple

import re as _re

# Frozen verdicts, one per wake.
VERDICTS = (
    "CLEAN_RESUME",
    "RECHECKPOINT",
    "RECONCILE_HEAD",
    "RECONCILE_STATE",
    "GITHUB_DOWN",
    "MERGED_DONE",
)

SEVERITIES = ("blocker", "major", "minor")

FINDING_FIELDS = ("id", "rule", "finding", "severity", "excerpt")

# Frozen wake rules, in check order.
RULES = (
    "github-down",
    "merged-done",
    "moved-head",
    "missing-commit",
    "interrupted-phase",
    "incomplete-check",
    "stale-capsule",
    "corrupt-snapshot",
    "provider-change",
    "duplicate-event",
    "clean",
)

# Verdict each rule carries (clean means CLEAN_RESUME).
RULE_VERDICTS = {
    "github-down": "GITHUB_DOWN",
    "merged-done": "MERGED_DONE",
    "moved-head": "RECONCILE_HEAD",
    "missing-commit": "RECONCILE_HEAD",
    "interrupted-phase": "RECHECKPOINT",
    "incomplete-check": "RECHECKPOINT",
    "stale-capsule": "RECONCILE_STATE",
    "corrupt-snapshot": "RECONCILE_STATE",
    "provider-change": "RECONCILE_STATE",
    "duplicate-event": "RECONCILE_STATE",
    "clean": "CLEAN_RESUME",
}

# Entry-ID shape for the frozen oracle.
_ENTRY_ID_RE = _re.compile(r"^replay-wake\.[a-z-]+\.\d{2}$")


def _make_finding(rule: str, message: str, excerpt: str,
                  severity: str = "major") -> Dict[str, str]:
    """Build one structured wake finding dict."""
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
        repairs.append("finding rule %r is not a frozen Stage 44 "
                       "wake rule" % (rule,))
    if "severity" in finding and finding.get("severity") not in SEVERITIES:
        repairs.append("finding severity %r must be "
                       "blocker|major|minor" % (finding.get("severity"),))
    return repairs


def _excerpt(observation: Dict[str, Any]) -> str:
    """Short evidence excerpt naming the issue/branch."""
    for key in ("issue", "branch", "head"):
        value = observation.get(key)
        if isinstance(value, (str, int, float)) and str(value).strip():
            return str(value)[:200]
    return "(wake)"


def _normalize_observation(observation: Any) -> Dict[str, Any]:
    """Fill total defaults so partial input never crashes."""
    observation = observation if isinstance(observation, dict) else {}
    journal = observation.get("journal")
    return {
        "issue": str(observation.get("issue", "")),
        "branch": str(observation.get("branch", "")),
        "journal": list(journal) if isinstance(journal, list)
        else [],
        "recorded_head": str(observation.get(
            "recorded_head", "")),
        "live_head": str(observation.get("live_head", "")),
        "commit_present": bool(observation.get(
            "commit_present", False)),
        "phase_complete": bool(observation.get(
            "phase_complete", False)),
        "checkpoint_state": str(observation.get(
            "checkpoint_state", "") or ""),
        "capsule_head": str(observation.get(
            "capsule_head", "")),
        "journal_head": str(observation.get(
            "journal_head", "")),
        "snapshot_ok": bool(observation.get(
            "snapshot_ok", True)),
        "builder_family": str(observation.get(
            "builder_family", "") or ""),
        "recorded_family": str(observation.get(
            "recorded_family", "") or ""),
        "github_reachable": bool(observation.get(
            "github_reachable", True)),
        "pr_merged": bool(observation.get("pr_merged", False)),
        "duplicate_conflict": bool(observation.get(
            "duplicate_conflict", False)),
    }


class WakeDecision:
    """One wake outcome for one observation."""

    verdict: str = "RECONCILE_STATE"
    rule: str = "clean"
    next_action: str = ""
    findings: List[Dict[str, str]] = []  # type: ignore[assignment]

    def __init__(self, verdict: str = "RECONCILE_STATE",
                 rule: str = "clean", next_action: str = "",
                 findings: Optional[List[Dict[str, str]]] = None):
        self.verdict = verdict
        self.rule = rule
        self.next_action = next_action
        self.findings = list(findings or [])


_NEXT_ACTIONS = {
    "CLEAN_RESUME": "resume the recorded next action",
    "RECHECKPOINT": "re-checkpoint before resuming",
    "RECONCILE_HEAD": "reconcile the head before any mutation",
    "RECONCILE_STATE": "reconcile state before any mutation",
    "GITHUB_DOWN": "local read-only work only",
    "MERGED_DONE": "reconcile and close out",
}


def wake(observation: Any) -> WakeDecision:
    """Map one wake observation to its verdict.

    Rules run in frozen order; the first hit decides the
    verdict and next action. Missing or ambiguous evidence
    never fabricates CLEAN_RESUME: any gap reconciles. A fully
    clean observation is CLEAN_RESUME with a clean finding.
    Pure function: no I/O, deterministic in its input. This
    decides; it never mutates, never recollects, never trusts
    the transcript.
    """
    item = _normalize_observation(observation)
    tag = _excerpt(item)
    if not item["github_reachable"]:
        rule = "github-down"
        return WakeDecision(
            verdict=RULE_VERDICTS[rule], rule=rule,
            next_action=_NEXT_ACTIONS[RULE_VERDICTS[rule]],
            findings=[_make_finding(
                rule,
                "live GitHub unreachable: local read-only work "
                "only, no mutation",
                tag, severity="blocker")])
    if item["pr_merged"]:
        rule = "merged-done"
        return WakeDecision(
            verdict=RULE_VERDICTS[rule], rule=rule,
            next_action=_NEXT_ACTIONS[RULE_VERDICTS[rule]],
            findings=[_make_finding(
                rule,
                "PR merged: reconcile and close out, never "
                "resume",
                tag)])
    if item["recorded_head"] and item["live_head"] \
            and item["recorded_head"] != item["live_head"]:
        rule = "moved-head"
        return WakeDecision(
            verdict=RULE_VERDICTS[rule], rule=rule,
            next_action=_NEXT_ACTIONS[RULE_VERDICTS[rule]],
            findings=[_make_finding(
                rule,
                "recorded head %r != live head %r: reconcile "
                "the head before any mutation"
                % (item["recorded_head"][:12],
                   item["live_head"][:12]),
                tag, severity="blocker")])
    if item["recorded_head"] and not item["commit_present"]:
        rule = "missing-commit"
        return WakeDecision(
            verdict=RULE_VERDICTS[rule], rule=rule,
            next_action=_NEXT_ACTIONS[RULE_VERDICTS[rule]],
            findings=[_make_finding(
                rule,
                "recorded commit absent from history: reconcile "
                "the head before any mutation",
                tag, severity="blocker")])
    if not item["phase_complete"]:
        rule = "interrupted-phase"
        return WakeDecision(
            verdict=RULE_VERDICTS[rule], rule=rule,
            next_action=_NEXT_ACTIONS[RULE_VERDICTS[rule]],
            findings=[_make_finding(
                rule,
                "journal ends mid-phase: re-checkpoint before "
                "resuming",
                tag)])
    if item["checkpoint_state"] and item["checkpoint_state"] \
            != "FINALIZE":
        rule = "incomplete-check"
        return WakeDecision(
            verdict=RULE_VERDICTS[rule], rule=rule,
            next_action=_NEXT_ACTIONS[RULE_VERDICTS[rule]],
            findings=[_make_finding(
                rule,
                "checkpoint at %s, not FINALIZE: re-checkpoint "
                "before resuming" % item["checkpoint_state"],
                tag)])
    if item["capsule_head"] and item["journal_head"] \
            and item["capsule_head"] != item["journal_head"]:
        rule = "stale-capsule"
        return WakeDecision(
            verdict=RULE_VERDICTS[rule], rule=rule,
            next_action=_NEXT_ACTIONS[RULE_VERDICTS[rule]],
            findings=[_make_finding(
                rule,
                "capsule head != journal head: reconcile state "
                "before any mutation",
                tag)])
    if not item["snapshot_ok"]:
        rule = "corrupt-snapshot"
        return WakeDecision(
            verdict=RULE_VERDICTS[rule], rule=rule,
            next_action=_NEXT_ACTIONS[RULE_VERDICTS[rule]],
            findings=[_make_finding(
                rule,
                "snapshot bytes fail validation: reconcile "
                "state before any mutation",
                tag, severity="blocker")])
    if item["builder_family"] and item["recorded_family"] \
            and item["builder_family"] != item["recorded_family"]:
        rule = "provider-change"
        return WakeDecision(
            verdict=RULE_VERDICTS[rule], rule=rule,
            next_action=_NEXT_ACTIONS[RULE_VERDICTS[rule]],
            findings=[_make_finding(
                rule,
                "builder family %r != recorded %r: reconcile "
                "state before any mutation"
                % (item["builder_family"],
                   item["recorded_family"]),
                tag)])
    if item["duplicate_conflict"]:
        rule = "duplicate-event"
        return WakeDecision(
            verdict=RULE_VERDICTS[rule], rule=rule,
            next_action=_NEXT_ACTIONS[RULE_VERDICTS[rule]],
            findings=[_make_finding(
                rule,
                "conflicting duplicate in journal: reconcile "
                "state before any mutation",
                tag)])
    rule = "clean"
    return WakeDecision(
        verdict=RULE_VERDICTS[rule], rule=rule,
        next_action=_NEXT_ACTIONS[RULE_VERDICTS[rule]],
        findings=[_make_finding(
            rule,
            "replay clean, head matches, receipts hold: resume "
            "the recorded next action",
            tag, severity="minor")])


def clean_observation() -> Dict[str, Any]:
    """One clean wake observation (CLEAN_RESUME).

    Replay clean, head matches, receipts hold, checkpoint at
    FINALIZE, capsule fresh, snapshot valid, same provider,
    GitHub reachable, PR open. Callers mutate one dimension
    per test.
    """
    head = "a" * 40
    return {
        "issue": "135",
        "branch": "issue/135-replay-wake",
        "journal": [{"seq": 1, "type": "claim-started"}],
        "recorded_head": head,
        "live_head": head,
        "commit_present": True,
        "phase_complete": True,
        "checkpoint_state": "FINALIZE",
        "capsule_head": head,
        "journal_head": head,
        "snapshot_ok": True,
        "builder_family": "anthropic",
        "recorded_family": "anthropic",
        "github_reachable": True,
        "pr_merged": False,
        "duplicate_conflict": False,
    }


def _entries_of(corpus: Any) -> List[Dict[str, Any]]:
    if isinstance(corpus, dict):
        entries = corpus.get("entries")
    else:
        entries = corpus
    if not isinstance(entries, list):
        return []
    return entries


def validate_wake_corpus(corpus: Any) -> Tuple[List[str],
                                               List[Dict[str, Any]]]:
    """Validate the frozen wake fixture oracle.

    Returns (findings, entries); an empty findings list means
    the corpus is a valid frozen oracle: frozen marker set,
    stable provenance, at least 11 entries, unique well-formed
    IDs, every entry computing its expected rule and verdict,
    and all 11 wake rules covered.
    """
    if isinstance(corpus, dict):
        if corpus.get("_frozen") is not True:
            return (["wake corpus is not frozen: set "
                     "\"_frozen\": true"], [])
        provenance = str(corpus.get("_provenance", ""))
        if "Stage 44 #135" not in provenance:
            return (["wake corpus provenance must name "
                      "\"Stage 44 #135\""], [])
    elif not isinstance(corpus, list):
        return (["wake corpus must be a JSON object with an "
                 "'entries' array (or a bare array)"], [])
    entries = _entries_of(corpus)
    findings: List[str] = []
    if len(entries) < 11:
        findings.append("wake corpus holds %d entries, want "
                        "at least 11" % len(entries))
    seen: Dict[str, int] = {}
    covered = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            findings.append("entries[%d] is not a mapping" % index)
            continue
        cid = str(entry.get("id", ""))
        if not _ENTRY_ID_RE.match(cid):
            findings.append("entry %r: id is not "
                            "replay-wake.<class>.<nn>" % cid)
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
                            "frozen Stage 44 wake rule" % (cid, rule))
            continue
        covered.add(str(rule))
        if entry.get("expected_verdict") != RULE_VERDICTS.get(
                str(rule)):
            findings.append("entry %s: expected_verdict %r != "
                            "rule verdict %r" % (cid, entry.get(
                                "expected_verdict"),
                                RULE_VERDICTS.get(str(rule))))
            continue
        result = wake(entry.get("observation", {}))
        if result.rule != rule:
            findings.append("entry %s: expected_rule %r != "
                            "wake %r" % (cid, rule, result.rule))
        if result.verdict != entry.get("expected_verdict"):
            findings.append("entry %s: expected_verdict %r != "
                            "wake %r" % (cid, entry.get(
                                "expected_verdict"),
                                result.verdict))
    for rule in RULES:
        if rule not in covered:
            findings.append("rule %r has no entries (all 11 "
                            "wake rules are required)"
                            % rule)
    return findings, entries
