"""Stage 55a Standard half: monotonic deny guards and the trusted base policy.

Lower-trust hooks/models never restore denied authority, and
PR-authored policy never certifies itself. The guard chain
composes admin/trusted -> standard -> repo -> phase/role ->
task -> dynamic layers: later layers may NO_OP or restrict
further, never FORCE_ALLOW something an earlier layer denied.
Denial is monotonic across the chain; owner override is
separate provenance (explicit replacement, never a bypass);
PRs weakening their own policy refuse; base/PR disagreement
refuses; ordinary allowed edits stay low-friction (no full
semantic-guard cost for harmless actions). ``evaluate`` maps
one guard request to ALLOW / DENY / NO_OP;
``validate_guard_corpus`` checks the frozen oracle. Requests
are plain data; missing keys fall back to total defaults, never
a crash.

Frozen layers (evaluation order)::

  admin / trusted / standard / repo / phase-role / task / dynamic

Frozen veredicts: ALLOW, DENY, NO_OP.

Frozen rules, in check order (first hit decides)::

  later-allow        — later layer FORCE_ALLOWs after an
                       earlier DENY: DENY (monotonic deny).
  hook-bug           — lower-trust hook error after a deny:
                       DENY (bugs never restore authority).
  self-weaken        — PR weakens its own policy: DENY (no
                       self-certification).
  base-disagreement  — base branch and PR disagree on policy:
                       DENY until reconciled.
  owner-replacement  — explicit owner replacement with fresh
                       provenance: ALLOW.
  adapter-gap        — provider adapter unable to enforce:
                       NO_OP with escalation (never silent
                       allow).
  protected-path     — protected path without owner approval:
                       DENY.
  ordinary-allow     — harmless allowed edit: ALLOW
                       low-friction (no semantic-guard cost).

Findings use the standard five keys via ``FINDING_FIELDS``;
``SEVERITIES`` names the allowed severities;
``validate_finding`` returns repair strings (empty means
valid). Pure functions: no I/O, no subprocess, no network —
requests in, verdicts out. R3 pilot: canaries gate promotion;
the companion 55b extensions half owns provider adapters.
"""

from typing import Any, Dict, List, Optional, Tuple

import re as _re

# Frozen guard layers, evaluation order.
LAYERS = (
    "admin",
    "trusted",
    "standard",
    "repo",
    "phase-role",
    "task",
    "dynamic",
)

VERDICTS = ("ALLOW", "DENY", "NO_OP")

SEVERITIES = ("blocker", "major", "minor")

FINDING_FIELDS = ("id", "rule", "finding", "severity", "excerpt")

# Frozen guard rules, in check order.
RULES = (
    "later-allow",
    "hook-bug",
    "self-weaken",
    "base-disagreement",
    "owner-replacement",
    "adapter-gap",
    "protected-path",
    "ordinary-allow",
)

# Verdict each rule carries.
RULE_VERDICTS = {
    "later-allow": "DENY",
    "hook-bug": "DENY",
    "self-weaken": "DENY",
    "base-disagreement": "DENY",
    "owner-replacement": "ALLOW",
    "adapter-gap": "NO_OP",
    "protected-path": "DENY",
    "ordinary-allow": "ALLOW",
}

OWNER_LOGIN = "kgsmith19"

# Entry-ID shape for the frozen oracle.
_ENTRY_ID_RE = _re.compile(r"^deny-guards\.[a-z-]+\.\d{2}$")


def _make_finding(rule: str, message: str, excerpt: str,
                  severity: str = "major") -> Dict[str, str]:
    """Build one structured guard finding dict."""
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
        repairs.append("finding rule %r is not a frozen Stage 55a "
                       "guard rule" % (rule,))
    if "severity" in finding and finding.get("severity") not in SEVERITIES:
        repairs.append("finding severity %r must be "
                       "blocker|major|minor" % (finding.get("severity"),))
    return repairs


