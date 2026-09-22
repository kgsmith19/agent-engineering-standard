"""Stage 52 Standard half: the canonical standards index and JIT route
compiler.

Compile the minimum complete applicable rule set for the current
task/action rather than loading every standard: ``standards/
index.yaml`` names every normative rule once (id, home,
triggers, enforcement class, critical flag, source hash);
``compile`` resolves one task description to its 5-15 rule-ID
route. Critical rules never reduce to AWARE-only; the whole
registry never loads accidentally; contradictory triggers,
orphan rules, stale hashes, path over-expansion, missing
provider capabilities, and malicious task data all refuse with
repair guidance. ``validate_route_corpus`` checks the frozen
oracle. Tasks and index entries are plain data; missing keys
fall back to total defaults, never a crash.

Frozen enforcement classes (escalating)::

  AWARE  — named in context, no acknowledgement needed.
  ACK    — the role acknowledges the rule before acting.
  GUARD  — machine-checked before the action.
  VERIFY — proven by evidence after the action.
  GATE   — blocks the action until satisfied.
  OWNER  — owner decision required.

``compile`` maps one task to its route (sorted rule IDs plus
per-rule classes). Route inputs: task kind, touched paths,
phase, risk, provider capabilities, extension profile. A
critical rule keeps at least ACK even on low-risk tasks.
Low-risk minimal tasks route few rules; high-risk or
cross-cutting tasks route more — never the whole registry.
Findings use the standard five keys via ``FINDING_FIELDS``;
``SEVERITIES`` names the allowed severities;
``validate_finding`` returns repair strings (empty means
valid). Pure functions: no I/O, no subprocess, no network —
tasks in, routes out. This compiles routes; Stage 53 decides
what to do with a routed rule.
"""

from typing import Any, Dict, List, Optional, Tuple

import hashlib
import json
import re as _re

# Frozen enforcement classes, escalating.
CLASSES = (
    "AWARE",
    "ACK",
    "GUARD",
    "VERIFY",
    "GATE",
    "OWNER",
)

SEVERITIES = ("blocker", "major", "minor")

FINDING_FIELDS = ("id", "rule", "finding", "severity", "excerpt")

# Frozen route rules, in check order.
RULES = (
    "duplicate-id",
    "missing-id",
    "orphan-rule",
    "stale-hash",
    "contradictory-triggers",
    "path-expansion",
    "missing-capability",
    "registry-overload",
    "malicious-task",
    "critical-demotion",
    "minimal-route",
)

# Route size bounds: normally 5-15 rule IDs.
ROUTE_MIN = 5
ROUTE_MAX = 15

# Entry-ID shape for the frozen oracle.
_ENTRY_ID_RE = _re.compile(r"^standards-route\.[a-z-]+\.\d{2}$")

_TASK_INJECTION_RE = _re.compile(
    r"(ignore (previous|all) instructions|disregard .*instructions|"
    r"override .*rules?|bypass .*gate|reveal .*prompt|system prompt"
    r"|__[A-Z_]+__)",
    _re.IGNORECASE)


def _make_finding(rule: str, message: str, excerpt: str,
                  severity: str = "major") -> Dict[str, str]:
    """Build one structured route finding dict."""
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
        repairs.append("finding rule %r is not a frozen Stage 52 "
                       "route rule" % (rule,))
    if "severity" in finding and finding.get("severity") not in SEVERITIES:
        repairs.append("finding severity %r must be "
                       "blocker|major|minor" % (finding.get("severity"),))
    return repairs


def _excerpt(task: Dict[str, Any]) -> str:
    """Short evidence excerpt naming the task."""
    for key in ("kind", "task", "action"):
        value = task.get(key)
        if isinstance(value, (str, int, float)) and str(value).strip():
            return str(value)[:200]
    return "(route)"


