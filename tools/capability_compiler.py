"""Stage 54a Standard half: the capability compiler.

Constrain what the agent can see and do so routine compliance
never depends on memory or repeated approvals: compile
role/phase/task profiles into concrete capability bounds —
read/write roots, execute and network allowlists, secret
handles, external-effect gates, owner-gated operations.
``compile`` maps one profile to its bounds; ``check`` maps one
requested action to ALLOW / DENY / ESCALATE;
``validate_capability_corpus`` checks the frozen oracle.
Profiles and actions are plain data; missing keys fall back to
total defaults, never a crash.

Frozen capability classes::

  read / write / execute / network / secrets / effects

Frozen rules, in check order (first hit decides)::

  foreign-read       — read outside read roots: DENY.
  foreign-write      — write outside write roots: DENY.
  frozen-mold        — write to a frozen Mold: DENY.
  direct-main        — direct-to-main mutation: DENY (PR only).
  secret-mount       — raw secret where a handle belongs: DENY.
  arbitrary-egress   — egress outside the allowlist: DENY.
  mcp-research-write — MCP write during research phase: DENY.
  no-sandbox         — provider without sandbox nor wrapper:
                       ESCALATE with dry-run/report.
  owner-escalation   — owner-approved escalation: ALLOW with
                       the approval recorded.
  focused-edit       — allowed focused edit inside roots: ALLOW.
  test-command       — allowlisted test command: ALLOW.

Starts dry-run/report with sharp-edge enforcement (foreign
writes, frozen molds, direct-main, raw secrets, arbitrary
egress deny immediately); full hard enforcement waits for
false-block and approval-reduction data. Provider-specific
sandbox mechanics belong to the agent-extensions half (54b);
this half owns policy compilation. Findings use the standard
five keys via ``FINDING_FIELDS``; ``SEVERITIES`` names the
allowed severities; ``validate_finding`` returns repair strings
(empty means valid). Pure functions: no I/O, no subprocess, no
network — profiles and actions in, bounds out.
"""

from typing import Any, Dict, List, Optional, Tuple

import re as _re

# Frozen capability classes.
CLASSES = (
    "read",
    "write",
    "execute",
    "network",
    "secrets",
    "effects",
)

VERDICTS = ("ALLOW", "DENY", "ESCALATE")

SEVERITIES = ("blocker", "major", "minor")

FINDING_FIELDS = ("id", "rule", "finding", "severity", "excerpt")

# Frozen capability rules, in check order.
RULES = (
    "foreign-read",
    "foreign-write",
    "frozen-mold",
    "direct-main",
    "secret-mount",
    "arbitrary-egress",
    "mcp-research-write",
    "no-sandbox",
    "owner-escalation",
    "focused-edit",
    "test-command",
)

# Verdict each rule carries.
RULE_VERDICTS = {
    "foreign-read": "DENY",
    "foreign-write": "DENY",
    "frozen-mold": "DENY",
    "direct-main": "DENY",
    "secret-mount": "DENY",
    "arbitrary-egress": "DENY",
    "mcp-research-write": "DENY",
    "no-sandbox": "ESCALATE",
    "owner-escalation": "ALLOW",
    "focused-edit": "ALLOW",
    "test-command": "ALLOW",
}

FROZEN_MOLD_MARKERS = ("Canonical/corpus/", "Canonical/schemas/",
                       "Canonical/capabilities.json")

# Entry-ID shape for the frozen oracle.
_ENTRY_ID_RE = _re.compile(r"^capability-compiler\.[a-z-]+\.\d{2}$")


def _make_finding(rule: str, message: str, excerpt: str,
                  severity: str = "major") -> Dict[str, str]:
    """Build one structured capability finding dict."""
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
        repairs.append("finding rule %r is not a frozen Stage 54a "
                       "capability rule" % (rule,))
    if "severity" in finding and finding.get("severity") not in SEVERITIES:
        repairs.append("finding severity %r must be "
                       "blocker|major|minor" % (finding.get("severity"),))
    return repairs


def _excerpt(action: Dict[str, Any]) -> str:
    """Short evidence excerpt naming the action target."""
    for key in ("target", "command", "endpoint", "action"):
        value = action.get(key)
        if isinstance(value, (str, int, float)) and str(value).strip():
            return str(value)[:200]
    return "(capability)"


def _under_any(path: str, roots: List[str]) -> bool:
    text = str(path or "").replace("\\", "/").strip().lstrip("/")
    for root in roots:
        guard = str(root or "").replace("\\", "/").strip().lstrip("/")
        if not guard:
            continue
        if text == guard or text.startswith(guard.rstrip("/") + "/"):
            return True
    return False


