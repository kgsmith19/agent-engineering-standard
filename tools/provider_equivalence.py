"""Stage 56a Standard half: cross-provider instruction and policy equivalence.

Claude, Codex, Gemini/Antigravity, and local/headless agents
receive equivalent canonical authority and fail safely when
features differ. The equivalence contract normalizes
provider-specific config to canonical rule IDs and
permissions, then proves the five-level precedence order:
owner/direct instruction > normative policy > verified capsule
> task data > untrusted content. A missing provider feature
lowers autonomy or substitutes an equivalent wrapper — never
silent full parity. ``normalize`` maps one provider report to
canonical form; ``precedence`` resolves one conflict to the
winning level; ``validate_equivalence_corpus`` checks the
frozen oracle. Reports are plain data; missing keys fall back
to total defaults, never a crash.

Frozen providers: claude, codex, gemini, local.

Frozen precedence (highest first)::

  owner-direct / normative-policy / verified-capsule /
  task-data / untrusted-content

Frozen rules, in check order (first hit decides)::

  nested-conflict    — nested instruction conflict resolves to
                       the higher precedence level.
  agents-override    — AGENTS.md override wins over task data.
  comment-injection  — malicious comment content loses to every
                       higher level.
  filename-injection — malicious filename loses to every
                       higher level.
  tool-injection     — malicious tool output loses to every
                       higher level.
  version-drift      — provider version drift records
                       degraded parity, never silent parity.
  child-inheritance  — child/subagent inherits the parent
                       route minus escalation rights.
  missing-hook       — missing PreTool hook lowers autonomy
                       with an equivalent manual wrapper.
  manual-equivalent  — local-model manual equivalent recorded
                       explicitly.
  hash-parity        — normalized rule/capability hashes match
                       across providers.

Findings use the standard five keys via ``FINDING_FIELDS``;
``SEVERITIES`` names the allowed severities;
``validate_finding`` returns repair strings (empty means
valid). Pure functions: no I/O, no subprocess, no network —
reports in, canonical forms out. This defines and canaries the
contract; the 56b extensions half builds the adapters.
"""

from typing import Any, Dict, List, Optional, Tuple

import hashlib
import json
import re as _re

# Frozen providers.
PROVIDERS = (
    "claude",
    "codex",
    "gemini",
    "local",
)

# Frozen precedence, highest first.
PRECEDENCE = (
    "owner-direct",
    "normative-policy",
    "verified-capsule",
    "task-data",
    "untrusted-content",
)

SEVERITIES = ("blocker", "major", "minor")

FINDING_FIELDS = ("id", "rule", "finding", "severity", "excerpt")

# Frozen equivalence rules, in check order.
RULES = (
    "nested-conflict",
    "agents-override",
    "comment-injection",
    "filename-injection",
    "tool-injection",
    "version-drift",
    "child-inheritance",
    "missing-hook",
    "manual-equivalent",
    "hash-parity",
)

# Verdict each rule carries (the winning precedence level or
# the parity outcome).
RULE_OUTCOMES = {
    "nested-conflict": "higher-wins",
    "agents-override": "normative-policy",
    "comment-injection": "higher-wins",
    "filename-injection": "higher-wins",
    "tool-injection": "higher-wins",
    "version-drift": "degraded",
    "child-inheritance": "inherited-minus-escalation",
    "missing-hook": "lowered-autonomy",
    "manual-equivalent": "recorded",
    "hash-parity": "matched",
}

_INJECTION_RE = _re.compile(
    r"(ignore (previous|all) instructions|disregard .*instructions|"
    r"override .*rules?|bypass .*gate|reveal .*prompt)",
    _re.IGNORECASE)

# Entry-ID shape for the frozen oracle.
_ENTRY_ID_RE = _re.compile(r"^provider-equivalence\.[a-z-]+\.\d{2}$")


def _make_finding(rule: str, message: str, excerpt: str,
                  severity: str = "major") -> Dict[str, str]:
    """Build one structured equivalence finding dict."""
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
        repairs.append("finding rule %r is not a frozen Stage 56a "
                       "equivalence rule" % (rule,))
    if "severity" in finding and finding.get("severity") not in SEVERITIES:
        repairs.append("finding severity %r must be "
                       "blocker|major|minor" % (finding.get("severity"),))
    return repairs


def _excerpt(report: Dict[str, Any]) -> str:
    """Short evidence excerpt naming the provider/case."""
    for key in ("provider", "case", "conflict"):
        value = report.get(key)
        if isinstance(value, (str, int, float)) and str(value).strip():
            return str(value)[:200]
    return "(equivalence)"


def _level_rank(level: str) -> int:
    try:
        return PRECEDENCE.index(level)
    except ValueError:
        return len(PRECEDENCE)


