"""Stage 61a Standard half: the Release Verification Mold and runtime
promotion contract.

Release claim IDs plus the Release Mold contract prove
integrated behavior, deployment, rollback, restore,
provenance, and runtime — independently of slice-level green.
No release promotes on percentage-complete milestones, stale
artifacts, broken integration, failed rollback, unusable
backups, missing attestations, breached invariants, missing
telemetry, partial green, or expired evidence. Promotion needs
a built, attacked, and qualified Release Mold plus a canary
with declared exposure, baseline, observation window, 2-5
invariants, and success/halt thresholds. ``evaluate`` maps one
release package to PROMOTE / HOLD / REFUSE;
``validate_release_corpus`` checks the frozen oracle. Packages
are plain data; missing keys fall back to total defaults, never
a crash.

Frozen verdicts: PROMOTE, HOLD, REFUSE.

Frozen release claim IDs::

  integrated-behavior / deployment-proof / rollback-proof /
  restore-proof / provenance-proof / runtime-proof / canary-proof

Frozen rules, in check order (first hit decides)::

  open-issues        — open release-blocking Issues: REFUSE.
  stale-artifact     — stale build artifact: REFUSE and rebuild.
  broken-integration — broken integrated behavior: REFUSE.
  failed-rollback    — rollback drill failed: REFUSE.
  unusable-backup    — backup/config/data unrestorable: REFUSE.
  missing-attestation— SBOM/attestation missing: REFUSE.
  invariant-breach   — canary invariant breached: REFUSE and halt.
  missing-telemetry  — canary telemetry missing: REFUSE.
  partial-green      — partial green treated as release-ready:
                       REFUSE.
  expired-evidence   — evidence past its window: REFUSE and
                       re-prove.
  restore-rpo        — successful restore within RPO/RTO:
                       PROMOTE path (with all proofs present).
  mold-unqualified   — Release Mold not built/attacked/
                       qualified: HOLD.
  canary-missing     — canary not declared (exposure, baseline,
                       window, invariants, thresholds): HOLD.
  clean-promote      — all proofs present and fresh: PROMOTE.

Findings use the standard five keys via ``FINDING_FIELDS``;
``SEVERITIES`` names the allowed severities;
``validate_finding`` returns repair strings (empty means
valid). Pure functions: no I/O, no subprocess, no network —
packages in, verdicts out. Provider permissions never widen
past narrow release-only provenance scope; the hyperbolic-core
runtime proofbed follows as Stage 61b.
"""

from typing import Any, Dict, List, Optional, Tuple

import re as _re

# Frozen release verdicts.
VERDICTS = (
    "PROMOTE",
    "HOLD",
    "REFUSE",
)

# Frozen release claim IDs.
CLAIMS = (
    "integrated-behavior",
    "deployment-proof",
    "rollback-proof",
    "restore-proof",
    "provenance-proof",
    "runtime-proof",
    "canary-proof",
)

SEVERITIES = ("blocker", "major", "minor")

FINDING_FIELDS = ("id", "rule", "finding", "severity", "excerpt")

# Frozen release rules, in check order.
RULES = (
    "open-issues",
    "stale-artifact",
    "broken-integration",
    "failed-rollback",
    "unusable-backup",
    "missing-attestation",
    "invariant-breach",
    "missing-telemetry",
    "partial-green",
    "expired-evidence",
    "restore-rpo",
    "mold-unqualified",
    "canary-missing",
    "clean-promote",
)

# Verdict each rule carries.
RULE_VERDICTS = {
    "open-issues": "REFUSE",
    "stale-artifact": "REFUSE",
    "broken-integration": "REFUSE",
    "failed-rollback": "REFUSE",
    "unusable-backup": "REFUSE",
    "missing-attestation": "REFUSE",
    "invariant-breach": "REFUSE",
    "missing-telemetry": "REFUSE",
    "partial-green": "REFUSE",
    "expired-evidence": "REFUSE",
    "restore-rpo": "PROMOTE",
    "mold-unqualified": "HOLD",
    "canary-missing": "HOLD",
    "clean-promote": "PROMOTE",
}

# Entry-ID shape for the frozen oracle.
_ENTRY_ID_RE = _re.compile(r"^release-mold\.[a-z-]+\.\d{2}$")


def _make_finding(rule: str, message: str, excerpt: str,
                  severity: str = "major") -> Dict[str, str]:
    """Build one structured release finding dict."""
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
        repairs.append("finding rule %r is not a frozen Stage 61a "
                       "release rule" % (rule,))
    if "severity" in finding and finding.get("severity") not in SEVERITIES:
        repairs.append("finding severity %r must be "
                       "blocker|major|minor" % (finding.get("severity"),))
    return repairs