def _excerpt(request: Dict[str, Any]) -> str:
    """Short evidence excerpt naming the action."""
    for key in ("action", "path", "layer"):
        value = request.get(key)
        if isinstance(value, (str, int, float)) and str(value).strip():
            return str(value)[:200]
    return "(guard)"


def _normalize_request(request: Any) -> Dict[str, Any]:
    """Fill total defaults so partial input never crashes."""
    request = request if isinstance(request, dict) else {}
    layers = request.get("layers")
    norm_layers: Dict[str, str] = {}
    if isinstance(layers, dict):
        for layer in LAYERS:
            value = layers.get(layer)
            norm_layers[layer] = str(value or "NO_OP")
    else:
        for layer in LAYERS:
            norm_layers[layer] = "NO_OP"
    return {
        "action": str(request.get("action", "")),
        "path": str(request.get("path", "") or ""),
        "layers": norm_layers,
        "hook_error": bool(request.get("hook_error", False)),
        "pr_weakens_policy": bool(request.get(
            "pr_weakens_policy", False)),
        "base_policy": str(request.get("base_policy", "") or ""),
        "pr_policy": str(request.get("pr_policy", "") or ""),
        "owner": str(request.get("owner", "") or ""),
        "owner_fresh": bool(request.get("owner_fresh", False)),
        "adapter_enforces": bool(request.get(
            "adapter_enforces", True)),
        "protected": bool(request.get("protected", False)),
        "owner_approved": bool(request.get(
            "owner_approved", False)),
        "harmless": bool(request.get("harmless", False)),
    }


class GuardDecision:
    """One guard outcome for one request."""

    verdict: str = "DENY"
    rule: str = "later-allow"
    findings: List[Dict[str, str]] = []  # type: ignore[assignment]

    def __init__(self, verdict: str = "DENY",
                 rule: str = "later-allow",
                 findings: Optional[List[Dict[str, str]]] = None):
        self.verdict = verdict
        self.rule = rule
        self.findings = list(findings or [])


def _decide(rule: str, message: str, tag: str,
            severity: str = "major") -> GuardDecision:
    return GuardDecision(
        verdict=RULE_VERDICTS[rule], rule=rule,
        findings=[_make_finding(rule, message, tag,
                                severity=severity)])


def evaluate(request: Any) -> GuardDecision:
    """Map one guard request to ALLOW / DENY / NO_OP.

    Walks layers in order: the first DENY sticks (later layers
    may only NO_OP or restrict, never FORCE_ALLOW). Hook errors
    after denial, self-weakening PRs, base/PR disagreement,
    unapproved protected paths all deny. Explicit owner
    replacement with fresh provenance allows; adapter gaps
    NO_OP with escalation; harmless edits allow low-friction.
    Pure function: no I/O, deterministic in its input. This
    guards; it never authorizes outside chain order.
    """
    item = _normalize_request(request)
    tag = _excerpt(item)
    denied_at: Optional[str] = None
    for layer in LAYERS:
        verdict = item["layers"].get(layer, "NO_OP")
        if verdict == "DENY" and denied_at is None:
            denied_at = layer
        if verdict == "ALLOW" and denied_at is not None:
            return _decide(
                "later-allow",
                "layer %r FORCE_ALLOWs after layer %r denied: "
                "DENY (denial is monotonic)" % (layer,
                                                denied_at),
                tag, severity="blocker")
    if item["hook_error"] and denied_at is not None:
        return _decide(
            "hook-bug",
            "lower-trust hook error after layer %r denied: "
            "DENY (bugs never restore authority)" % denied_at,
            tag, severity="blocker")
    if item["pr_weakens_policy"]:
        return _decide(
            "self-weaken",
            "PR weakens its own policy: DENY (policy never "
            "self-certifies)",
            tag, severity="blocker")
    if item["base_policy"] and item["pr_policy"] \
            and item["base_policy"] != item["pr_policy"]:
        return _decide(
            "base-disagreement",
            "base and PR disagree on policy: DENY until "
            "reconciled",
            tag, severity="blocker")
    if item["owner"] == OWNER_LOGIN and item["owner_fresh"]:
        return _decide(
            "owner-replacement",
            "explicit owner replacement with fresh provenance: "
            "ALLOW",
            tag, severity="minor")
    if not item["adapter_enforces"]:
        return _decide(
            "adapter-gap",
            "provider adapter unable to enforce: NO_OP with "
            "escalation (never silent allow)",
            tag)
    if item["protected"] and not item["owner_approved"]:
        return _decide(
            "protected-path",
            "protected path %r without owner approval: DENY"
            % item["path"],
            tag, severity="blocker")
    if denied_at is not None:
        return _decide(
            "later-allow",
            "layer %r denied: DENY holds across the chain"
            % denied_at,
            tag, severity="blocker")
    return _decide(
        "ordinary-allow",
        "harmless allowed edit: ALLOW low-friction (no "
        "semantic-guard cost)",
        tag, severity="minor")


