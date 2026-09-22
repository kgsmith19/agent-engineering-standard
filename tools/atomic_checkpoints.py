"""Stage 43 Standard half: semantic atomic checkpoints.

Every context/role transition and consequential side effect
recovers at coherent semantic barriers through one five-state
mechanism: PREPARE -> SAVE -> PUBLISH -> READ-BACK -> FINALIZE.
Compare-and-swap guards every transition; a crash anywhere
recovers to the last coherent state, never forward into
corruption. ``decide`` maps one checkpoint attempt to its
outcome (CHECKPOINTED, RECOVER with the coherent barrier, or
REFUSE); ``validate_checkpoint_corpus`` checks the frozen
oracle. Attempts are plain data; missing keys fall back to
total defaults, never a crash.

Frozen rules, in check order (first hit decides)::

  dirty-worktree     — uncommitted work: checkpoint nothing
                       half-finished as complete.
  tests-incomplete   — red tests: no checkpoint as complete.
  stale-cas          — CAS token mismatch: never bypass CAS.
  crash-interrupt    — simulated crash at a barrier: recover
                       to the last coherent barrier.
  push-failed        — publish push failed: recover to SAVE
                       and retry publish.
  corrupt-artifact   — artifact bytes invalid: refuse.
  duplicate-finalize — already finalized: refuse the second
                       finalize (idempotent no-op signal).
  remote-ahead       — remote ack without local receipt:
                       recover to READ-BACK and read back.

A clean attempt is CHECKPOINTED at FINALIZE. Findings are
repair guidance (rule + message + excerpt), never an error:
``FINDING_FIELDS`` names the five required keys,
``SEVERITIES`` names the allowed severities, and
``validate_finding`` returns repair strings (empty means
valid). Pure functions: no I/O, no subprocess, no network —
attempts in, outcomes out. Recovery is to coherence, never a
general-purpose snapshot; CAS is never bypassed.
"""

from typing import Any, Dict, List, Optional, Tuple

import re as _re

# Frozen barrier states, in mechanism order.
STATES = (
    "PREPARE",
    "SAVE",
    "PUBLISH",
    "READ-BACK",
    "FINALIZE",
)

OUTCOMES = ("CHECKPOINTED", "RECOVER", "REFUSE")

SEVERITIES = ("blocker", "major", "minor")

FINDING_FIELDS = ("id", "rule", "finding", "severity", "excerpt")

# Frozen checkpoint rules, in check order.
RULES = (
    "dirty-worktree",
    "tests-incomplete",
    "stale-cas",
    "crash-interrupt",
    "push-failed",
    "corrupt-artifact",
    "duplicate-finalize",
    "remote-ahead",
)

# Crash at a barrier recovers to the last coherent barrier.
CRASH_RECOVERY = {
    "PREPARE": "START",
    "SAVE": "PREPARE",
    "PUBLISH": "SAVE",
    "READ-BACK": "PUBLISH",
    "FINALIZE": "READ-BACK",
}

# Entry-ID shape for the frozen oracle.
_ENTRY_ID_RE = _re.compile(r"^atomic-checkpoint\.[a-z-]+\.\d{2}$")


def _make_finding(rule: str, message: str, excerpt: str,
                  severity: str = "major") -> Dict[str, str]:
    """Build one structured checkpoint finding dict."""
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
        repairs.append("finding rule %r is not a frozen Stage 43 "
                       "checkpoint rule" % (rule,))
    if "severity" in finding and finding.get("severity") not in SEVERITIES:
        repairs.append("finding severity %r must be "
                       "blocker|major|minor" % (finding.get("severity"),))
    return repairs


def _excerpt(attempt: Dict[str, Any]) -> str:
    """Short evidence excerpt naming the checkpoint."""
    name = attempt.get("name")
    if isinstance(name, (str, int, float)) and str(name).strip():
        return str(name)[:200]
    return "(attempt)"


