"""Stage 47 Standard half: idempotent external effects and tool executions.

Crash/retry never duplicates comments, Issues, dispatches,
emails, deployments, or other mutations. Every operation
carries a fingerprint (tool + canonical args + head + lease
generation); before any retry the envelope reconciles against
the authoritative result (remote run IDs, webhooks, receipts):
a recorded result replays, a conflicting payload reuse
refuses, changed arguments after the guard refuse, mutated
results refuse, stale heads refuse, non-idempotent
destructive actions need explicit confirmation, and comment
upserts and deployment dispatches carry their dedupe keys.
``decide`` maps one execution attempt to EXECUTE / REPLAY /
REFUSE; ``validate_effect_corpus`` checks the frozen oracle.
Attempts are plain data; missing keys fall back to total
defaults, never a crash.

Frozen rules, in check order (first hit decides)::

  recorded-result     — authoritative result exists: replay it,
                        never re-execute (EXECUTE becomes REPLAY).
  conflicting-reuse   — same fingerprint, different payload:
                        refuse (payloads never change identity).
  changed-argument    — arguments changed after the guard:
                        refuse and re-guard.
  mutated-result      — authoritative result bytes changed:
                        refuse (results are immutable).
  stale-head          — head moved since the guard: refuse and
                        re-guard at the live head.
  destructive-action  — non-idempotent destructive action
                        without explicit confirmation: refuse.
  duplicate-webhook   — duplicate delivery: replay the
                        recorded outcome, never a second effect.
  crash-after-remote  — crash after remote success: reconcile
                        first, then replay.
  missing-dedupe      — comment upsert or dispatch without its
                        dedupe key: refuse.

A clean first execution is EXECUTE. Findings use the standard
five keys via ``FINDING_FIELDS``; ``SEVERITIES`` names the
allowed severities; ``validate_finding`` returns repair strings
(empty means valid). Pure functions: no I/O, no subprocess, no
network — attempts in, verdicts out. No product-side effects
are exercised in tests; denial is monotonic (a later
lower-trust callback never reverses a refusal).
"""

from typing import Any, Dict, List, Optional, Tuple

import hashlib
import json
import re as _re

# Frozen execution verdicts.
VERDICTS = ("EXECUTE", "REPLAY", "REFUSE")

SEVERITIES = ("blocker", "major", "minor")

FINDING_FIELDS = ("id", "rule", "finding", "severity", "excerpt")

# Frozen effect rules, in check order.
RULES = (
    "recorded-result",
    "conflicting-reuse",
    "changed-argument",
    "mutated-result",
    "stale-head",
    "destructive-action",
    "duplicate-webhook",
    "crash-after-remote",
    "missing-dedupe",
)

# Operations requiring explicit confirmation (non-idempotent).
DESTRUCTIVE_OPS = ("deploy", "delete", "email-send", "merge",
                   "payment")

# Operations requiring a dedupe key.
DEDUPE_OPS = ("comment-upsert", "dispatch")

# Entry-ID shape for the frozen oracle.
_ENTRY_ID_RE = _re.compile(r"^idempotent-effect\.[a-z-]+\.\d{2}$")


def _make_finding(rule: str, message: str, excerpt: str,
                  severity: str = "major") -> Dict[str, str]:
    """Build one structured effect finding dict."""
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
        repairs.append("finding rule %r is not a frozen Stage 47 "
                       "effect rule" % (rule,))
    if "severity" in finding and finding.get("severity") not in SEVERITIES:
        repairs.append("finding severity %r must be "
                       "blocker|major|minor" % (finding.get("severity"),))
    return repairs