def _normalize_action(action: Any) -> Dict[str, Any]:
    """Fill total defaults so partial input never crashes."""
    action = action if isinstance(action, dict) else {}

    def _strs(value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(v) for v in value
                    if isinstance(v, (str, int, float))]
        return []

    return {
        "kind": str(action.get("kind", "")),
        "target": str(action.get("target", "") or ""),
        "command": str(action.get("command", "") or ""),
        "endpoint": str(action.get("endpoint", "") or ""),
        "phase": str(action.get("phase", "") or ""),
        "direct_main": bool(action.get("direct_main", False)),
        "raw_secret": bool(action.get("raw_secret", False)),
        "handle": str(action.get("handle", "") or ""),
        "sandbox": bool(action.get("sandbox", False)),
        "wrapper": bool(action.get("wrapper", False)),
        "owner_approved": bool(action.get(
            "owner_approved", False)),
        "test_command": bool(action.get("test_command", False)),
        "mcp_write": bool(action.get("mcp_write", False)),
        "read_roots": _strs(action.get("read_roots")),
        "write_roots": _strs(action.get("write_roots")),
        "exec_allow": _strs(action.get("exec_allow")),
        "net_allow": _strs(action.get("net_allow")),
    }


class CapabilityDecision:
    """One capability outcome for one action."""

    verdict: str = "DENY"
    rule: str = "foreign-read"
    findings: List[Dict[str, str]] = []  # type: ignore[assignment]

    def __init__(self, verdict: str = "DENY",
                 rule: str = "foreign-read",
                 findings: Optional[List[Dict[str, str]]] = None):
        self.verdict = verdict
        self.rule = rule
        self.findings = list(findings or [])


def _decide(rule: str, message: str, tag: str,
            severity: str = "major") -> CapabilityDecision:
    return CapabilityDecision(
        verdict=RULE_VERDICTS[rule], rule=rule,
        findings=[_make_finding(rule, message, tag,
                                severity=severity)])


def check(action: Any) -> CapabilityDecision:
    """Map one requested action to ALLOW / DENY / ESCALATE.

    Sharp edges deny immediately (foreign paths, frozen molds,
    direct-main, raw secrets, arbitrary egress, research MCP
    writes); sandbox gaps escalate dry-run; owner approvals
    allow with the approval recorded; focused edits and
    allowlisted test commands allow. Pure function: no I/O,
    deterministic in its input. This bounds reach; it never
    performs the action.
    """
    item = _normalize_action(action)
    tag = _excerpt(item)
    kind = item["kind"]
    if kind == "read":
        if not _under_any(item["target"], item["read_roots"]):
            return _decide(
                "foreign-read",
                "read of %r outside read roots: DENY"
                % item["target"],
                tag, severity="blocker")
        return CapabilityDecision(verdict="ALLOW",
                                  rule="focused-edit",
                                  findings=[])
    if kind == "write":
        for marker in FROZEN_MOLD_MARKERS:
            if str(item["target"]).replace(
                    "\\", "/").lstrip("/").startswith(marker):
                return _decide(
                    "frozen-mold",
                    "write to frozen Mold %r: DENY, regenerate "
                    "via the owning tool" % item["target"],
                    tag, severity="blocker")
        if item["direct_main"]:
            return _decide(
                "direct-main",
                "direct-to-main mutation: DENY, land via PR "
                "only",
                tag, severity="blocker")
        if not _under_any(item["target"], item["write_roots"]):
            return _decide(
                "foreign-write",
                "write to %r outside write roots: DENY"
                % item["target"],
                tag, severity="blocker")
        if item["phase"] == "research" and item["mcp_write"]:
            return _decide(
                "mcp-research-write",
                "MCP write during research: DENY, research is "
                "read-only",
                tag)
        return _decide(
            "focused-edit",
            "focused edit inside write roots: ALLOW",
            tag, severity="minor")
    if kind == "secret":
        if item["raw_secret"] or not item["handle"]:
            return _decide(
                "secret-mount",
                "raw secret where a handle belongs: DENY, mount "
                "the scoped handle",
                tag, severity="blocker")
        return CapabilityDecision(verdict="ALLOW",
                                  rule="focused-edit",
                                  findings=[])
    if kind == "egress":
        if not _under_any(item["endpoint"], item["net_allow"]) \
                and item["endpoint"] not in item["net_allow"]:
            return _decide(
                "arbitrary-egress",
                "egress to %r outside the allowlist: DENY"
                % item["endpoint"],
                tag, severity="blocker")
        return CapabilityDecision(verdict="ALLOW",
                                  rule="focused-edit",
                                  findings=[])
    if kind == "execute":
        if item["test_command"] and item["command"] in item[
                "exec_allow"]:
            return _decide(
                "test-command",
                "allowlisted test command: ALLOW",
                tag, severity="minor")
        if item["owner_approved"]:
            return _decide(
                "owner-escalation",
                "owner-approved escalation: ALLOW with the "
                "approval recorded",
                tag, severity="minor")
        if not item["sandbox"] and not item["wrapper"]:
            return _decide(
                "no-sandbox",
                "provider without sandbox nor wrapper: "
                "ESCALATE dry-run/report",
                tag)
        if item["command"] not in item["exec_allow"]:
            return _decide(
                "arbitrary-egress",
                "command %r outside the execute allowlist: "
                "DENY" % item["command"],
                tag)
        return CapabilityDecision(verdict="ALLOW",
                                  rule="focused-edit",
                                  findings=[])
    return _decide(
        "foreign-read",
        "unknown action kind %r: DENY by default" % (kind,),
        tag, severity="blocker")


