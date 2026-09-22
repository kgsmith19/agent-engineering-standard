"""Stage 60a Standard half: exact-head evidence, control plane, and PR Gate
hardening.

Every claim, lane, review, standards result, and merge action
binds to the exact current head under the expected
control-plane contract — versioned for simple and monorepo
profiles. Worker lanes stay read-only/least-privilege/full-SHA;
required workflows always report; the current PR head equals
the tested head; privileged jobs execute no PR-controlled code
or artifact; expected-OID auto-merge arms only on the exact
head; owner holds and bypasses follow explicit provenance.
``evaluate`` maps one control-plane observation to ARM / HOLD /
REFUSE; ``validate_control_corpus`` checks the frozen oracle.
Observations are plain data; missing keys fall back to total
defaults, never a crash.

Frozen verdicts: ARM, HOLD, REFUSE.

Frozen profiles: simple, monorepo.

Frozen rules, in check order (first hit decides)::

  missing-lane       — required lane missing: REFUSE.
  duplicate-lane     — duplicate lane report: REFUSE.
  skipped-lane       — lane skipped: REFUSE.
  neutral-lane       — lane concluded neutral: REFUSE (lanes
                       report success/failure, never neutral).
  cancelled-lane     — lane cancelled: REFUSE and rerun.
  stale-lane         — tested SHA != current head: REFUSE and
                       re-verify.
  path-filter        — path filter hides the lane: REFUSE.
  unsafe-target      — unsafe pull_request_target with PR code:
                       REFUSE.
  floating-pin       — floating action pin: REFUSE and pin
                       full-SHA.
  excess-permission  — worker lane above least privilege:
                       REFUSE.
  head-moved         — head moved since arming: REFUSE and
                       re-arm.
  missing-evidence   — screenshot/digest evidence missing:
                       REFUSE.
  policy-fail        — standards-policy failure: REFUSE.
  merge-conflict     — merge conflict present: HOLD.
  draft-hold         — unauthorized draft or owner hold: HOLD.
  rearm              — auto-merge needs re-arm on the exact
                       head: HOLD with re-arm.
  clean-arm          — all lanes green at the exact head with
                       expected OIDs: ARM.

Findings use the standard five keys via ``FINDING_FIELDS``;
``SEVERITIES`` names the allowed severities;
``validate_finding`` returns repair strings (empty means
valid). Pure functions: no I/O, no subprocess, no network —
observations in, verdicts out. One final aggregator only;
hyperbolic-core's stable check name never renames; its
control-plane slice follows as Stage 60b.
"""

from typing import Any, Dict, List, Optional, Tuple

import re as _re

# Frozen control verdicts.
VERDICTS = (
    "ARM",
    "HOLD",
    "REFUSE",
)

# Frozen control profiles.
PROFILES = (
    "simple",
    "monorepo",
)

SEVERITIES = ("blocker", "major", "minor")

FINDING_FIELDS = ("id", "rule", "finding", "severity", "excerpt")

# Frozen control rules, in check order.
RULES = (
    "missing-lane",
    "duplicate-lane",
    "skipped-lane",
    "neutral-lane",
    "cancelled-lane",
    "stale-lane",
    "path-filter",
    "unsafe-target",
    "floating-pin",
    "excess-permission",
    "head-moved",
    "missing-evidence",
    "policy-fail",
    "merge-conflict",
    "draft-hold",
    "rearm",
    "clean-arm",
)

# Verdict each rule carries.
RULE_VERDICTS = {
    "missing-lane": "REFUSE",
    "duplicate-lane": "REFUSE",
    "skipped-lane": "REFUSE",
    "neutral-lane": "REFUSE",
    "cancelled-lane": "REFUSE",
    "stale-lane": "REFUSE",
    "path-filter": "REFUSE",
    "unsafe-target": "REFUSE",
    "floating-pin": "REFUSE",
    "excess-permission": "REFUSE",
    "head-moved": "REFUSE",
    "missing-evidence": "REFUSE",
    "policy-fail": "REFUSE",
    "merge-conflict": "HOLD",
    "draft-hold": "HOLD",
    "rearm": "HOLD",
    "clean-arm": "ARM",
}

# Entry-ID shape for the frozen oracle.
_ENTRY_ID_RE = _re.compile(r"^control-plane\.[a-z-]+\.\d{2}$")


def _make_finding(rule: str, message: str, excerpt: str,
                  severity: str = "major") -> Dict[str, str]:
    """Build one structured control finding dict."""
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
        repairs.append("finding rule %r is not a frozen Stage 60a "
                       "control rule" % (rule,))
    if "severity" in finding and finding.get("severity") not in SEVERITIES:
        repairs.append("finding severity %r must be "
                       "blocker|major|minor" % (finding.get("severity"),))
    return repairs


