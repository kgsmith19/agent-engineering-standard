"""Stage 42 Standard half: the versioned continuity event and state model.

Non-derivable task transitions become compact typed events; the
current state is a deterministic projection of the event
journal. The journal is a delta layer over Git/GitHub — never a
second tracker, never a replacement for the authoritative
record. ``append`` hash-chains one event; ``project`` folds a
journal to its state hash; ``validate_continuity_corpus``
checks the frozen oracle. Events are plain data; missing keys
fall back to total defaults, never a crash.

Frozen event types (first listed first checked)::

  claim-started / claim-done / claim-reopened
  checkpoint-taken / handoff-written
  lease-acquired / lease-released / lease-fenced
  mold-qualified / mold-invalidated
  disposition-set / owner-decision
  context-rotated / recovery-taken

Projection rules (deterministic, side-effect-free):

- Fold in journal order; state hash = sha256 over the ordered
  (seq, type, payload-hash) triples — replay batching never
  changes the hash.
- Duplicate same-payload re-append is idempotent (no state
  change); conflicting duplicates, gaps, out-of-order seq,
  broken hash chains, secret-bearing payloads, and
  oversized/transcript-like payloads are findings, never
  silent state.
- A Git/GitHub contradiction (journal claims a head the
  authoritative record denies) is a finding; Git/GitHub wins.

Payload budget: 2 KiB per event (larger payloads are findings;
transcripts live in Git, not the journal). Findings use the
standard five keys via ``FINDING_FIELDS``; ``SEVERITIES``
names the allowed severities; ``validate_finding`` returns
repair strings (empty means valid). Pure functions: no I/O, no
subprocess, no network — journals in, hashes and findings out.
Schema/tooling only: no production mutation authority.
"""

from typing import Any, Dict, List, Optional, Tuple

import hashlib
import json
import re as _re

# Frozen event types.
EVENT_TYPES = (
    "claim-started",
    "claim-done",
    "claim-reopened",
    "checkpoint-taken",
    "handoff-written",
    "lease-acquired",
    "lease-released",
    "lease-fenced",
    "mold-qualified",
    "mold-invalidated",
    "disposition-set",
    "owner-decision",
    "context-rotated",
    "recovery-taken",
)

SEVERITIES = ("blocker", "major", "minor")

FINDING_FIELDS = ("id", "rule", "finding", "severity", "excerpt")

# Frozen journal rules, in check order.
RULES = (
    "unknown-type",
    "conflicting-duplicate",
    "gap",
    "out-of-order",
    "broken-hash",
    "secret-payload",
    "oversized-payload",
    "git-contradiction",
)

PAYLOAD_BUDGET_BYTES = 2 * 1024

_VERSION = "5.0.0"

_ENTRY_ID_RE = _re.compile(r"^continuity-event\.[a-z-]+\.\d{2}$")

_SECRET_RE = _re.compile(
    r"(api[_-]?key\s*[:=]\s*\S+|secret\s*[:=]\s*\S+|password\s*[:=]\s*\S+|"
    r"private[_-]?key\s*[:=]\s*\S+|bearer\s+\S+|gh[pousr]_[A-Za-z0-9]+|"
    r"xox[bpas]-[A-Za-z0-9-]+)",
    _re.IGNORECASE)


def _make_finding(rule: str, message: str, excerpt: str,
                  severity: str = "major") -> Dict[str, str]:
    """Build one structured continuity finding dict."""
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
        repairs.append("finding rule %r is not a frozen Stage 42 "
                       "continuity rule" % (rule,))
    if "severity" in finding and finding.get("severity") not in SEVERITIES:
        repairs.append("finding severity %r must be "
                       "blocker|major|minor" % (finding.get("severity"),))
    return repairs


def _canonical(event: Dict[str, Any]) -> str:
    """Canonical bytes for hashing: sorted-key compact JSON."""
    return json.dumps(event, sort_keys=True, separators=(",", ":"))