def compile(profile: Any) -> Dict[str, Any]:  # noqa: A001 - frozen Stage 54a name
    """Compile one role/phase/task profile into capability bounds.

    Returns {"read_roots", "write_roots", "exec_allow",
    "net_allow", "secret_handles", "mode"}: dry-run/report by
    default with sharp edges denying. Pure function: no I/O,
    deterministic in its input.
    """
    profile = profile if isinstance(profile, dict) else {}
    role = str(profile.get("role", "") or "builder")
    return {
        "read_roots": ["tools/", "tests/",
                       "Canonical/corpus/"],
        "write_roots": ["tools/", "tests/"]
        if role == "builder" else ["evidence/"],
        "exec_allow": ["python tools/standardctl.py verify",
                       "python -m unittest"],
        "net_allow": ["api.github.com"],
        "secret_handles": ["scoped-secret-handle"],
        "mode": "dry-run/report with sharp-edge enforcement",
    }


def clean_action() -> Dict[str, Any]:
    """One clean capability action (ALLOW).

    A focused builder edit inside write roots. Callers mutate
    one dimension per test.
    """
    return {
        "kind": "write",
        "target": "tools/demo.py",
        "command": "",
        "endpoint": "",
        "phase": "implement",
        "direct_main": False,
        "raw_secret": False,
        "handle": "",
        "sandbox": True,
        "wrapper": False,
        "owner_approved": False,
        "test_command": False,
        "mcp_write": False,
        "read_roots": ["tools/", "tests/"],
        "write_roots": ["tools/", "tests/"],
        "exec_allow": ["python tools/standardctl.py verify"],
        "net_allow": ["api.github.com"],
    }


def _entries_of(corpus: Any) -> List[Dict[str, Any]]:
    if isinstance(corpus, dict):
        entries = corpus.get("entries")
    else:
        entries = corpus
    if not isinstance(entries, list):
        return []
    return entries


def validate_capability_corpus(corpus: Any) -> Tuple[List[str],
                                                     List[Dict[str, Any]]]:
    """Validate the frozen capability fixture oracle.

    Returns (findings, entries); an empty findings list means
    the corpus is a valid frozen oracle: frozen marker set,
    stable provenance, at least 11 entries, unique well-formed
    IDs, every entry computing its expected rule and verdict,
    and all 11 capability rules covered.
    """
    if isinstance(corpus, dict):
        if corpus.get("_frozen") is not True:
            return (["capability corpus is not frozen: set "
                     "\"_frozen\": true"], [])
        provenance = str(corpus.get("_provenance", ""))
        if "Stage 54a #145" not in provenance:
            return (["capability corpus provenance must name "
                      "\"Stage 54a #145\""], [])
    elif not isinstance(corpus, list):
        return (["capability corpus must be a JSON object with an "
                 "'entries' array (or a bare array)"], [])
    entries = _entries_of(corpus)
    findings: List[str] = []
    if len(entries) < 11:
        findings.append("capability corpus holds %d entries, want "
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
                            "capability-compiler.<class>.<nn>" % cid)
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
                            "frozen Stage 54a capability rule"
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
        result = check(entry.get("action", {}))
        if result.rule != rule:
            findings.append("entry %s: expected_rule %r != "
                            "check %r" % (cid, rule, result.rule))
        if result.verdict != entry.get("expected_verdict"):
            findings.append("entry %s: expected_verdict %r != "
                            "check %r" % (cid, entry.get(
                                "expected_verdict"),
                                result.verdict))
    for rule in RULES:
        if rule not in covered:
            findings.append("rule %r has no entries (all 11 "
                            "capability rules are required)"
                            % rule)
    return findings, entries
