"""Stage 33 Standard half: frozen molds with proof invalidation.

A qualified Mold is a frozen verification contract: its payload hash
anchors every downstream authorization (DoR, capsule, evidence,
review, PR claim, Release Mold). Stage 33 (Risk R3) is the last line
of defense against a silently weakened oracle: when intent,
commands, oracles, or protected paths change, any proof recorded
against the old Mold content must stop authorizing work until the
Mold is explicitly reopened and requalified.

Run shape (plain data; missing keys fall back to total defaults,
never a crash)::

    {"mold": str,                        # mold name
     "mold_digest": str,                # sha256 hex of the CURRENT Mold payload
     "frozen_digest": str,              # sha256 hex recorded at freeze time
     "frozen_head": str,                # head the freeze was recorded at
     "head": str,                       # head this run executes at
     "intent_digest": str,              # sha256 of the linked intent text
     "frozen_intent_digest": str,       # intent digest recorded at freeze time
     "commands": [{"command": str, "digest": str}, ...],
     "frozen_commands": [{"command": str, "digest": str}, ...],
     "change_class": str,               # editorial|semantic|reopen (see below)
     "proof": {"verdict": str,          # prior qualification verdict reused
               "run_digest": str, ...},
     "protected_paths": [str, ...],
     "touched_paths": [str, ...],
     "provider": str}

Change classification (deterministic, frozen precedence):

1. ``reopen`` — an explicit, structured reopen record is present
   (``reopen: {"reason": str, "requalified": bool}`` with a
   non-empty reason). A reopened Mold re-enters qualification;
   invalidation findings do not fire, but the stale proof is
   still refused until ``requalified`` is true.
2. ``editorial`` — every observed delta is provably non-semantic:
   the Mold payload digest is unchanged AND the intent digest is
   unchanged AND every command digest is unchanged AND no
   protected path was touched. Only then may cached proof be
   reused.
3. ``semantic`` — anything else (payload, intent, or command
   digest drift; protected-path touch; unknown/missing freeze
   data). Semantic drift invalidates all prior proof.

Frozen rules (first listed first checked; findings appended in
this order, so output order is stable). Every finding names the
offending dimension:

1. ``mold-payload-changed`` — current ``mold_digest`` differs
   from ``frozen_digest`` without a structured reopen ->
   blocker. The Mold content moved under a live freeze.
2. ``intent-changed`` — ``intent_digest`` differs from
   ``frozen_intent_digest`` without a reopen -> blocker. The
   intent the Mold evidences is no longer the intent frozen.
3. ``command-changed`` — any frozen command digest differs, a
   frozen command is missing, or an unfrozen command appears,
   without a reopen -> blocker. The execution the proof ran
   under no longer exists.
4. ``protected-path-touched`` — any ``touched_paths`` entry at
   or under a ``protected_paths`` entry -> blocker. Protected
   ground moved; no cached authorization survives it.
5. ``stale-proof-reuse`` — a prior ``proof`` record (verdict or
   run_digest) is presented for a Mold whose freeze inputs
   drifted (any of rules 1-3 fired) -> blocker. Stale proof
   never re-authorizes work.
6. ``stale-review-reuse`` — a prior review/release approval
   (``prior_approval: {"kind": "review"|"release", ...}``) is
   presented after freeze drift -> blocker. Approvals bind to
   exact frozen content, not to the Mold name.
7. ``reopen-without-requalification`` — a structured reopen is
   present but ``requalified`` is false while new proof is
   claimed -> blocker. Reopening suspends invalidation; only
   requalification restores trust.

``freeze`` mints the freeze record; ``check_invalidation``
returns findings (empty means the cached proof still binds);
``validate_invalidation_corpus`` checks the frozen oracle.
Pure functions: no I/O, deterministic in their inputs.
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

RULES = (
    "mold-payload-changed",
    "intent-changed",
    "command-changed",
    "protected-path-touched",
    "stale-proof-reuse",
    "stale-review-reuse",
    "reopen-without-requalification",
)

CHANGE_CLASSES = ("editorial", "semantic", "reopen")

FREEZE_FIELDS = ("mold", "frozen_digest", "frozen_head",
                 "frozen_intent_digest", "frozen_commands",
                 "frozen_by")

FROZEN_BY = "proof_invalidation.freeze"

_ENTRY_ID_RE = None  # compiled lazily (stdlib re import below)

import re as _re

_ENTRY_ID_RE = _re.compile(r"^proof-inv\.[a-z-]+\.\d{2}$")


@dataclass
class InvalidationResult:
    """One freeze/invalidation outcome for one run."""

    change_class: str = "semantic"
    findings: List[Dict[str, str]] = field(default_factory=list)
    invalidated: bool = True

    @property
    def ok(self) -> bool:
        return not self.invalidated and not any(
            f.get("severity") == "blocker" for f in self.findings)


def _make_finding(rule: str, message: str, excerpt: str,
                  severity: str = "blocker") -> Dict[str, str]:
    """Build one structured finding dict for an invalidated run."""
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
    for key in ("id", "rule", "finding", "severity", "excerpt"):
        if key not in finding:
            repairs.append("finding is missing required key %r" % key)
    rule = finding.get("rule")
    if "rule" in finding and rule not in RULES:
        repairs.append("finding rule %r is not a frozen Stage 33 "
                       "invalidation rule" % (rule,))
    if "severity" in finding and finding.get("severity") not in (
            "blocker", "major", "minor"):
        repairs.append("finding severity %r must be "
                       "blocker|major|minor" % (finding.get("severity"),))
    return repairs


def _digest_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalize_commands(value: Any) -> List[Dict[str, str]]:
    if not isinstance(value, list):
        return []
    normalized = []
    for entry in value:
        if not isinstance(entry, dict):
            continue
        normalized.append({
            "command": str(entry.get("command", "")),
            "digest": str(entry.get("digest", "")),
        })
    return normalized


def _normalize_run(run: Any) -> Dict[str, Any]:
    """Fill total defaults so partial input never crashes."""
    run = run if isinstance(run, dict) else {}
    proof = run.get("proof")
    prior = run.get("prior_approval")
    reopen = run.get("reopen")
    return {
        "mold": str(run.get("mold", "")),
        "mold_digest": str(run.get("mold_digest", "")),
        "frozen_digest": str(run.get("frozen_digest", "")),
        "frozen_head": str(run.get("frozen_head", "")),
        "head": str(run.get("head", "")),
        "intent_digest": str(run.get("intent_digest", "")),
        "frozen_intent_digest": str(
            run.get("frozen_intent_digest", "")),
        "commands": _normalize_commands(run.get("commands")),
        "frozen_commands": _normalize_commands(
            run.get("frozen_commands")),
        "proof": dict(proof) if isinstance(proof, dict) else {},
        "prior_approval": dict(prior)
        if isinstance(prior, dict) else {},
        "reopen": dict(reopen) if isinstance(reopen, dict) else {},
        "protected_paths": [str(v) for v in run.get(
            "protected_paths", [])
            if isinstance(v, (str, int, float))]
        if isinstance(run.get("protected_paths"), list) else [],
        "touched_paths": [str(v) for v in run.get(
            "touched_paths", [])
            if isinstance(v, (str, int, float))]
        if isinstance(run.get("touched_paths"), list) else [],
        "provider": str(run.get("provider", "")),
    }


def _path_touched(touched: str, protected: str) -> bool:
    """True when a touched path is at or under a protected path."""
    clean = str(touched or "").replace("\\", "/").strip().lstrip("/")
    guard = str(protected or "").replace("\\", "/").strip().lstrip("/")
    if not clean or not guard:
        return False
    if clean == guard:
        return True
    return clean.startswith(guard.rstrip("/") + "/")


def _command_drift(run: Dict[str, Any]) -> List[str]:
    """Return human-readable command deltas; empty means stable."""
    frozen = {c["command"]: c["digest"]
              for c in run["frozen_commands"] if c["command"]}
    current = {c["command"]: c["digest"]
               for c in run["commands"] if c["command"]}
    deltas = []
    for command, digest in sorted(frozen.items()):
        if command not in current:
            deltas.append("command removed: %r" % command)
        elif current[command] != digest:
            deltas.append("command changed: %r" % command)
    for command in sorted(current):
        if command not in frozen:
            deltas.append("command added: %r" % command)
    return deltas


def _payload_drifted(run: Dict[str, Any]) -> bool:
    return bool(run["frozen_digest"]) and \
        run["mold_digest"] != run["frozen_digest"]


def _intent_drifted(run: Dict[str, Any]) -> bool:
    return bool(run["frozen_intent_digest"]) and \
        run["intent_digest"] != run["frozen_intent_digest"]


def classify_change(run: Any) -> str:
    """Return editorial|semantic|reopen for one run (pure)."""
    normalized = _normalize_run(run)
    reopen = normalized["reopen"]
    if str(reopen.get("reason", "")).strip():
        return "reopen"
    if _payload_drifted(normalized):
        return "semantic"
    if _intent_drifted(normalized):
        return "semantic"
    if _command_drift(normalized):
        return "semantic"
    if any(_path_touched(t, p)
           for t in normalized["touched_paths"]
           for p in normalized["protected_paths"]):
        return "semantic"
    if not normalized["frozen_digest"]:
        return "semantic"
    return "editorial"


def freeze(mold: str, mold_digest: str, head: str,
           intent_digest: str = "",
           commands: Any = None,
           provider: str = "") -> Dict[str, Any]:
    """Mint one freeze record as plain data (no I/O)."""
    return {
        "mold": str(mold),
        "frozen_digest": str(mold_digest),
        "frozen_head": str(head),
        "frozen_intent_digest": str(intent_digest),
        "frozen_commands": _normalize_commands(commands),
        "frozen_by": FROZEN_BY,
        "provider": str(provider),
    }


def check_invalidation(run: Any) -> InvalidationResult:
    """Check one run against its freeze; findings mean invalidated.

    A structured reopen suspends drift findings (including the
    stale-proof and stale-review refusals, which collapse into
    the single reopen-without-requalification finding) but still
    refuses stale proof until requalified. Pure function: no
    I/O, deterministic in its input.
    """
    normalized = _normalize_run(run)
    reopen = normalized["reopen"]
    reopened = bool(str(reopen.get("reason", "")).strip())
    requalified = bool(reopen.get("requalified", False))
    findings: List[Dict[str, str]] = []

    payload_drift = _payload_drifted(normalized)
    intent_drift = _intent_drifted(normalized)
    command_deltas = _command_drift(normalized)
    protected_hit = next(
        (t for t in normalized["touched_paths"]
         for p in normalized["protected_paths"]
         if _path_touched(t, p)), "")

    if not reopened:
        if payload_drift:
            findings.append(_make_finding(
                "mold-payload-changed",
                "Mold payload drifted under a live freeze "
                "(frozen %.12s != current %.12s): freeze a new "
                "Mold or file a structured reopen"
                % (normalized["frozen_digest"],
                   normalized["mold_digest"]),
                normalized["mold"] or "(unnamed mold)"))
        if intent_drift:
            findings.append(_make_finding(
                "intent-changed",
                "linked intent drifted under a live freeze: "
                "the proof evidences frozen intent %.12s, not "
                "current %.12s"
                % (normalized["frozen_intent_digest"],
                   normalized["intent_digest"]),
                normalized["mold"] or "(unnamed mold)"))
        if command_deltas:
            findings.append(_make_finding(
                "command-changed",
                "execution drifted under a live freeze (%s): "
                "the proof ran under commands that no longer "
                "exist" % "; ".join(command_deltas),
                normalized["mold"] or "(unnamed mold)"))
        if protected_hit:
            findings.append(_make_finding(
                "protected-path-touched",
                "protected ground moved (touched %r): no cached "
                "authorization survives a protected-path touch"
                % protected_hit,
                normalized["mold"] or "(unnamed mold)"))

    drift = payload_drift or intent_drift or bool(
        command_deltas) or bool(protected_hit)
    if normalized["proof"] and drift and not reopened:
        findings.append(_make_finding(
            "stale-proof-reuse",
            "prior proof (verdict %r) is bound to frozen "
            "content, not to the Mold name: requalify before "
            "reusing it"
            % str(normalized["proof"].get("verdict", "")),
            normalized["mold"] or "(unnamed mold)"))
    if normalized["prior_approval"] and drift and not reopened:
        findings.append(_make_finding(
            "stale-review-reuse",
            "prior %s approval is bound to exact frozen "
            "content: freeze drift voids it, re-approve after "
            "requalification"
            % str(normalized["prior_approval"].get(
                "kind", "review")),
            normalized["mold"] or "(unnamed mold)"))
    if reopened and not requalified and (
            normalized["proof"] or normalized["prior_approval"]):
        findings.append(_make_finding(
            "reopen-without-requalification",
            "Mold was reopened (%s) but not requalified: "
            "reopening suspends invalidation without restoring "
            "trust"
            % str(reopen.get("reason", ""))[:120],
            normalized["mold"] or "(unnamed mold)"))

    if reopened:
        change_class = "reopen"
    elif drift or not normalized["frozen_digest"]:
        change_class = "semantic"
    else:
        change_class = "editorial"
    return InvalidationResult(
        change_class=change_class,
        findings=findings,
        invalidated=bool(findings))


def _entries_of(corpus: Any) -> List[Dict[str, Any]]:
    if isinstance(corpus, dict):
        entries = corpus.get("entries")
    else:
        entries = corpus
    if not isinstance(entries, list):
        return []
    return entries


def validate_invalidation_corpus(
        corpus: Any) -> Tuple[List[str], List[Dict[str, Any]]]:
    """Validate the frozen invalidation fixture oracle.

    Returns (findings, entries); an empty findings list means
    the corpus is a valid frozen oracle: frozen marker set,
    stable provenance, at least 11 entries, unique
    well-formed IDs, every entry computing its expected rules,
    verdict class, and change class, and all 7 invalidation
    rules covered.
    """
    if isinstance(corpus, dict):
        if corpus.get("_frozen") is not True:
            return (["invalidation corpus is not frozen: set "
                     "\"_frozen\": true"], [])
        provenance = str(corpus.get("_provenance", ""))
        if "Stage 33 #124" not in provenance:
            return (["invalidation corpus provenance must name "
                      "\"Stage 33 #124\""], [])
    elif not isinstance(corpus, list):
        return (["invalidation corpus must be a JSON object with an "
                 "'entries' array (or a bare array)"], [])
    entries = _entries_of(corpus)
    findings: List[str] = []
    if len(entries) < 11:
        findings.append("invalidation corpus holds %d entries, want "
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
                            "proof-inv.<class>.<nn>" % cid)
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
        for key in ("expected_invalidated", "expected_change"):
            if key not in entry:
                findings.append("entry %s: %s is required" % (cid,
                                                              key))
        result = check_invalidation(entry.get("run", {}))
        computed = sorted({f["rule"] for f in result.findings})
        if sorted(str(r) for r in expected) != computed:
            findings.append("entry %s: expected_rules %r != "
                            "check %r"
                            % (cid, sorted(str(r)
                                           for r in expected),
                               computed))
        if bool(entry.get("expected_invalidated")) != \
                result.invalidated:
            findings.append("entry %s: expected_invalidated %r != "
                            "check %r" % (cid, entry.get(
                                "expected_invalidated"),
                                result.invalidated))
        if entry.get("expected_change") != result.change_class:
            findings.append("entry %s: expected_change %r != "
                            "check %r" % (cid, entry.get(
                                "expected_change"),
                                result.change_class))
    for rule in RULES:
        if rule not in covered:
            findings.append("rule %r has no entries (all 7 "
                            "invalidation rules are required)"
                            % rule)
    return findings, entries