def _normalize_attempt(attempt: Any) -> Dict[str, Any]:
    """Fill total defaults so partial input never crashes."""
    attempt = attempt if isinstance(attempt, dict) else {}
    return {
        "name": str(attempt.get("name", "")),
        "worktree_clean": bool(attempt.get(
            "worktree_clean", False)),
        "tests_green": bool(attempt.get("tests_green", False)),
        "cas_current": str(attempt.get("cas_current", "")),
        "cas_expected": str(attempt.get("cas_expected", "")),
        "crash_at": str(attempt.get("crash_at", "") or ""),
        "push_ok": bool(attempt.get("push_ok", True)),
        "artifact_ok": bool(attempt.get("artifact_ok", True)),
        "already_finalized": bool(attempt.get(
            "already_finalized", False)),
        "remote_ack": bool(attempt.get("remote_ack", False)),
        "local_receipt": bool(attempt.get(
            "local_receipt", False)),
    }


class CheckpointDecision:
    """One checkpoint outcome for one attempt."""

    outcome: str = "REFUSE"
    coherent: str = "START"
    findings: List[Dict[str, str]] = []  # type: ignore[assignment]

    def __init__(self, outcome: str = "REFUSE",
                 coherent: str = "START",
                 findings: Optional[List[Dict[str, str]]] = None):
        self.outcome = outcome
        self.coherent = coherent
        self.findings = list(findings or [])


def decide(attempt: Any) -> CheckpointDecision:
    """Map one checkpoint attempt to its outcome.

    Guards run first (dirty tree, red tests, stale CAS); then
    crash simulation recovers to the last coherent barrier;
    then publish integrity (push, artifact, duplicate, remote
    receipt). A clean attempt is CHECKPOINTED at FINALIZE.
    Pure function: no I/O, deterministic in its input. This
    decides; it never pushes, never writes, never finalizes.
    """
    item = _normalize_attempt(attempt)
    tag = _excerpt(item)
    if not item["worktree_clean"]:
        return CheckpointDecision(
            outcome="REFUSE", coherent="START", findings=[_make_finding(
                "dirty-worktree",
                "worktree dirty: commit or stash before "
                "checkpointing; half-finished edits are never "
                "checkpointed as complete",
                tag)])
    if not item["tests_green"]:
        return CheckpointDecision(
            outcome="REFUSE", coherent="START", findings=[_make_finding(
                "tests-incomplete",
                "tests not green: checkpoint nothing incomplete "
                "as complete",
                tag)])
    if item["cas_current"] != item["cas_expected"] \
            or not item["cas_expected"]:
        return CheckpointDecision(
            outcome="REFUSE", coherent="START", findings=[_make_finding(
                "stale-cas",
                "CAS token stale or missing: re-read the barrier "
                "and retry; CAS is never bypassed",
                tag, severity="blocker")])
    if item["crash_at"]:
        barrier = item["crash_at"]
        if barrier not in CRASH_RECOVERY:
            return CheckpointDecision(
                outcome="REFUSE", coherent="START",
                findings=[_make_finding(
                    "crash-interrupt",
                    "unknown crash barrier %r: crash only at %s"
                    % (barrier, ", ".join(STATES)),
                    tag)])
        return CheckpointDecision(
            outcome="RECOVER",
            coherent=CRASH_RECOVERY[barrier],
            findings=[_make_finding(
                "crash-interrupt",
                "crash at %s: recover to the last coherent "
                "barrier %s" % (barrier,
                                CRASH_RECOVERY[barrier]),
                tag)])
    if not item["push_ok"]:
        return CheckpointDecision(
            outcome="RECOVER", coherent="SAVE", findings=[_make_finding(
                "push-failed",
                "publish push failed: recover to SAVE and retry "
                "publish",
                tag)])
    if not item["artifact_ok"]:
        return CheckpointDecision(
            outcome="REFUSE", coherent="SAVE", findings=[_make_finding(
                "corrupt-artifact",
                "artifact bytes invalid: re-save before "
                "publishing",
                tag, severity="blocker")])
    if item["already_finalized"]:
        return CheckpointDecision(
            outcome="REFUSE", coherent="FINALIZE",
            findings=[_make_finding(
                "duplicate-finalize",
                "already finalized: the second finalize is a "
                "no-op, never a second mutation",
                tag)])
    if item["remote_ack"] and not item["local_receipt"]:
        return CheckpointDecision(
            outcome="RECOVER", coherent="READ-BACK",
            findings=[_make_finding(
                "remote-ahead",
                "remote succeeded before local receipt: recover "
                "to READ-BACK and read back before finalizing",
                tag)])
    return CheckpointDecision(outcome="CHECKPOINTED",
                              coherent="FINALIZE", findings=[])