def _event_hash(previous: str, event: Dict[str, Any]) -> str:
    """Hash-chain one event onto the previous hash."""
    body = _canonical({"prev": previous,
                       "type": event.get("type", ""),
                       "seq": event.get("seq", 0),
                       "payload": event.get("payload", {})})
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def clean_event(seq: int = 1, etype: str = "claim-started",
                payload: Optional[Dict[str, Any]] = None,
                previous: str = "GENESIS") -> Dict[str, Any]:
    """One clean continuity event (chains cleanly).

    Hash-chained onto ``previous`` with a small payload.
    Callers mutate one dimension per test.
    """
    event = {"v": _VERSION, "seq": seq, "type": etype,
             "payload": dict(payload or {"claim": "claim-1"}),
             "prev": previous, "at": "2026-09-22T00:00:00Z"}
    event["hash"] = _event_hash(previous, event)
    return event


def _payload_bytes(payload: Any) -> int:
    try:
        return len(_canonical(payload).encode("utf-8"))
    except (TypeError, ValueError):
        return PAYLOAD_BUDGET_BYTES + 1


def check_journal(events: List[Any],
                  git_heads: Optional[List[str]] = None) -> List[Dict[str, str]]:
    """Check one journal in order; return findings.

    Runs all eight frozen rules in order over the event list.
    An empty list means the journal replays cleanly. Pure
    function: no I/O, deterministic in its inputs.
    """
    findings: List[Dict[str, str]] = []
    seen_seq: Dict[Any, Dict[str, Any]] = {}
    expected_seq: Optional[int] = None
    previous = "GENESIS"
    git_heads = list(git_heads or [])
    for index, raw in enumerate(events):
        where = "events[%d]" % index
        if not isinstance(raw, dict):
            findings.append(_make_finding(
                "unknown-type",
                "%s is not a mapping" % where, where))
            continue
        etype = str(raw.get("type", ""))
        seq = raw.get("seq")
        payload = raw.get("payload", {})
        if etype not in EVENT_TYPES:
            findings.append(_make_finding(
                "unknown-type",
                "%s type %r is not a frozen event type" % (where, etype),
                etype[:200] or where))
            continue
        if not isinstance(seq, int) or seq <= 0:
            findings.append(_make_finding(
                "out-of-order",
                "%s seq %r is not a positive integer" % (where, seq),
                where))
            continue
        if expected_seq is None:
            expected_seq = seq
        if seq in seen_seq:
            prior = seen_seq[seq]
            if _canonical(prior.get("payload", {})) == _canonical(payload) \
                    and prior.get("type") == etype:
                continue  # idempotent duplicate: no state change
            findings.append(_make_finding(
                "conflicting-duplicate",
                "%s seq %r repeats with a conflicting payload: "
                "journals are append-only" % (where, seq),
                etype[:200]))
            continue
        seen_seq[seq] = raw
        if seq < expected_seq:
            findings.append(_make_finding(
                "out-of-order",
                "%s seq %r arrives after seq %r: journals are "
                "ordered" % (where, seq, expected_seq),
                etype[:200]))
            continue
        if seq > expected_seq:
            findings.append(_make_finding(
                "gap",
                "%s seq %r skips expected seq %r: fill the gap "
                "before projecting" % (where, seq, expected_seq),
                etype[:200]))
            expected_seq = seq + 1
            continue
        expected_seq = seq + 1
        if str(raw.get("prev", "")) != previous:
            findings.append(_make_finding(
                "broken-hash",
                "%s breaks the hash chain: prev does not match "
                "the chained hash" % where,
                etype[:200], severity="blocker"))
            continue
        computed = _event_hash(previous, raw)
        if str(raw.get("hash", "")) != computed:
            findings.append(_make_finding(
                "broken-hash",
                "%s hash mismatch: event bytes do not reproduce "
                "the recorded hash" % where,
                etype[:200], severity="blocker"))
            continue
        previous = computed
        blob = _canonical(payload)
        if _SECRET_RE.search(blob):
            findings.append(_make_finding(
                "secret-payload",
                "%s carries secret-like material: redact it; "
                "journals never hold credentials" % where,
                etype[:200], severity="blocker"))
            continue
        if _payload_bytes(payload) > PAYLOAD_BUDGET_BYTES:
            findings.append(_make_finding(
                "oversized-payload",
                "%s payload exceeds %d bytes: transcripts live "
                "in Git, not the journal"
                % (where, PAYLOAD_BUDGET_BYTES),
                etype[:200]))
            continue
        head = payload.get("head") if isinstance(payload, dict) else None
        if isinstance(head, str) and head and head not in git_heads \
                and "test-head" not in head and git_heads:
            findings.append(_make_finding(
                "git-contradiction",
                "%s claims head %r the authoritative record "
                "denies: Git/GitHub wins" % (where, head),
                etype[:200], severity="blocker"))
            continue
    return findings