def normalize(report: Any) -> Dict[str, Any]:
    """Map one provider report to canonical form.

    Returns {"provider", "rules", "capabilities", "parity",
    "digest"}: normalized rule IDs and capability names plus a
    sha256 digest over the sorted pair. Unsupported capabilities
    record degraded parity explicitly, never silent parity.
    Pure function: no I/O, deterministic in its input.
    """
    report = report if isinstance(report, dict) else {}
    provider = str(report.get("provider", "") or "")
    rules = sorted(str(r) for r in report.get("rules", [])
                   if isinstance(r, (str, int, float)))
    capabilities = sorted(str(c) for c in report.get(
        "capabilities", []) if isinstance(c, (str, int, float)))
    unsupported = sorted(str(u) for u in report.get(
        "unsupported", []) if isinstance(u, (str, int, float)))
    canonical = json.dumps(
        {"rules": rules, "capabilities": capabilities},
        sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode(
        "utf-8")).hexdigest()[:16]
    parity = "full" if not unsupported else "degraded"
    return {"provider": provider, "rules": rules,
            "capabilities": capabilities,
            "unsupported": unsupported, "parity": parity,
            "digest": digest}


def precedence(outer: str, inner: str) -> str:
    """Resolve one nested conflict to the winning level.

    The higher precedence level (lower index) wins; ties hold
    the outer level. Unknown levels lose to any known level.
    """
    if _level_rank(outer) <= _level_rank(inner):
        return outer
    return inner


class EquivalenceDecision:
    """One equivalence outcome for one case."""

    outcome: str = "higher-wins"
    rule: str = "nested-conflict"
    findings: List[Dict[str, str]] = []  # type: ignore[assignment]

    def __init__(self, outcome: str = "higher-wins",
                 rule: str = "nested-conflict",
                 findings: Optional[List[Dict[str, str]]] = None):
        self.outcome = outcome
        self.rule = rule
        self.findings = list(findings or [])


def _decide(rule: str, message: str, tag: str,
            severity: str = "major") -> EquivalenceDecision:
    return EquivalenceDecision(
        outcome=RULE_OUTCOMES[rule], rule=rule,
        findings=[_make_finding(rule, message, tag,
                                severity=severity)])


def decide(case: Any) -> EquivalenceDecision:
    """Map one equivalence case to its outcome.

    Nested conflicts resolve by precedence; AGENTS overrides
    beat task data; comment/filename/tool injections lose;
    version drift degrades; children inherit minus escalation;
    missing hooks lower autonomy; manual equivalents record;
    matching digests prove hash parity. Pure function: no I/O,
    deterministic in its input. This proves equivalence; it
    never builds adapters.
    """
    case = case if isinstance(case, dict) else {}
    kind = str(case.get("kind", ""))
    tag = _excerpt(case)
    if kind == "nested":
        winner = precedence(str(case.get("outer", "")),
                            str(case.get("inner", "")))
        return EquivalenceDecision(
            outcome="higher-wins", rule="nested-conflict",
            findings=[_make_finding(
                "nested-conflict",
                "nested conflict resolves to %r (higher "
                "precedence wins)" % winner,
                tag, severity="minor")])
    if kind == "override":
        return _decide(
            "agents-override",
            "AGENTS.md override wins over task data: "
            "normative-policy outranks task-data",
            tag, severity="minor")
    if kind == "comment":
        text = str(case.get("text", ""))
        if _INJECTION_RE.search(text):
            return _decide(
                "comment-injection",
                "malicious comment loses to every higher level: "
                "untrusted-content never wins",
                tag, severity="blocker")
        return _decide(
            "comment-injection",
            "benign comment carries no override: higher levels "
            "hold",
            tag, severity="minor")
    if kind == "filename":
        text = str(case.get("text", ""))
        if _INJECTION_RE.search(text) or ".." in text:
            return _decide(
                "filename-injection",
                "malicious filename loses to every higher "
                "level: untrusted-content never wins",
                tag, severity="blocker")
        return _decide(
            "filename-injection",
            "benign filename carries no override: higher "
            "levels hold",
            tag, severity="minor")
    if kind == "tool-output":
        text = str(case.get("text", ""))
        if _INJECTION_RE.search(text):
            return _decide(
                "tool-injection",
                "malicious tool output loses to every higher "
                "level: untrusted-content never wins",
                tag, severity="blocker")
        return _decide(
            "tool-injection",
            "benign tool output carries no override: higher "
            "levels hold",
            tag, severity="minor")
    if kind == "drift":
        return _decide(
            "version-drift",
            "provider version %r drifted: degraded parity "
            "recorded, never silent parity"
            % str(case.get("version", "")),
            tag)
    if kind == "child":
        return _decide(
            "child-inheritance",
            "child inherits the parent route minus escalation "
            "rights",
            tag, severity="minor")
    if kind == "hook":
        if not case.get("hook_present", False):
            return _decide(
                "missing-hook",
                "missing PreTool hook: autonomy lowered with "
                "an equivalent manual wrapper",
                tag)
        return _decide(
            "missing-hook",
            "hook present: parity holds",
            tag, severity="minor")
    if kind == "manual":
        return _decide(
            "manual-equivalent",
            "local-model manual equivalent recorded "
            "explicitly: %r"
            % str(case.get("equivalent", "")),
            tag, severity="minor")
    if kind == "parity":
        reports = case.get("reports", [])
        digests = set()
        if isinstance(reports, list):
            for report in reports:
                digests.add(normalize(report)["digest"])
        if len(digests) == 1 and digests != {""}:
            return _decide(
                "hash-parity",
                "normalized rule/capability hashes match across "
                "providers",
                tag, severity="minor")
        return EquivalenceDecision(
            outcome="degraded", rule="hash-parity",
            findings=[_make_finding(
                "hash-parity",
                "normalized hashes diverge: degraded parity "
                "recorded",
                tag)])
    return EquivalenceDecision(
        outcome="higher-wins", rule="nested-conflict",
        findings=[_make_finding(
            "nested-conflict",
            "unknown case kind %r: precedence decides" % (kind,),
            tag, severity="minor")])