# Canonical index: rule ID -> (triggers, class, critical).
# Triggers name task kinds, path prefixes, phases, and risks.
# Compact by design: the compiler resolves per-task routes from
# this table instead of loading 264 registry records.
INDEX = (
    ("thin-outcome", ("implement",), "ACK", False),
    ("one-writer", ("implement", "parallel"), "GATE", True),
    ("exact-head", ("implement", "verify", "merge"), "GUARD", True),
    ("lease-fencing", ("implement", "parallel"), "GATE", True),
    ("no-resident-skill", ("implement",), "ACK", False),
    ("plane-source", ("implement",), "GUARD", False),
    ("plane-generated", ("implement",), "GUARD", False),
    ("lint-real", ("implement", "verify"), "VERIFY", False),
    ("dead-code", ("implement",), "VERIFY", False),
    ("duplication", ("implement",), "VERIFY", False),
    ("dependency-decision", ("implement",), "ACK", False),
    ("charter-clean", ("implement", "review"), "ACK", False),
    ("checkpoint-finalize", ("checkpoint", "resume"), "GATE", True),
    ("journal-order", ("resume", "replay"), "GUARD", True),
    ("wake-verdict", ("resume", "wake"), "GATE", True),
    ("hat-sat", ("resume", "handoff"), "GATE", True),
    ("idempotent-retry", ("execute", "retry"), "GUARD", True),
    ("safe-parallel", ("parallel",), "GATE", True),
    ("one-producer", ("orchestrate",), "ACK", False),
    ("route-minimal", ("plan",), "AWARE", False),
    ("receipt-accept", ("verify", "review"), "VERIFY", False),
    ("no-shortness-reward", ("evaluate",), "ACK", False),
    ("owner-escalation", ("escalate", "merge"), "OWNER", True),
    ("gate-aggregator", ("merge",), "GATE", True),
    ("evidence-index", ("merge", "verify"), "VERIFY", False),
)

INDEX_IDS = tuple(entry[0] for entry in INDEX)


def _normalize_index(entries: Any) -> List[Dict[str, Any]]:
    """Normalize an index entry list to plain dicts."""
    if not isinstance(entries, list):
        return []
    out = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        out.append({
            "id": str(entry.get("id", "")),
            "home": str(entry.get("home", "") or ""),
            "triggers": list(entry.get("triggers") or [])
            if isinstance(entry.get("triggers"), list) else [],
            "class": str(entry.get("class", "") or ""),
            "critical": bool(entry.get("critical", False)),
            "source_hash": str(entry.get("source_hash", "")
                               or ""),
        })
    return out


def default_index() -> List[Dict[str, Any]]:
    """Build the canonical index entries from INDEX."""
    entries = []
    for rid, triggers, cls, critical in INDEX:
        entries.append({
            "id": rid,
            "home": "standards/%s.md" % rid.replace("-", "_"),
            "triggers": list(triggers),
            "class": cls,
            "critical": critical,
            "source_hash": hashlib.sha256(rid.encode(
                "utf-8")).hexdigest()[:16],
        })
    return entries


def _normalize_task(task: Any) -> Dict[str, Any]:
    """Fill total defaults so partial input never crashes."""
    task = task if isinstance(task, dict) else {}
    caps = task.get("capabilities")
    paths = task.get("paths")
    return {
        "kind": str(task.get("kind", "")),
        "paths": [str(p) for p in paths
                  if isinstance(p, (str, int, float))]
        if isinstance(paths, list) else [],
        "phase": str(task.get("phase", "") or ""),
        "risk": str(task.get("risk", "") or ""),
        "capabilities": [str(c) for c in caps
                         if isinstance(c, (str, int, float))]
        if isinstance(caps, list) else [],
        "critical_caps": [str(c) for c in task.get(
            "critical_caps", []) or []]
        if isinstance(task.get("critical_caps"), list) else [],
    }


