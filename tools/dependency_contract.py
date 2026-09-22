"""Stage 39 Standard half: the dependency and library decision contract.

Prefer proven libraries or native platform capability only when
they reduce total owned complexity and risk. ``decide`` maps one
dependency proposal to its verdict (adopt-local, adopt-library,
or reject with repair guidance); ``validate_dependency_corpus``
checks the frozen oracle. Proposal fields are plain data;
missing keys fall back to total defaults, never a crash.

Frozen decision rules, in check order (first hit decides the
rejection reason; a fully clean library proposal is ADOPT)::

  license-conflict   — license incompatible with the repo
  supply-chain-alert — known abandonment or active alert
  duplicates-platform— platform already owns the capability
  heavy-for-value    — popular-but-heavy cost exceeds benefit
  local-cheaper      — a tiny secure local helper wins

A proposal that deletes owned complexity, carries a clean
license, and passes every rule is ADOPT-LIBRARY; a proposal
where the local helper wins is ADOPT-LOCAL; anything else is
REJECT with exactly its rule. Rollback information (pin +
revert plan) is required on every ADOPT verdict. Findings are
repair guidance (rule + message + excerpt), never an error:
``FINDING_FIELDS`` names the five required keys,
``SEVERITIES`` names the allowed severities, and
``validate_finding`` returns repair strings (empty means
valid). Pure functions: no I/O, no subprocess, no network —
proposals in, verdicts out. Advisory baseline only: no
blocking threshold in this stage.
"""

from typing import Any, Dict, List, Optional, Tuple

import re as _re

# Frozen decision rules, in check order.
RULES = (
    "license-conflict",
    "supply-chain-alert",
    "duplicates-platform",
    "heavy-for-value",
    "local-cheaper",
)

VERDICTS = ("ADOPT-LIBRARY", "ADOPT-LOCAL", "REJECT")

SEVERITIES = ("blocker", "major", "minor")

FINDING_FIELDS = ("id", "rule", "finding", "severity", "excerpt")

COMPATIBLE_LICENSES = ("MIT", "Apache-2.0", "BSD-3-Clause",
                       "BSD-2-Clause", "ISC", "PSF-2.0")

# Entry-ID shape for the frozen oracle.
_ENTRY_ID_RE = _re.compile(r"^dependency-contract\.[a-z-]+\.\d{2}$")


def _make_finding(rule: str, message: str, excerpt: str,
                  severity: str = "major") -> Dict[str, str]:
    """Build one structured dependency finding dict."""
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
        repairs.append("finding rule %r is not a frozen Stage 39 "
                       "dependency rule" % (rule,))
    if "severity" in finding and finding.get("severity") not in SEVERITIES:
        repairs.append("finding severity %r must be "
                       "blocker|major|minor" % (finding.get("severity"),))
    return repairs


def _excerpt(proposal: Dict[str, Any]) -> str:
    """Short evidence excerpt naming the package."""
    name = proposal.get("name")
    if isinstance(name, (str, int, float)) and str(name).strip():
        return str(name)[:200]
    return "(proposal)"


def _normalize_proposal(proposal: Any) -> Dict[str, Any]:
    """Fill total defaults so partial input never crashes."""
    proposal = proposal if isinstance(proposal, dict) else {}
    return {
        "name": str(proposal.get("name", "")),
        "license": str(proposal.get("license", "")),
        "abandoned": bool(proposal.get("abandoned", False)),
        "supply_alert": bool(proposal.get("supply_alert", False)),
        "platform_has": bool(proposal.get("platform_has", False)),
        "heavy": bool(proposal.get("heavy", False)),
        "deletes_loc": int(proposal.get("deletes_loc") or 0),
        "local_loc": int(proposal.get("local_loc") or 0),
        "local_secure": bool(proposal.get("local_secure", False)),
        "pinned": bool(proposal.get("pinned", False)),
        "revert_plan": str(proposal.get("revert_plan", "")),
    }


def _check_license(proposal: Dict[str, Any]) -> List[Dict[str, str]]:
    """License gate: incompatible licenses reject as blockers."""
    if proposal["license"] not in COMPATIBLE_LICENSES:
        return [_make_finding(
            "license-conflict",
            "license %r is incompatible: use a %s-licensed "
            "alternative or a local helper"
            % (proposal["license"] or "(none)",
               "/".join(COMPATIBLE_LICENSES[:2])),
            _excerpt(proposal), severity="blocker")]
    return []


def _check_supply(proposal: Dict[str, Any]) -> List[Dict[str, str]]:
    """Supply-chain gate: abandoned or alerted packages reject."""
    if proposal["abandoned"] or proposal["supply_alert"]:
        return [_make_finding(
            "supply-chain-alert",
            "package %r is abandoned or under supply-chain "
            "alert: pin a maintained fork or write the local "
            "helper" % proposal["name"],
            _excerpt(proposal), severity="blocker")]
    return []


def _check_platform(proposal: Dict[str, Any]) -> List[Dict[str, str]]:
    """Platform gate: no dependency duplicating stdlib."""
    if proposal["platform_has"]:
        return [_make_finding(
            "duplicates-platform",
            "platform already owns %r: use the native capability "
            "instead of a dependency" % proposal["name"],
            _excerpt(proposal))]
    return []