def clean_case() -> Dict[str, Any]:
    """One clean equivalence case (precedence holds).

    A nested owner-vs-task conflict resolving owner-direct.
    Callers mutate one dimension per test.
    """
    return {
        "kind": "nested",
        "provider": "claude",
        "outer": "owner-direct",
        "inner": "task-data",
        "text": "",
        "version": "",
        "hook_present": True,
        "equivalent": "",
        "reports": [],
    }


def _entries_of(corpus: Any) -> List[Dict[str, Any]]:
    if isinstance(corpus, dict):
        entries = corpus.get("entries")
    else:
        entries = corpus
    if not isinstance(entries, list):
        return []
    return entries


def validate_equivalence_corpus(corpus: Any) -> Tuple[List[str],
                                                      List[Dict[str, Any]]]:
    """Validate the frozen equivalence fixture oracle.

    Returns (findings, entries); an empty findings list means
    the corpus is a valid frozen oracle: frozen marker set,
    stable provenance, at least 10 entries, unique well-formed
    IDs, every entry computing its expected rule and outcome,
    and all 10 equivalence rules covered.
    """
    if isinstance(corpus, dict):
        if corpus.get("_frozen") is not True:
            return (["equivalence corpus is not frozen: set "
                     "\"_frozen\": true"], [])
        provenance = str(corpus.get("_provenance", ""))
        if "Stage 56a #147" not in provenance:
            return (["equivalence corpus provenance must name "
                      "\"Stage 56a #147\""], [])
    elif not isinstance(corpus, list):
        return (["equivalence corpus must be a JSON object with an "
                 "'entries' array (or a bare array)"], [])
    entries = _entries_of(corpus)
    findings: List[str] = []
    if len(entries) < 10:
        findings.append("equivalence corpus holds %d entries, want "
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
                            "provider-equivalence.<class>.<nn>"
                            % cid)
        if cid in seen:
            findings.append("duplicate entry id %s (entries %d "
                            "and %d)" % (cid, seen[cid], index))
        else:
            seen[cid] = index
        if not str(entry.get("note", "")).strip():
            findings.append("entry %s: a one-line adjudication note "
                            "is required" % cid)
        for key in ("expected_rule", "expected_outcome"):
            if key not in entry:
                findings.append("entry %s: %s is required"
                                % (cid, key))
        rule = entry.get("expected_rule")
        if rule not in RULES:
            findings.append("entry %s: expected_rule %r is not a "
                            "frozen Stage 56a equivalence rule"
                            % (cid, rule))
            continue
        covered.add(str(rule))
        if entry.get("expected_outcome") != RULE_OUTCOMES.get(
                str(rule)):
            findings.append("entry %s: expected_outcome %r != "
                            "rule outcome %r" % (cid, entry.get(
                                "expected_outcome"),
                                RULE_OUTCOMES.get(str(rule))))
            continue
        result = decide(entry.get("case", {}))
        if result.rule != rule:
            findings.append("entry %s: expected_rule %r != "
                            "decide %r" % (cid, rule, result.rule))
        if result.outcome != entry.get("expected_outcome"):
            findings.append("entry %s: expected_outcome %r != "
                            "decide %r" % (cid, entry.get(
                                "expected_outcome"),
                                result.outcome))
    for rule in RULES:
        if rule not in covered:
            findings.append("rule %r has no entries (all 10 "
                            "equivalence rules are required)"
                            % rule)
    return findings, entries