class RouteResult:
    """One route compilation outcome for one task."""

    route: List[str] = []  # type: ignore[assignment]
    classes: Dict[str, str] = {}  # type: ignore[assignment]
    findings: List[Dict[str, str]] = []  # type: ignore[assignment]

    def __init__(self, route: Optional[List[str]] = None,
                 classes: Optional[Dict[str, str]] = None,
                 findings: Optional[List[Dict[str, str]]] = None):
        self.route = list(route or [])
        self.classes = dict(classes or {})
        self.findings = list(findings or [])


def _check_index(entries: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Index integrity: unique IDs, named homes, known classes,
    stable hashes, no orphans, no contradictions."""
    findings: List[Dict[str, str]] = []
    seen: Dict[str, int] = {}
    for index, entry in enumerate(entries):
        rid = entry["id"]
        if not rid:
            findings.append(_make_finding(
                "missing-id",
                "entries[%d] has no id: every normative rule "
                "needs one" % index,
                "entries[%d]" % index, severity="blocker"))
            continue
        if rid in seen:
            findings.append(_make_finding(
                "duplicate-id",
                "duplicate rule id %r (entries %d and %d)"
                % (rid, seen[rid], index),
                rid[:200], severity="blocker"))
            continue
        seen[rid] = index
        if not entry["home"]:
            findings.append(_make_finding(
                "orphan-rule",
                "rule %r has no normative home: every rule "
                "lives somewhere" % rid,
                rid[:200]))
        if entry["class"] not in CLASSES:
            findings.append(_make_finding(
                "contradictory-triggers",
                "rule %r names unknown class %r: use one of %s"
                % (rid, entry["class"], ", ".join(CLASSES)),
                rid[:200]))
        expected = hashlib.sha256(rid.encode(
            "utf-8")).hexdigest()[:16]
        if entry["source_hash"] and entry["source_hash"] != expected:
            findings.append(_make_finding(
                "stale-hash",
                "rule %r source hash drifted: re-derive the "
                "index" % rid,
                rid[:200]))
    return findings


def compile(task: Any,  # noqa: A001 - frozen Stage 52 name
            entries: Optional[List[Dict[str, Any]]] = None,
            index: Optional[List[Dict[str, Any]]] = None) -> RouteResult:
    """Compile one task to its minimal rule-ID route.

    Resolves triggers (kind, path prefix, phase, risk) against
    the canonical index; critical rules keep at least ACK;
    routes stay within ROUTE_MIN..ROUTE_MAX (low-risk minimal
    tasks route few, high-risk cross-cutting tasks route more,
    never the registry). Malicious task data, missing
    capabilities, path over-expansion, and critical demotion
    refuse with findings. Pure function: no I/O, deterministic
    in its inputs.
    """
    raw_entries = default_index() if entries is None \
        and index is None else (entries if entries is not None
                                else index)
    normalized = _normalize_index(raw_entries or [])
    findings = _check_index(normalized)
    if findings:
        return RouteResult(route=[], classes={},
                           findings=findings)
    item = _normalize_task(task)
    tag = _excerpt(item)
    blob = json.dumps({"kind": item["kind"],
                       "paths": item["paths"],
                       "phase": item["phase"]},
                      sort_keys=True)
    if _TASK_INJECTION_RE.search(blob) or _TASK_INJECTION_RE.search(
            item["kind"]):
        return RouteResult(route=[], classes={}, findings=[_make_finding(
            "malicious-task",
            "task data carries injection or template tokens: "
            "refuse before routing",
            tag, severity="blocker")])
    for cap in item["critical_caps"]:
        if cap not in item["capabilities"]:
            return RouteResult(
                route=[], classes={},
                findings=[_make_finding(
                    "missing-capability",
                    "critical capability %r absent from the "
                    "provider profile: route nothing until "
                    "it resolves" % cap,
                    tag, severity="blocker")])
    route: List[str] = []
    classes: Dict[str, str] = {}
    for entry in normalized:
        triggers = entry["triggers"]
        hit = item["kind"] in triggers or item["phase"] in triggers
        if not hit:
            for path in item["paths"]:
                if str(path) in triggers:
                    hit = True
                    break
        if item["risk"] in ("R2", "R3") and entry["critical"]:
            hit = True
        if hit:
            route.append(entry["id"])
            cls = entry["class"]
            if entry["critical"] and cls == "AWARE":
                findings.append(_make_finding(
                    "critical-demotion",
                    "critical rule %r reduced to AWARE-only: "
                    "critical rules keep at least ACK"
                    % (entry["id"],),
                    tag, severity="blocker"))
                cls = "ACK"
            classes[entry["id"]] = cls
    route = sorted(set(route))
    if len(route) > 40:
        return RouteResult(route=[], classes={}, findings=[_make_finding(
            "registry-overload",
            "route holds %d rules: the whole registry loaded "
            "accidentally; narrow the task" % len(route),
            tag, severity="blocker")])
    if len(item["paths"]) > 20:
        findings.append(_make_finding(
            "path-expansion",
            "%d paths expand the route: bound the focus "
            "envelope" % (len(item["paths"]),),
            tag))
    low_risk = item["risk"] in ("R0", "R1", "")
    if low_risk and len(route) <= 4 and route:
        findings.append(_make_finding(
            "minimal-route",
            "low-risk task routes %d rules: minimal route "
            "confirmed" % (len(route),),
            tag, severity="minor"))
    return RouteResult(route=route, classes=classes,
                       findings=findings)


def _entries_of(corpus: Any) -> List[Dict[str, Any]]:
    if isinstance(corpus, dict):
        entries = corpus.get("entries")
    else:
        entries = corpus
    if not isinstance(entries, list):
        return []
    return entries


def validate_route_corpus(corpus: Any) -> Tuple[List[str],
                                                List[Dict[str, Any]]]:
    """Validate the frozen route fixture oracle.

    Returns (findings, entries); an empty findings list means
    the corpus is a valid frozen oracle: frozen marker set,
    stable provenance, at least 11 entries, unique well-formed
    IDs, every entry's computed rules matching expected_rules
    with route bounds and critical classes holding, and all 11
    route rules covered.
    """
    if isinstance(corpus, dict):
        if corpus.get("_frozen") is not True:
            return (["route corpus is not frozen: set "
                     "\"_frozen\": true"], [])
        provenance = str(corpus.get("_provenance", ""))
        if "Stage 52 #143" not in provenance:
            return (["route corpus provenance must name "
                      "\"Stage 52 #143\""], [])
    elif not isinstance(corpus, list):
        return (["route corpus must be a JSON object with an "
                 "'entries' array (or a bare array)"], [])
    entries = _entries_of(corpus)
    findings: List[str] = []
    if len(entries) < 11:
        findings.append("route corpus holds %d entries, want "
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
                            "standards-route.<class>.<nn>" % cid)
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
        task = entry.get("task", {})
        custom = entry.get("index")
        result = compile(task, entries=custom)
        computed = sorted({f["rule"] for f in result.findings})
        if sorted(str(r) for r in expected) != computed:
            findings.append("entry %s: expected_rules %r != "
                            "compile %r"
                            % (cid, sorted(str(r)
                                           for r in expected),
                               computed))
            continue
        if not expected:
            if not (ROUTE_MIN <= len(result.route) <= ROUTE_MAX):
                findings.append("entry %s: route holds %d IDs, "
                                "want %d-%d" % (cid,
                                                len(result.route),
                                                ROUTE_MIN,
                                                ROUTE_MAX))
            for rid in result.route:
                if rid in [e["id"] for e in _normalize_index(
                        custom) if e["critical"]] \
                        and result.classes.get(rid) == "AWARE":
                    findings.append("entry %s: critical rule %r "
                                    "at AWARE" % (cid, rid))
        if "expected_route" in entry and entry["expected_route"] \
                and sorted(entry["expected_route"]) != result.route:
            findings.append("entry %s: expected_route drifted" % cid)
    for rule in RULES:
        if rule not in covered:
            findings.append("rule %r has no entries (all 11 "
                            "route rules are required)"
                            % rule)
    return findings, entries