def clean_attempt() -> Dict[str, Any]:
    """One clean checkpoint attempt (CHECKPOINTED at FINALIZE).

    Clean tree, green tests, fresh CAS, no crash, pushed,
    valid artifact, first finalize, receipt recorded.
    Callers mutate one dimension per test.
    """
    return {
        "name": "checkpoint-1",
        "worktree_clean": True,
        "tests_green": True,
        "cas_current": "cas-7",
        "cas_expected": "cas-7",
        "crash_at": "",
        "push_ok": True,
        "artifact_ok": True,
        "already_finalized": False,
        "remote_ack": True,
        "local_receipt": True,
    }


def _entries_of(corpus: Any) -> List[Dict[str, Any]]:
    if isinstance(corpus, dict):
        entries = corpus.get("entries")
    else:
        entries = corpus
    if not isinstance(entries, list):
        return []
    return entries


def validate_checkpoint_corpus(corpus: Any) -> Tuple[List[str],
                                                     List[Dict[str, Any]]]:
    """Validate the frozen checkpoint fixture oracle.

    Returns (findings, entries); an empty findings list means
    the corpus is a valid frozen oracle: frozen marker set,
    stable provenance, at least 10 entries, unique well-formed
    IDs, every entry computing its expected rules, outcome, and
    coherent barrier, and all 8 checkpoint rules covered.
    """
    if isinstance(corpus, dict):
        if corpus.get("_frozen") is not True:
            return (["checkpoint corpus is not frozen: set "
                     "\"_frozen\": true"], [])
        provenance = str(corpus.get("_provenance", ""))
        if "Stage 43 #134" not in provenance:
            return (["checkpoint corpus provenance must name "
                      "\"Stage 43 #134\""], [])
    elif not isinstance(corpus, list):
        return (["checkpoint corpus must be a JSON object with an "
                 "'entries' array (or a bare array)"], [])
    entries = _entries_of(corpus)
    findings: List[str] = []
    if len(entries) < 10:
        findings.append("checkpoint corpus holds %d entries, want "
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
                            "atomic-checkpoint.<class>.<nn>" % cid)
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
        for key in ("expected_outcome", "expected_coherent"):
            if key not in entry:
                findings.append("entry %s: %s is required"
                                % (cid, key))
        result = decide(entry.get("attempt", {}))
        computed = sorted({f["rule"] for f in result.findings})
        if sorted(str(r) for r in expected) != computed:
            findings.append("entry %s: expected_rules %r != "
                            "decide %r"
                            % (cid, sorted(str(r)
                                           for r in expected),
                               computed))
        if entry.get("expected_outcome") != result.outcome:
            findings.append("entry %s: expected_outcome %r != "
                            "decide %r" % (cid, entry.get(
                                "expected_outcome"),
                                result.outcome))
        if entry.get("expected_coherent") != result.coherent:
            findings.append("entry %s: expected_coherent %r != "
                            "decide %r" % (cid, entry.get(
                                "expected_coherent"),
                                result.coherent))
    for rule in RULES:
        if rule not in covered:
            findings.append("rule %r has no entries (all 8 "
                            "checkpoint rules are required)"
                            % rule)
    return findings, entries
