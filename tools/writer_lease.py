"""Stage 46 Standard half: the generation-bound one-writer lease.

One mutable writer per slice across provider, process, host,
and context changes. The lease is a fencing-generation CAS
record: acquire mints a generation, transfer moves the holder
forward one generation, release closes the lease, reconcile
re-derives truth from branch/commits/process/report state
(including cloud workspace loss). Stale generations, late
heartbeats on old generations, expired leases, and second
claimants refuse with deterministic conflict output;
read-only agents never need a lease; owner recovery from a
stuck lease is explicit, never automatic silent override.
``decide`` maps one lease operation to GRANT / REFUSE /
RECOVER / RELEASED; ``validate_lease_corpus`` checks the
frozen oracle. Operations are plain data; missing keys fall
back to total defaults, never a crash.

Frozen operations: acquire, heartbeat, transfer, release,
write, reconcile, owner-recover.

Frozen rules, in check order (first hit decides)::

  concurrent-claim  — second claimant while a live lease holds.
  stale-generation  — operation generation behind the lease.
  expired-lease     — lease past its heartbeat deadline.
  late-heartbeat    — heartbeat on a superseded generation.
  provider-transfer — holder moved provider without transfer.
  workspace-lost    — cloud workspace lost: reconcile first.
  partition-split   — network partition: both sides fence, the
                      newer generation wins on reconcile.
  process-dead      — holder process dead: recover via CAS.
  owner-recovery    — explicit owner release of a stuck lease.
  clean-release     — holder released: the slice is free.
  no-lease          — no lease exists where one is required.

A clean acquire/heartbeat/transfer/write/reconcile is GRANT.
Findings use the standard five keys via ``FINDING_FIELDS``;
``SEVERITIES`` names the allowed severities;
``validate_finding`` returns repair strings (empty means
valid). Pure functions: no I/O, no subprocess, no network —
operations in, verdicts out. No central coordination service:
Git/GitHub state plus the CAS record is the coordinator.
"""

from typing import Any, Dict, List, Optional, Tuple

import re as _re

# Frozen lease operations.
OPERATIONS = (
    "acquire",
    "heartbeat",
    "transfer",
    "release",
    "write",
    "reconcile",
    "owner-recover",
)

VERDICTS = ("GRANT", "REFUSE", "RECOVER", "RELEASED")

SEVERITIES = ("blocker", "major", "minor")

FINDING_FIELDS = ("id", "rule", "finding", "severity", "excerpt")

# Frozen lease rules, in check order.
RULES = (
    "concurrent-claim",
    "stale-generation",
    "expired-lease",
    "late-heartbeat",
    "provider-transfer",
    "workspace-lost",
    "partition-split",
    "process-dead",
    "owner-recovery",
    "clean-release",
    "no-lease",
)

OWNER_LOGIN = "kgsmith19"

# Heartbeat deadline in abstract ticks (advisory pilot scale).
HEARTBEAT_DEADLINE = 3

# Entry-ID shape for the frozen oracle.
_ENTRY_ID_RE = _re.compile(r"^writer-lease\.[a-z-]+\.\d{2}$")


def _make_finding(rule: str, message: str, excerpt: str,
                  severity: str = "major") -> Dict[str, str]:
    """Build one structured lease finding dict."""
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
        repairs.append("finding rule %r is not a frozen Stage 46 "
                       "lease rule" % (rule,))
    if "severity" in finding and finding.get("severity") not in SEVERITIES:
        repairs.append("finding severity %r must be "
                       "blocker|major|minor" % (finding.get("severity"),))
    return repairs


def _excerpt(operation: Dict[str, Any]) -> str:
    """Short evidence excerpt naming the slice/holder."""
    for key in ("slice", "holder", "agent"):
        value = operation.get(key)
        if isinstance(value, (str, int, float)) and str(value).strip():
            return str(value)[:200]
    return "(lease)"


def _normalize_operation(operation: Any) -> Dict[str, Any]:
    """Fill total defaults so partial input never crashes."""
    operation = operation if isinstance(operation, dict) else {}
    lease = operation.get("lease")
    return {
        "op": str(operation.get("op", "") or ""),
        "agent": str(operation.get("agent", "")),
        "slice": str(operation.get("slice", "")),
        "lease": dict(lease) if isinstance(lease, dict) else {},
        "generation": int(operation.get("generation") or 0),
        "ticks_since_heartbeat": int(operation.get(
            "ticks_since_heartbeat") or 0),
        "holder_alive": bool(operation.get(
            "holder_alive", True)),
        "provider": str(operation.get("provider", "") or ""),
        "transfer_to": str(operation.get("transfer_to", "") or ""),
        "transfer_provider": str(operation.get(
            "transfer_provider", "") or ""),
        "workspace_present": bool(operation.get(
            "workspace_present", True)),
        "partitioned": bool(operation.get("partitioned", False)),
        "owner": str(operation.get("owner", "") or ""),
        "read_only": bool(operation.get("read_only", False)),
    }