def _excerpt(observation: Dict[str, Any]) -> str:
    """Short evidence excerpt naming the PR."""
    for key in ("pr", "head", "profile"):
        value = observation.get(key)
        if isinstance(value, (str, int, float)) and str(value).strip():
            return str(value)[:200]
    return "(control)"


def _normalize_observation(observation: Any) -> Dict[str, Any]:
    """Fill total defaults so partial input never crashes."""
    observation = observation if isinstance(observation, dict) else {}
    lanes = observation.get("lanes")
    return {
        "pr": str(observation.get("pr", "")),
        "profile": str(observation.get("profile", "") or ""),
        "lanes": [str(l) for l in lanes
                  if isinstance(l, (str, int, float))]
        if isinstance(lanes, list) else [],
        "required": [str(l) for l in observation.get(
            "required", []) or []]
        if isinstance(observation.get("required"), list) else [],
        "conclusions": dict(observation.get("conclusions", {}))
        if isinstance(observation.get("conclusions"), dict)
        else {},
        "tested_head": str(observation.get(
            "tested_head", "") or ""),
        "live_head": str(observation.get("live_head", "") or ""),
        "path_filtered": bool(observation.get(
            "path_filtered", False)),
        "pr_target_unsafe": bool(observation.get(
            "pr_target_unsafe", False)),
        "pins_floating": bool(observation.get(
            "pins_floating", False)),
        "excess_permission": bool(observation.get(
            "excess_permission", False)),
        "evidence_complete": bool(observation.get(
            "evidence_complete", True)),
        "policy_ok": bool(observation.get("policy_ok", True)),
        "conflicted": bool(observation.get("conflicted", False)),
        "draft": bool(observation.get("draft", False)),
        "draft_allowed": bool(observation.get(
            "draft_allowed", False)),
        "owner_hold": bool(observation.get("owner_hold", False)),
        "needs_rearm": bool(observation.get(
            "needs_rearm", False)),
        "expected_oid": str(observation.get(
            "expected_oid", "") or ""),
        "armed_oid": str(observation.get("armed_oid", "") or ""),
    }


class ControlDecision:
    """One control-plane outcome for one observation."""

    verdict: str = "REFUSE"
    rule: str = "missing-lane"
    findings: List[Dict[str, str]] = []  # type: ignore[assignment]

    def __init__(self, verdict: str = "REFUSE",
                 rule: str = "missing-lane",
                 findings: Optional[List[Dict[str, str]]] = None):
        self.verdict = verdict
        self.rule = rule
        self.findings = list(findings or [])


def _decide(rule: str, message: str, tag: str,
            severity: str = "major") -> ControlDecision:
    return ControlDecision(
        verdict=RULE_VERDICTS[rule], rule=rule,
        findings=[_make_finding(rule, message, tag,
                                severity=severity)])


def evaluate(observation: Any) -> ControlDecision:
    """Map one control-plane observation to ARM / HOLD / REFUSE.

    Lane presence, uniqueness, reporting, conclusions, head
    equality, filters, target safety, pins, permissions,
    evidence, policy, conflicts, drafts/holds, and re-arm state
    gate in order; a fully green exact-head observation with
    expected OIDs arms. Pure function: no I/O, deterministic in
    its input. This decides; the aggregator enforces.
    """
    item = _normalize_observation(observation)
    tag = _excerpt(item)
    for required in item["required"]:
        if required not in item["lanes"]:
            return _decide(
                "missing-lane",
                "required lane %r missing: REFUSE" % (required,),
                tag, severity="blocker")
    if len(set(item["lanes"])) != len(item["lanes"]):
        return _decide(
            "duplicate-lane",
            "duplicate lane report: REFUSE",
            tag, severity="blocker")
    for lane in item["lanes"]:
        conclusion = str(item["conclusions"].get(lane, "success")
                         or "success")
        if conclusion == "skipped":
            return _decide(
                "skipped-lane",
                "lane %r skipped: REFUSE" % (lane,),
                tag, severity="blocker")
        if conclusion == "neutral":
            return _decide(
                "neutral-lane",
                "lane %r concluded neutral: REFUSE (lanes "
                "report success/failure)" % (lane,),
                tag, severity="blocker")
        if conclusion == "cancelled":
            return _decide(
                "cancelled-lane",
                "lane %r cancelled: REFUSE and rerun" % (lane,),
                tag)
    if item["tested_head"] and item["live_head"] \
            and item["tested_head"] != item["live_head"]:
        return _decide(
            "stale-lane",
            "tested SHA != current head: REFUSE and re-verify",
            tag, severity="blocker")
    if item["path_filtered"]:
        return _decide(
            "path-filter",
            "path filter hides a lane: REFUSE",
            tag, severity="blocker")
    if item["pr_target_unsafe"]:
        return _decide(
            "unsafe-target",
            "unsafe pull_request_target with PR code: REFUSE",
            tag, severity="blocker")
    if item["pins_floating"]:
        return _decide(
            "floating-pin",
            "floating action pin: REFUSE and pin full-SHA",
            tag, severity="blocker")
    if item["excess_permission"]:
        return _decide(
            "excess-permission",
            "worker lane above least privilege: REFUSE",
            tag, severity="blocker")
    if item["evidence_complete"] is False:
        return _decide(
            "missing-evidence",
            "screenshot/digest evidence missing: REFUSE",
            tag)
    if not item["policy_ok"]:
        return _decide(
            "policy-fail",
            "standards-policy failure: REFUSE",
            tag, severity="blocker")
    for lane in item["lanes"]:
        conclusion = str(item["conclusions"].get(lane, "success")
                         or "success")
        if conclusion not in ("success", "skipped", "neutral",
                              "cancelled"):
            return _decide(
                "policy-fail",
                "lane %r concluded %r: REFUSE" % (lane,
                                                  conclusion),
                tag, severity="blocker")
    if item["conflicted"]:
        return _decide(
            "merge-conflict",
            "merge conflict present: HOLD",
            tag)
    if (item["draft"] and not item["draft_allowed"]) \
            or item["owner_hold"]:
        return _decide(
            "draft-hold",
            "unauthorized draft or owner hold: HOLD",
            tag)
    if item["needs_rearm"]:
        return _decide(
            "rearm",
            "auto-merge needs re-arm on the exact head: HOLD "
            "with re-arm",
            tag)
    if item["expected_oid"] and item["armed_oid"] \
            and item["expected_oid"] != item["armed_oid"]:
        return _decide(
            "head-moved",
            "armed OID != expected OID: REFUSE and re-arm",
            tag, severity="blocker")
    if not item["lanes"]:
        return _decide(
            "missing-lane",
            "no lanes reported: REFUSE",
            tag, severity="blocker")
    return ControlDecision(
        verdict="ARM", rule="clean-arm",
        findings=[_make_finding(
            "clean-arm",
            "all lanes green at the exact head with expected "
            "OIDs: ARM",
            tag, severity="minor")])