def _excerpt(package: Dict[str, Any]) -> str:
    """Short evidence excerpt naming the release."""
    for key in ("release", "version", "milestone"):
        value = package.get(key)
        if isinstance(value, (str, int, float)) and str(value).strip():
            return str(value)[:200]
    return "(release)"


def _normalize_package(package: Any) -> Dict[str, Any]:
    """Fill total defaults so partial input never crashes."""
    package = package if isinstance(package, dict) else {}
    claims = package.get("claims")
    invariants = package.get("canary_invariants")
    return {
        "release": str(package.get("release", "")),
        "open_blockers": int(package.get("open_blockers") or 0),
        "artifact_fresh": bool(package.get(
            "artifact_fresh", True)),
        "integration_green": bool(package.get(
            "integration_green", True)),
        "rollback_ok": bool(package.get("rollback_ok", True)),
        "backup_restorable": bool(package.get(
            "backup_restorable", True)),
        "attested": bool(package.get("attested", True)),
        "invariants_held": bool(package.get(
            "invariants_held", True)),
        "telemetry_present": bool(package.get(
            "telemetry_present", True)),
        "partial_green": bool(package.get(
            "partial_green", False)),
        "evidence_fresh": bool(package.get(
            "evidence_fresh", True)),
        "restore_rpo_ok": bool(package.get(
            "restore_rpo_ok", False)),
        "restore_rto_ok": bool(package.get(
            "restore_rto_ok", False)),
        "mold_built": bool(package.get("mold_built", False)),
        "mold_attacked": bool(package.get(
            "mold_attacked", False)),
        "mold_qualified": bool(package.get(
            "mold_qualified", False)),
        "canary_declared": bool(package.get(
            "canary_declared", False)),
        "canary_exposure": str(package.get(
            "canary_exposure", "") or ""),
        "canary_window": str(package.get(
            "canary_window", "") or ""),
        "canary_invariants": list(invariants)
        if isinstance(invariants, list) else [],
        "claims": [str(c) for c in claims
                   if isinstance(c, (str, int, float))]
        if isinstance(claims, list) else [],
    }


class ReleaseDecision:
    """One release outcome for one package."""

    verdict: str = "REFUSE"
    rule: str = "open-issues"
    findings: List[Dict[str, str]] = []  # type: ignore[assignment]

    def __init__(self, verdict: str = "REFUSE",
                 rule: str = "open-issues",
                 findings: Optional[List[Dict[str, str]]] = None):
        self.verdict = verdict
        self.rule = rule
        self.findings = list(findings or [])


def _decide(rule: str, message: str, tag: str,
            severity: str = "major") -> ReleaseDecision:
    return ReleaseDecision(
        verdict=RULE_VERDICTS[rule], rule=rule,
        findings=[_make_finding(rule, message, tag,
                                severity=severity)])