class LeaseDecision:
    """One lease outcome for one operation."""

    verdict: str = "REFUSE"
    rule: str = "no-lease"
    findings: List[Dict[str, str]] = []  # type: ignore[assignment]

    def __init__(self, verdict: str = "REFUSE", rule: str = "no-lease",
                 findings: Optional[List[Dict[str, str]]] = None):
        self.verdict = verdict
        self.rule = rule
        self.findings = list(findings or [])


def _refuse(rule: str, message: str, tag: str,
            severity: str = "major") -> LeaseDecision:
    return LeaseDecision(
        verdict="REFUSE", rule=rule,
        findings=[_make_finding(rule, message, tag,
                                severity=severity)])


def _recover(rule: str, message: str, tag: str) -> LeaseDecision:
    return LeaseDecision(
        verdict="RECOVER", rule=rule,
        findings=[_make_finding(rule, message, tag)])


def decide(operation: Any) -> LeaseDecision:
    """Map one lease operation to GRANT / REFUSE / RECOVER /
    RELEASED.

    Read-only agents never need a lease (GRANT, no-lease).
    Owner recovery is explicit (owner login + stuck lease).
    Acquire on a free slice grants; a second claimant refuses.
    Stale generations, expired heartbeats, late heartbeats,
    untransferred provider moves, lost workspaces, partitions,
    and dead holders refuse or recover deterministically. A
    clean operation is GRANT. Pure function: no I/O,
    deterministic in its input. This decides; it never mints
    authority outside CAS order, never silently overrides.
    """
    item = _normalize_operation(operation)
    tag = _excerpt(item)
    lease = item["lease"]
    held = bool(lease.get("holder"))
    generation = int(lease.get("generation") or 0)
    op = item["op"]
    if op not in OPERATIONS:
        return _refuse(
            "no-lease",
            "unknown operation %r: use one of %s"
            % (op, ", ".join(OPERATIONS)),
            tag)
    if item["read_only"]:
        return LeaseDecision(verdict="GRANT", rule="no-lease",
                             findings=[])
    if op == "owner-recover":
        if item["owner"] == OWNER_LOGIN and held:
            return LeaseDecision(
                verdict="RELEASED", rule="owner-recovery",
                findings=[_make_finding(
                    "owner-recovery",
                    "owner %r explicitly released the stuck "
                    "lease held by %r: the slice is free"
                    % (OWNER_LOGIN, lease.get("holder")),
                    tag)])
        return _refuse(
            "owner-recovery",
            "owner recovery needs the owner login plus a stuck "
            "lease: silent override never releases",
            tag, severity="blocker")
    if op == "acquire":
        if held:
            return _refuse(
                "concurrent-claim",
                "slice %r already leased to %r at generation "
                "%d: one writer only"
                % (item["slice"], lease.get("holder"),
                   generation),
                tag, severity="blocker")
        return LeaseDecision(verdict="GRANT", rule="no-lease",
                             findings=[])
    if not held:
        return _refuse(
            "no-lease",
            "no lease held for slice %r: acquire before %s"
            % (item["slice"], op),
            tag)
    if op == "heartbeat" and item["generation"] != generation:
        return _refuse(
            "late-heartbeat",
            "heartbeat on superseded generation %d (lease at "
            "%d): only the current generation heartbeats"
            % (item["generation"], generation),
            tag)
    if item["generation"] < generation:
        return _refuse(
            "stale-generation",
            "operation generation %d behind lease generation "
            "%d: a stale writer is fenced"
            % (item["generation"], generation),
            tag, severity="blocker")
    if item["ticks_since_heartbeat"] > HEARTBEAT_DEADLINE:
        return _refuse(
            "expired-lease",
            "lease expired (%d ticks past heartbeat, deadline "
            "%d): re-acquire via CAS"
            % (item["ticks_since_heartbeat"],
               HEARTBEAT_DEADLINE),
            tag)
    if item["provider"] and lease.get("provider") \
            and item["provider"] != lease.get("provider") \
            and op != "transfer" and not item["transfer_to"]:
        return _refuse(
            "provider-transfer",
            "holder moved provider %r -> %r without transfer: "
            "transfer the lease forward one generation"
            % (lease.get("provider"), item["provider"]),
            tag, severity="blocker")
    if not item["workspace_present"]:
        return _recover(
            "workspace-lost",
            "cloud workspace lost: reconcile against "
            "branch/commits/report state before writing",
            tag)
    if item["partitioned"]:
        return _recover(
            "partition-split",
            "network partition: both sides fence; the newer "
            "generation wins on reconcile",
            tag)
    if not item["holder_alive"]:
        return _recover(
            "process-dead",
            "holder process dead: recover the lease via CAS at "
            "a new generation",
            tag)
    if op == "release":
        if item["agent"] and item["agent"] != lease.get("holder"):
            return _refuse(
                "concurrent-claim",
                "release by %r refused: only holder %r releases"
                % (item["agent"], lease.get("holder")),
                tag, severity="blocker")
        return LeaseDecision(
            verdict="RELEASED", rule="clean-release",
            findings=[_make_finding(
                "clean-release",
                "holder %r released generation %d: the slice "
                "is free" % (lease.get("holder"), generation),
                tag, severity="minor")])
    if op == "transfer":
        if not item["transfer_to"]:
            return _refuse(
                "provider-transfer",
                "transfer names no recipient: transfer moves "
                "the holder forward one generation",
                tag)
        return LeaseDecision(verdict="GRANT",
                             rule="provider-transfer",
                             findings=[])
    if op == "reconcile":
        return LeaseDecision(verdict="GRANT", rule="no-lease",
                             findings=[])
    return LeaseDecision(verdict="GRANT", rule="no-lease",
                         findings=[])