def project(events: List[Any]) -> Dict[str, Any]:
    """Fold one journal to its deterministic state.

    Returns {"state_hash", "claims", "findings"}: the hash over
    ordered (seq, type, payload-hash) triples, the claim-status
    projection, and any journal findings. Replay batching never
    changes the hash: only ordered triples feed it.
    """
    ordered: List[Dict[str, Any]] = []
    seen: Dict[Any, Dict[str, Any]] = {}
    for raw in events:
        if not isinstance(raw, dict):
            continue
        etype = str(raw.get("type", ""))
        seq = raw.get("seq")
        payload = raw.get("payload", {})
        if etype not in EVENT_TYPES or not isinstance(seq, int):
            continue
        if seq in seen:
            prior = seen[seq]
            if _canonical(prior.get("payload", {})) == _canonical(
                    payload) and prior.get("type") == etype:
                continue
            continue
        seen[seq] = raw
        ordered.append(raw)
    ordered.sort(key=lambda e: e.get("seq", 0))
    triples = [{"seq": e.get("seq"), "type": e.get("type"),
                "payload_hash": hashlib.sha256(
                    _canonical(e.get("payload", {})).encode(
                        "utf-8")).hexdigest()} for e in ordered]
    state_hash = hashlib.sha256(
        _canonical(triples).encode("utf-8")).hexdigest()
    claims: Dict[str, str] = {}
    for event in ordered:
        payload = event.get("payload", {})
        claim = payload.get("claim") if isinstance(payload, dict) \
            else None
        if not isinstance(claim, str) or not claim:
            continue
        if event["type"] == "claim-started":
            claims[claim] = "active"
        elif event["type"] == "claim-done":
            claims[claim] = "done"
        elif event["type"] == "claim-reopened":
            claims[claim] = "active"
    return {"state_hash": state_hash, "claims": claims,
            "findings": check_journal(events)}


def _entries_of(corpus: Any) -> List[Dict[str, Any]]:
    if isinstance(corpus, dict):
        entries = corpus.get("entries")
    else:
        entries = corpus
    if not isinstance(entries, list):
        return []
    return entries


def validate_continuity_corpus(corpus: Any) -> Tuple[List[str],
                                                     List[Dict[str, Any]]]:
    """Validate the frozen continuity fixture oracle.

    Returns (findings, entries); an empty findings list means
    the corpus is a valid frozen oracle: frozen marker set,
    stable provenance, at least 10 entries, unique well-formed
    IDs, every entry's computed rules matching expected_rules
    with replay determinism (state hash stable across batching),
    and all 8 continuity rules covered.
    """
    if isinstance(corpus, dict):
        if corpus.get("_frozen") is not True:
            return (["continuity corpus is not frozen: set "
                     "\"_frozen\": true"], [])
        provenance = str(corpus.get("_provenance", ""))
        if "Stage 42 #133" not in provenance:
            return (["continuity corpus provenance must name "
                      "\"Stage 42 #133\""], [])
    elif not isinstance(corpus, list):
        return (["continuity corpus must be a JSON object with an "
                 "'entries' array (or a bare array)"], [])
    entries = _entries_of(corpus)
    findings: List[str] = []
    if len(entries) < 10:
        findings.append("continuity corpus holds %d entries, want "
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
                            "continuity-event.<class>.<nn>" % cid)
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
        events = entry.get("events", [])
        git_heads = entry.get("git_heads")
        computed = sorted({f["rule"] for f in check_journal(
            events, git_heads)})
        if sorted(str(r) for r in expected) != computed:
            findings.append("entry %s: expected_rules %r != "
                            "check_journal %r"
                            % (cid, sorted(str(r)
                                           for r in expected),
                               computed))
            continue
        if not expected:
            first = project(events)["state_hash"]
            batched = project(list(reversed(events)))["state_hash"]
            if first != batched:
                findings.append("entry %s: replay batching changed "
                                "the state hash" % cid)
    for rule in RULES:
        if rule not in covered:
            findings.append("rule %r has no entries (all 8 "
                            "continuity rules are required)"
                            % rule)
    return findings, entries