def clean_observation() -> Dict[str, Any]:
    """One clean control observation (ARM).

    Required lanes green at the exact head, full-SHA pins,
    least privilege, evidence complete, no conflicts/holds.
    Callers mutate one dimension per test.
    """
    head = "a" * 40
    lanes = ["policy", "tests", "gate-compliance"]
    return {
        "pr": "PR-1",
        "profile": "simple",
        "lanes": list(lanes),
        "required": list(lanes),
        "conclusions": {lane: "success" for lane in lanes},
        "tested_head": head,
        "live_head": head,
        "path_filtered": False,
        "pr_target_unsafe": False,
        "pins_floating": False,
        "excess_permission": False,
        "evidence_complete": True,
        "policy_ok": True,
        "conflicted": False,
        "draft": False,
        "draft_allowed": False,
        "owner_hold": False,
        "needs_rearm": False,
        "expected_oid": head,
        "armed_oid": head,
    }


def _entries_of(corpus: Any) -> List[Dict[str, Any]]:
    if isinstance(corpus, dict):
        entries = corpus.get("entries")
    else:
        entries = corpus
    if not isinstance(entries, list):
        return []
    return entries


def validate_control_corpus(corpus: Any) -> Tuple[List[str],
                                                  List[Dict[str, Any]]]:
    """Validate the frozen control fixture oracle.

    Returns (findings, entries); an empty findings list means
    the corpus is a valid frozen oracle: frozen marker set,
    stable provenance, at least 17 entries, unique well-formed
    IDs, every entry computing its expected rule and verdict,
    and all 17 control rules covered.
    """
    if isinstance(corpus, dict):
        if corpus.get("_frozen") is not True:
            return (["control corpus is not frozen: set "
                     "\"_frozen\": true"], [])
        provenance = str(corpus.get("_provenance", ""))
        if "Stage 60a #151" not in provenance:
            return (["control corpus provenance must name "
                      "\"Stage 60a #151\""], [])
    elif not isinstance(corpus, list):
        return (["control corpus must be a JSON object with an "
                 "'entries' array (or a bare array)"], [])
    entries = _entries_of(corpus)
    findings: List[str] = []
    if len(entries) < 17:
        findings.append("control corpus holds %d entries, want "
                        "at least 17" % len(entries))
    seen: Dict[str, int] = {}
    covered = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            findings.append("entries[%d] is not a mapping" % index)
            continue
        cid = str(entry.get("id", ""))
        if not _ENTRY_ID_RE.match(cid):
            findings.append("entry %r: id is not "
                            "control-plane.<class>.<nn>" % cid)
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
                            "frozen Stage 60a control rule"
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
        result = evaluate(entry.get("observation", {}))
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
            findings.append("rule %r has no entries (all 17 "
                            "control rules are required)"
                            % rule)
    return findings, entries