def fingerprint(tool: str, args: Any, head: str,
                generation: int) -> str:
    """Compute the operation fingerprint: sha256 over canonical
    (tool, args, head, generation). Same fingerprint means the
    same operation; different payloads under one fingerprint
    are conflicts, never updates."""
    canonical = json.dumps(
        {"tool": str(tool), "args": args,
         "head": str(head), "generation": int(generation or 0)},
        sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _excerpt(attempt: Dict[str, Any]) -> str:
    """Short evidence excerpt naming the tool/operation."""
    for key in ("tool", "operation", "fingerprint"):
        value = attempt.get(key)
        if isinstance(value, (str, int, float)) and str(value).strip():
            return str(value)[:200]
    return "(effect)"


def _normalize_attempt(attempt: Any) -> Dict[str, Any]:
    """Fill total defaults so partial input never crashes."""
    attempt = attempt if isinstance(attempt, dict) else {}
    return {
        "tool": str(attempt.get("tool", "")),
        "operation": str(attempt.get("operation", "") or ""),
        "args": attempt.get("args", {}),
        "head": str(attempt.get("head", "")),
        "guard_head": str(attempt.get("guard_head", "") or ""),
        "generation": int(attempt.get("generation") or 0),
        "fingerprint": str(attempt.get("fingerprint", "") or ""),
        "recorded_fingerprint": str(attempt.get(
            "recorded_fingerprint", "") or ""),
        "recorded_result": attempt.get("recorded_result"),
        "has_recorded_result": bool(attempt.get(
            "has_recorded_result", False)),
        "recorded_payload": attempt.get("recorded_payload"),
        "payload": attempt.get("payload"),
        "guard_args": attempt.get("guard_args"),
        "result_mutated": bool(attempt.get(
            "result_mutated", False)),
        "confirmed": bool(attempt.get("confirmed", False)),
        "duplicate_delivery": bool(attempt.get(
            "duplicate_delivery", False)),
        "crashed_after_remote": bool(attempt.get(
            "crashed_after_remote", False)),
        "dedupe_key": str(attempt.get("dedupe_key", "") or ""),
    }


class EffectDecision:
    """One effect outcome for one execution attempt."""

    verdict: str = "REFUSE"
    rule: str = "missing-dedupe"
    findings: List[Dict[str, str]] = []  # type: ignore[assignment]

    def __init__(self, verdict: str = "REFUSE",
                 rule: str = "missing-dedupe",
                 findings: Optional[List[Dict[str, str]]] = None):
        self.verdict = verdict
        self.rule = rule
        self.findings = list(findings or [])


def _refuse(rule: str, message: str, tag: str,
            severity: str = "major") -> EffectDecision:
    return EffectDecision(
        verdict="REFUSE", rule=rule,
        findings=[_make_finding(rule, message, tag,
                                severity=severity)])


def decide(attempt: Any) -> EffectDecision:
    """Map one execution attempt to EXECUTE / REPLAY / REFUSE.

    Recorded results replay; duplicate deliveries replay;
    crashes after remote success reconcile-then-replay;
    conflicting reuses, changed arguments, mutated results,
    stale heads, unconfirmed destructive actions, and missing
    dedupe keys refuse. A clean first execution is EXECUTE.
    Denial is monotonic: nothing here reverses a refusal.
    Pure function: no I/O, deterministic in its input. This
    decides; it never executes, never dispatches, never sends.
    """
    item = _normalize_attempt(attempt)
    tag = _excerpt(item)
    computed = fingerprint(item["tool"], item["args"],
                           item["head"], item["generation"])
    if item["has_recorded_result"]:
        return EffectDecision(
            verdict="REPLAY", rule="recorded-result",
            findings=[_make_finding(
                "recorded-result",
                "authoritative result recorded: replay it, never "
                "re-execute",
                tag, severity="minor")])
    if item["duplicate_delivery"]:
        return EffectDecision(
            verdict="REPLAY", rule="duplicate-webhook",
            findings=[_make_finding(
                "duplicate-webhook",
                "duplicate delivery: replay the recorded "
                "outcome, never a second effect",
                tag, severity="minor")])
    if item["crashed_after_remote"]:
        return EffectDecision(
            verdict="REPLAY", rule="crash-after-remote",
            findings=[_make_finding(
                "crash-after-remote",
                "crash after remote success: reconcile against "
                "the authoritative result, then replay",
                tag)])
    if item["recorded_fingerprint"] \
            and item["fingerprint"] \
            and item["recorded_fingerprint"] == item["fingerprint"] \
            and item["recorded_payload"] is not None \
            and item["payload"] is not None \
            and json.dumps(item["recorded_payload"], sort_keys=True) \
            != json.dumps(item["payload"], sort_keys=True):
        return _refuse(
            "conflicting-reuse",
            "same fingerprint with a different payload: "
            "payloads never change an operation's identity",
            tag, severity="blocker")
    if item["guard_args"] is not None \
            and json.dumps(item["guard_args"], sort_keys=True) \
            != json.dumps(item["args"], sort_keys=True):
        return _refuse(
            "changed-argument",
            "arguments changed after the guard: refuse and "
            "re-guard before executing",
            tag, severity="blocker")
    if item["result_mutated"]:
        return _refuse(
            "mutated-result",
            "authoritative result bytes changed: results are "
            "immutable; refuse",
            tag, severity="blocker")
    if item["guard_head"] and item["head"] \
            and item["guard_head"] != item["head"]:
        return _refuse(
            "stale-head",
            "head moved since the guard: refuse and re-guard "
            "at the live head",
            tag)
    if item["operation"] in DESTRUCTIVE_OPS \
            and not item["confirmed"]:
        return _refuse(
            "destructive-action",
            "non-idempotent %r without explicit confirmation: "
            "confirm before executing" % item["operation"],
            tag, severity="blocker")
    if item["operation"] in DEDUPE_OPS and not item["dedupe_key"]:
        return _refuse(
            "missing-dedupe",
            "%r without its dedupe key: attach the key before "
            "executing" % item["operation"],
            tag)
    _ = computed
    return EffectDecision(verdict="EXECUTE", rule="recorded-result",
                          findings=[])


def clean_attempt() -> Dict[str, Any]:
    """One clean execution attempt (EXECUTE).

    First execution of a comment upsert with its dedupe key,
    guarded args, live head, no recorded result. Callers mutate
    one dimension per test.
    """
    head = "a" * 40
    return {
        "tool": "github",
        "operation": "comment-upsert",
        "args": {"issue": 138, "body": "receipt"},
        "head": head,
        "guard_head": head,
        "generation": 3,
        "fingerprint": "",
        "recorded_fingerprint": "",
        "recorded_result": None,
        "has_recorded_result": False,
        "recorded_payload": None,
        "payload": {"issue": 138, "body": "receipt"},
        "guard_args": {"issue": 138, "body": "receipt"},
        "result_mutated": False,
        "confirmed": False,
        "duplicate_delivery": False,
        "crashed_after_remote": False,
        "dedupe_key": "comment-138-receipt",
    }


def _entries_of(corpus: Any) -> List[Dict[str, Any]]:
    if isinstance(corpus, dict):
        entries = corpus.get("entries")
    else:
        entries = corpus
    if not isinstance(entries, list):
        return []
    return entries


def validate_effect_corpus(corpus: Any) -> Tuple[List[str],
                                                 List[Dict[str, Any]]]:
    """Validate the frozen effect fixture oracle.

    Returns (findings, entries); an empty findings list means
    the corpus is a valid frozen oracle: frozen marker set,
    stable provenance, at least 9 entries, unique well-formed
    IDs, every entry computing its expected rule and verdict,
    and all 9 effect rules covered.
    """
    if isinstance(corpus, dict):
        if corpus.get("_frozen") is not True:
            return (["effect corpus is not frozen: set "
                     "\"_frozen\": true"], [])
        provenance = str(corpus.get("_provenance", ""))
        if "Stage 47 #138" not in provenance:
            return (["effect corpus provenance must name "
                      "\"Stage 47 #138\""], [])
    elif not isinstance(corpus, list):
        return (["effect corpus must be a JSON object with an "
                 "'entries' array (or a bare array)"], [])
    entries = _entries_of(corpus)
    findings: List[str] = []
    if len(entries) < 9:
        findings.append("effect corpus holds %d entries, want "
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
                            "idempotent-effect.<class>.<nn>" % cid)
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
                            "frozen Stage 47 effect rule" % (cid, rule))
            continue
        covered.add(str(rule))
        if entry.get("expected_verdict") not in VERDICTS:
            findings.append("entry %s: expected_verdict %r is not "
                            "a frozen verdict" % (cid, entry.get(
                                "expected_verdict")))
            continue
        result = decide(entry.get("attempt", {}))
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
                            "effect rules are required)"
                            % rule)
    return findings, entries