def clean_request() -> Dict[str, Any]:
    """One clean guard request (ALLOW).

    Harmless edit, no denials, adapter enforces. Callers mutate
    one dimension per test.
    """
    layers = {layer: "NO_OP" for layer in LAYERS}
    return {
        "action": "edit-tools",
        "path": "tools/demo.py",
        "layers": layers,
        "hook_error": False,
        "pr_weakens_policy": False,
        "base_policy": "",
        "pr_policy": "",
        "owner": "",
        "owner_fresh": False,
        "adapter_enforces": True,
        "protected": False,
        "owner_approved": False,
        "harmless": True,
    }


def _entries_of(corpus: Any) -> List[Dict[str, Any]]:
    if isinstance(corpus, dict):
        entries = corpus.get("entries")
    else:
        entries = corpus
    if not isinstance(entries, list):
        return []
    return entries


def validate_guard_corpus(corpus: Any) -> Tuple[List[str],
                                                List[Dict[str, Any]]]:
    """Validate the frozen guard fixture oracle.

    Returns (findings, entries); an empty findings list means
    the corpus is a valid frozen oracle: frozen marker set,
    stable provenance, at least 8 entries, unique well-formed
    IDs, every entry computing its expected rule and verdict,
    and all 8 guard rules covered.
    """
    if isinstance(corpus, dict):
        if corpus.get("_frozen") is not True:
            return (["guard corpus is not frozen: set "
                     "\"_frozen\": true"], [])
        provenance = str(corpus.get("_provenance", ""))
        if "Stage 55a #146" not in provenance:
            return (["guard corpus provenance must name "
                      "\"Stage 55a #146\""], [])
    elif not isinstance(corpus, list):
        return (["guard corpus must be a JSON object with an "
                 "'entries' array (or a bare array)"], [])
    entries = _entries_of(corpus)
    findings: List[str] = []
    if len(entries) < 8:
        findings.append("guard corpus holds %d entries, want "
                        "at least 8" % len(entries))
    seen: Dict[str, int] = {}
    covered = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            findings.append("entries[%d] is not a mapping" % index)
            continue
        cid = str(entry.get("id", ""))
        if not _ENTRY_ID_RE.match(cid):
            findings.append("entry %r: id is not "
                            "deny-guards.<class>.<nn>" % cid)
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
                            "frozen Stage 55a guard rule"
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
        result = evaluate(entry.get("request", {}))
        if result.rule != rule:
            findings.append("entry %s: expected_rule %r != "
                            "evaluate %r"
                            % (cid, rule, result.rule))
        if result.verdict != entry.get("expected_verdict"):
            findings.append("entry %s: expected_verdict %r != "
                            "evaluate %r" % (cid, entry.get(
                                "expected_verdict"),
                                result.verdict))
    for rule in RULES:
        if rule not in covered:
            findings.append("rule %r has no entries (all 8 "
                            "guard rules are required)"
                            % rule)
    return findings, entries