def _check_heavy(proposal: Dict[str, Any]) -> List[Dict[str, str]]:
    """Weight gate: popular-but-heavy libraries need to earn it
    by deleting owned complexity."""
    if proposal["heavy"] and proposal["deletes_loc"] < 500:
        return [_make_finding(
            "heavy-for-value",
            "heavy library %r deletes only %d owned LOC: adopt "
            "only when it deletes real complexity (>= 500 LOC) "
            "or use the local helper"
            % (proposal["name"], proposal["deletes_loc"]),
            _excerpt(proposal))]
    return []


def _check_local(proposal: Dict[str, Any]) -> List[Dict[str, str]]:
    """Local-helper gate: a tiny secure local helper wins over a
    dependency that buys nothing."""
    if proposal["local_secure"] and proposal["local_loc"] <= 50 \
            and proposal["deletes_loc"] <= 0:
        return [_make_finding(
            "local-cheaper",
            "tiny secure local helper (%d LOC) beats a dependency "
            "for %r: write it locally"
            % (proposal["local_loc"], proposal["name"]),
            _excerpt(proposal))]
    return []


_CHECKS = (
    _check_license,
    _check_supply,
    _check_platform,
    _check_heavy,
    _check_local,
)


class DependencyDecision:
    """One dependency decision outcome for one proposal."""

    verdict: str = "REJECT"
    findings: List[Dict[str, str]] = []  # type: ignore[assignment]

    def __init__(self, verdict: str = "REJECT",
                 findings: Optional[List[Dict[str, str]]] = None):
        self.verdict = verdict
        self.findings = list(findings or [])


def decide(proposal: Any) -> DependencyDecision:
    """Map one dependency proposal to its verdict.

    All five frozen rules run in order; the first hit decides
    the rejection reason. A library proposal clearing every
    rule is ADOPT-LIBRARY; a proposal where the local helper
    wins is ADOPT-LOCAL (reported via local-cheaper); anything
    else is REJECT. Pure function: no I/O, deterministic in
    its input. This decides; it never installs, never pins,
    never writes a lockfile.
    """
    normalized = _normalize_proposal(proposal)
    for check in _CHECKS:
        findings = check(normalized)
        if findings:
            if findings[0]["rule"] == "local-cheaper":
                return DependencyDecision(
                    verdict="ADOPT-LOCAL", findings=findings)
            return DependencyDecision(
                verdict="REJECT", findings=findings)
    return DependencyDecision(verdict="ADOPT-LIBRARY", findings=[])


def clean_proposal() -> Dict[str, Any]:
    """One clean dependency proposal (ADOPT-LIBRARY).

    An MIT library deleting 500 owned LOC with a pin and a
    revert plan. Callers mutate one dimension per test.
    """
    return {
        "name": "demo-lib",
        "license": "MIT",
        "abandoned": False,
        "supply_alert": False,
        "platform_has": False,
        "heavy": True,
        "deletes_loc": 500,
        "local_loc": 200,
        "local_secure": False,
        "pinned": True,
        "revert_plan": "revert the commit and unlock",
    }


def _entries_of(corpus: Any) -> List[Dict[str, Any]]:
    if isinstance(corpus, dict):
        entries = corpus.get("entries")
    else:
        entries = corpus
    if not isinstance(entries, list):
        return []
    return entries


def validate_dependency_corpus(corpus: Any) -> Tuple[List[str],
                                                     List[Dict[str, Any]]]:
    """Validate the frozen dependency fixture oracle.

    Returns (findings, entries); an empty findings list means
    the corpus is a valid frozen oracle: frozen marker set,
    stable provenance, at least 8 entries, unique well-formed
    IDs, every entry computing its expected rules and verdict,
    and all 5 dependency rules covered.
    """
    if isinstance(corpus, dict):
        if corpus.get("_frozen") is not True:
            return (["dependency corpus is not frozen: set "
                     "\"_frozen\": true"], [])
        provenance = str(corpus.get("_provenance", ""))
        if "Stage 39 #130" not in provenance:
            return (["dependency corpus provenance must name "
                      "\"Stage 39 #130\""], [])
    elif not isinstance(corpus, list):
        return (["dependency corpus must be a JSON object with an "
                 "'entries' array (or a bare array)"], [])
    entries = _entries_of(corpus)
    findings: List[str] = []
    if len(entries) < 8:
        findings.append("dependency corpus holds %d entries, want "
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
                            "dependency-contract.<class>.<nn>" % cid)
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
        if "expected_verdict" not in entry:
            findings.append("entry %s: expected_verdict is required"
                            % cid)
        elif entry.get("expected_verdict") not in VERDICTS:
            findings.append("entry %s: expected_verdict %r is not "
                            "a frozen verdict" % (cid, entry.get(
                                "expected_verdict")))
            continue
        result = decide(entry.get("proposal", {}))
        computed = sorted({f["rule"] for f in result.findings})
        if sorted(str(r) for r in expected) != computed:
            findings.append("entry %s: expected_rules %r != "
                            "decide %r"
                            % (cid, sorted(str(r)
                                           for r in expected),
                               computed))
        if entry.get("expected_verdict") != result.verdict:
            findings.append("entry %s: expected_verdict %r != "
                            "decide %r" % (cid, entry.get(
                                "expected_verdict"),
                                result.verdict))
    for rule in RULES:
        if rule not in covered:
            findings.append("rule %r has no entries (all 5 "
                            "dependency rules are required)"
                            % rule)
    return findings, entries