def evaluate(package: Any) -> ReleaseDecision:
    """Map one release package to PROMOTE / HOLD / REFUSE.

    Blockers, stale artifacts, broken integration, failed
    rollbacks, unrestorable backups, missing attestations,
    breached invariants, missing telemetry, partial green, and
    expired evidence refuse; proven restores promote; unbuilt
    molds and undeclared canaries hold; complete fresh packages
    promote. Pure function: no I/O, deterministic in its input.
    This decides; it never deploys, never promotes live.
    """
    item = _normalize_package(package)
    tag = _excerpt(item)
    if item["open_blockers"] > 0:
        return _decide(
            "open-issues",
            "%d open release-blocking Issues: REFUSE"
            % item["open_blockers"],
            tag, severity="blocker")
    if not item["artifact_fresh"]:
        return _decide(
            "stale-artifact",
            "stale build artifact: REFUSE and rebuild",
            tag)
    if not item["integration_green"]:
        return _decide(
            "broken-integration",
            "broken integrated behavior: REFUSE",
            tag, severity="blocker")
    if not item["rollback_ok"]:
        return _decide(
            "failed-rollback",
            "rollback drill failed: REFUSE",
            tag, severity="blocker")
    if not item["backup_restorable"]:
        return _decide(
            "unusable-backup",
            "backup/config/data unrestorable: REFUSE",
            tag, severity="blocker")
    if not item["attested"]:
        return _decide(
            "missing-attestation",
            "SBOM/attestation missing: REFUSE",
            tag)
    if not item["invariants_held"]:
        return _decide(
            "invariant-breach",
            "canary invariant breached: REFUSE and halt",
            tag, severity="blocker")
    if not item["telemetry_present"]:
        return _decide(
            "missing-telemetry",
            "canary telemetry missing: REFUSE",
            tag)
    if item["partial_green"]:
        return _decide(
            "partial-green",
            "partial green treated as release-ready: REFUSE",
            tag, severity="blocker")
    if not item["evidence_fresh"]:
        return _decide(
            "expired-evidence",
            "evidence past its window: REFUSE and re-prove",
            tag)
    missing_claims = [c for c in CLAIMS
                      if c not in item["claims"]]
    if item["restore_rpo_ok"] and item["restore_rto_ok"] \
            and not missing_claims and item["evidence_fresh"]:
        return _decide(
            "restore-rpo",
            "successful restore within RPO/RTO with all %d "
            "claims: PROMOTE path" % len(CLAIMS),
            tag, severity="minor")
    if not (item["mold_built"] and item["mold_attacked"]
            and item["mold_qualified"]):
        return _decide(
            "mold-unqualified",
            "Release Mold not built/attacked/qualified: HOLD",
            tag)
    invariants = [str(v) for v in item["canary_invariants"]
                  if isinstance(v, (str, int, float))]
    if not item["canary_declared"] or not item[
            "canary_exposure"] or not item["canary_window"] \
            or not (2 <= len(invariants) <= 5):
        return _decide(
            "canary-missing",
            "canary not declared (exposure, baseline, window, "
            "2-5 invariants, thresholds): HOLD",
            tag)
    if missing_claims:
        return _decide(
            "mold-unqualified",
            "missing release claims %r: HOLD" % (missing_claims,),
            tag)
    return ReleaseDecision(
        verdict="PROMOTE", rule="clean-promote",
        findings=[_make_finding(
            "clean-promote",
            "all proofs present and fresh: PROMOTE",
            tag, severity="minor")])


def clean_package() -> Dict[str, Any]:
    """One clean release package (PROMOTE).

    All claims present, fresh evidence, proven restore, built
    mold, declared canary. Callers mutate one dimension per
    test.
    """
    return {
        "release": "v5.0",
        "open_blockers": 0,
        "artifact_fresh": True,
        "integration_green": True,
        "rollback_ok": True,
        "backup_restorable": True,
        "attested": True,
        "invariants_held": True,
        "telemetry_present": True,
        "partial_green": False,
        "evidence_fresh": True,
        "restore_rpo_ok": True,
        "restore_rto_ok": True,
        "mold_built": True,
        "mold_attacked": True,
        "mold_qualified": True,
        "canary_declared": True,
        "canary_exposure": "1% for 24h",
        "canary_window": "24h",
        "canary_invariants": ["error-rate", "latency-p99",
                              "rollback-time"],
        "claims": list(CLAIMS),
    }


def _entries_of(corpus: Any) -> List[Dict[str, Any]]:
    if isinstance(corpus, dict):
        entries = corpus.get("entries")
    else:
        entries = corpus
    if not isinstance(entries, list):
        return []
    return entries


def validate_release_corpus(corpus: Any) -> Tuple[List[str],
                                                  List[Dict[str, Any]]]:
    """Validate the frozen release fixture oracle.

    Returns (findings, entries); an empty findings list means
    the corpus is a valid frozen oracle: frozen marker set,
    stable provenance, at least 14 entries, unique well-formed
    IDs, every entry computing its expected rule and verdict,
    and all 14 release rules covered.
    """
    if isinstance(corpus, dict):
        if corpus.get("_frozen") is not True:
            return (["release corpus is not frozen: set "
                     "\"_frozen\": true"], [])
        provenance = str(corpus.get("_provenance", ""))
        if "Stage 61a #152" not in provenance:
            return (["release corpus provenance must name "
                      "\"Stage 61a #152\""], [])
    elif not isinstance(corpus, list):
        return (["release corpus must be a JSON object with an "
                 "'entries' array (or a bare array)"], [])
    entries = _entries_of(corpus)
    findings: List[str] = []
    if len(entries) < 14:
        findings.append("release corpus holds %d entries, want "
                        "at least 14" % len(entries))
    seen: Dict[str, int] = {}
    covered = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            findings.append("entries[%d] is not a mapping" % index)
            continue
        cid = str(entry.get("id", ""))
        if not _ENTRY_ID_RE.match(cid):
            findings.append("entry %r: id is not "
                            "release-mold.<class>.<nn>" % cid)
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
                            "frozen Stage 61a release rule"
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
        result = evaluate(entry.get("package", {}))
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
            findings.append("rule %r has no entries (all 14 "
                            "release rules are required)"
                            % rule)
    return findings, entries