def clean_operation() -> Dict[str, Any]:
    """One clean lease operation (GRANT).

    A heartbeat at the current generation with a live holder,
    fresh heartbeat, present workspace, no partition. Callers
    mutate one dimension per test.
    """
    return {
        "op": "heartbeat",
        "agent": "builder-1",
        "slice": "slice-1",
        "lease": {"holder": "builder-1", "generation": 3,
                  "provider": "anthropic"},
        "generation": 3,
        "ticks_since_heartbeat": 0,
        "holder_alive": True,
        "provider": "anthropic",
        "transfer_to": "",
        "transfer_provider": "",
        "workspace_present": True,
        "partitioned": False,
        "owner": "",
        "read_only": False,
    }


def _entries_of(corpus: Any) -> List[Dict[str, Any]]:
    if isinstance(corpus, dict):
        entries = corpus.get("entries")
    else:
        entries = corpus
    if not isinstance(entries, list):
        return []
    return entries


def validate_lease_corpus(corpus: Any) -> Tuple[List[str],
                                                List[Dict[str, Any]]]:
    """Validate the frozen lease fixture oracle.

    Returns (findings, entries); an empty findings list means
    the corpus is a valid frozen oracle: frozen marker set,
    stable provenance, at least 11 entries, unique well-formed
    IDs, every entry computing its expected rule and verdict,
    and all 11 lease rules covered.
    """
    if isinstance(corpus, dict):
        if corpus.get("_frozen") is not True:
            return (["lease corpus is not frozen: set "
                     "\"_frozen\": true"], [])
        provenance = str(corpus.get("_provenance", ""))
        if "Stage 46 #137" not in provenance:
            return (["lease corpus provenance must name "
                      "\"Stage 46 #137\""], [])
    elif not isinstance(corpus, list):
        return (["lease corpus must be a JSON object with an "
                 "'entries' array (or a bare array)"], [])
    entries = _entries_of(corpus)
    findings: List[str] = []
    if len(entries) < 11:
        findings.append("lease corpus holds %d entries, want "
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
                            "writer-lease.<class>.<nn>" % cid)
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
                            "frozen Stage 46 lease rule" % (cid, rule))
            continue
        covered.add(str(rule))
        if entry.get("expected_verdict") not in VERDICTS:
            findings.append("entry %s: expected_verdict %r is not "
                            "a frozen verdict" % (cid, entry.get(
                                "expected_verdict")))
            continue
        result = decide(entry.get("operation", {}))
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
            findings.append("rule %r has no entries (all 11 "
                            "lease rules are required)"
                            % rule)
    return findings, entries
