"""Stage 49 Standard half: hardened worktrees, subagents, SAFE parallelism,
and cleanup.

Parallel autonomy runs fast only when mutable independence is
mechanically proven: two slices run together iff they touch
disjoint files, share no mutable schema/state, exchange no
dependent output, and hold distinct leases. ``decide`` maps one
parallelism proposal to SAFE / SERIALIZE / REFUSE;
``validate_parallel_corpus`` checks the frozen oracle.
Proposals are plain data; missing keys fall back to total
defaults, never a crash. UNKNOWN never serializes to an
assumed-safe default — only explicit SAFE permits
parallelism.

Frozen verdicts: SAFE, SERIALIZE, REFUSE.

Frozen rules, in check order (first hit decides)::

  same-files        — writers touch the same files: serialize.
  shared-schema     — shared mutable schema/state: serialize.
  dependent-output  — one slice needs the other's output:
                      serialize.
  orphan-process    — orphan writer process: refuse until
                      reaped and reconciled.
  unpushed-work     — unpushed commits on either slice: refuse
                      cleanup-affecting parallelism.
  closed-unmerged   — closed-but-unmerged branch: refuse.
  squash-recognized — squash-merged content recognized as
                      merged: cleanup may proceed (SAFE).
  cloud-workspace   — cloud workspace condition classified:
                      missing reports refuse, present ones hold.
  missing-report    — required subagent report absent: refuse.
  classifier-failed — the concurrency classifier threw or is
                      missing: refuse (UNKNOWN never SAFE).
  clean-parallel    — disjoint, independent, leased: SAFE.

Cleanup policy (same verdicts): never remove a worktree with
an open PR, unpushed commits, or an active writer; only
explicit SAFE permits parallel mutation. Findings use the
standard five keys via ``FINDING_FIELDS``; ``SEVERITIES``
names the allowed severities; ``validate_finding`` returns
repair strings (empty means valid). Pure functions: no I/O, no
subprocess, no network — proposals in, verdicts out.
"""

from typing import Any, Dict, List, Optional, Tuple

import re as _re

# Frozen parallelism verdicts.
VERDICTS = ("SAFE", "SERIALIZE", "REFUSE")

SEVERITIES = ("blocker", "major", "minor")

FINDING_FIELDS = ("id", "rule", "finding", "severity", "excerpt")

# Frozen parallelism rules, in check order.
RULES = (
    "same-files",
    "shared-schema",
    "dependent-output",
    "orphan-process",
    "unpushed-work",
    "closed-unmerged",
    "squash-recognized",
    "cloud-workspace",
    "missing-report",
    "classifier-failed",
    "clean-parallel",
)

# Verdict each rule carries.
RULE_VERDICTS = {
    "same-files": "SERIALIZE",
    "shared-schema": "SERIALIZE",
    "dependent-output": "SERIALIZE",
    "orphan-process": "REFUSE",
    "unpushed-work": "REFUSE",
    "closed-unmerged": "REFUSE",
    "squash-recognized": "SAFE",
    "cloud-workspace": "REFUSE",
    "missing-report": "REFUSE",
    "classifier-failed": "REFUSE",
    "clean-parallel": "SAFE",
}

# Entry-ID shape for the frozen oracle.
_ENTRY_ID_RE = _re.compile(r"^safe-parallelism\.[a-z-]+\.\d{2}$")


def _make_finding(rule: str, message: str, excerpt: str,
                  severity: str = "major") -> Dict[str, str]:
    """Build one structured parallelism finding dict."""
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
        repairs.append("finding rule %r is not a frozen Stage 49 "
                       "parallelism rule" % (rule,))
    if "severity" in finding and finding.get("severity") not in SEVERITIES:
        repairs.append("finding severity %r must be "
                       "blocker|major|minor" % (finding.get("severity"),))
    return repairs


def _excerpt(proposal: Dict[str, Any]) -> str:
    """Short evidence excerpt naming the slices."""
    for key in ("slices", "pair", "worktree"):
        value = proposal.get(key)
        if isinstance(value, (str, int, float)) and str(value).strip():
            return str(value)[:200]
    items = proposal.get("files_a")
    if isinstance(items, list) and items:
        return str(items[0])[:200]
    return "(parallel)"


def _normalize_proposal(proposal: Any) -> Dict[str, Any]:
    """Fill total defaults so partial input never crashes."""
    proposal = proposal if isinstance(proposal, dict) else {}

    def _strs(value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(v) for v in value
                    if isinstance(v, (str, int, float))]
        return []

    return {
        "files_a": _strs(proposal.get("files_a")),
        "files_b": _strs(proposal.get("files_b")),
        "shared_schema": bool(proposal.get(
            "shared_schema", False)),
        "dependent_output": bool(proposal.get(
            "dependent_output", False)),
        "orphan_process": bool(proposal.get(
            "orphan_process", False)),
        "unpushed": bool(proposal.get("unpushed", False)),
        "closed_unmerged": bool(proposal.get(
            "closed_unmerged", False)),
        "squash_merged": bool(proposal.get(
            "squash_merged", False)),
        "cloud_workspace": str(proposal.get(
            "cloud_workspace", "") or ""),
        "report_present": bool(proposal.get(
            "report_present", True)),
        "classifier_ok": bool(proposal.get(
            "classifier_ok", True)),
        "leases_distinct": bool(proposal.get(
            "leases_distinct", True)),
        "open_pr": bool(proposal.get("open_pr", False)),
        "active_writer": bool(proposal.get(
            "active_writer", False)),
    }


class ParallelDecision:
    """One parallelism outcome for one proposal."""

    verdict: str = "REFUSE"
    rule: str = "clean-parallel"
    findings: List[Dict[str, str]] = []  # type: ignore[assignment]

    def __init__(self, verdict: str = "REFUSE",
                 rule: str = "clean-parallel",
                 findings: Optional[List[Dict[str, str]]] = None):
        self.verdict = verdict
        self.rule = rule
        self.findings = list(findings or [])


def _decide(rule: str, message: str, tag: str,
            severity: str = "major") -> ParallelDecision:
    return ParallelDecision(
        verdict=RULE_VERDICTS[rule], rule=rule,
        findings=[_make_finding(rule, message, tag,
                                severity=severity)])


def decide(proposal: Any) -> ParallelDecision:
    """Map one parallelism proposal to SAFE / SERIALIZE / REFUSE.

    Shared files, schemas, and dependent outputs serialize;
    orphan processes, unpushed work, closed-unmerged branches,
    cloud gaps, missing reports, and classifier failures
    refuse; squash-recognized merges and clean disjoint leased
    pairs are SAFE. UNKNOWN never defaults safe: only explicit
    SAFE permits parallelism. Pure function: no I/O,
    deterministic in its input. This decides; it never spawns,
    never merges, never deletes.
    """
    item = _normalize_proposal(proposal)
    tag = _excerpt(item)
    if set(item["files_a"]) & set(item["files_b"]):
        return _decide(
            "same-files",
            "writers touch the same files %r: serialize"
            % sorted(set(item["files_a"])
                     & set(item["files_b"])),
            tag)
    if item["shared_schema"]:
        return _decide(
            "shared-schema",
            "shared mutable schema/state: serialize until the "
            "schema boundary splits",
            tag)
    if item["dependent_output"]:
        return _decide(
            "dependent-output",
            "one slice needs the other's output: serialize in "
            "dependency order",
            tag)
    if item["orphan_process"]:
        return _decide(
            "orphan-process",
            "orphan writer process: reap and reconcile before "
            "any parallelism",
            tag, severity="blocker")
    if item["unpushed"]:
        return _decide(
            "unpushed-work",
            "unpushed commits present: refuse cleanup-affecting "
            "parallelism until pushed or reconciled",
            tag)
    if item["closed_unmerged"] and not item["squash_merged"]:
        return _decide(
            "closed-unmerged",
            "closed-but-unmerged branch: refuse until the "
            "branch reconciles",
            tag)
    if item["closed_unmerged"] and item["squash_merged"]:
        return _decide(
            "squash-recognized",
            "squash-merged content recognized as merged: "
            "cleanup may proceed",
            tag, severity="minor")
    if item["cloud_workspace"] == "missing":
        return _decide(
            "cloud-workspace",
            "cloud workspace missing: classify before "
            "parallelizing",
            tag)
    if not item["report_present"]:
        return _decide(
            "missing-report",
            "required subagent report absent: refuse until the "
            "report lands",
            tag)
    if not item["classifier_ok"]:
        return _decide(
            "classifier-failed",
            "concurrency classifier threw or is missing: "
            "UNKNOWN is never SAFE",
            tag, severity="blocker")
    if not item["leases_distinct"]:
        return _decide(
            "shared-schema",
            "slices share one lease: serialize under a single "
            "writer",
            tag)
    return _decide(
        "clean-parallel",
        "disjoint files, independent outputs, distinct leases: "
        "SAFE to parallelize",
        tag, severity="minor")


def clean_proposal() -> Dict[str, Any]:
    """One clean parallelism proposal (SAFE).

    Disjoint files, no shared schema, independent outputs,
    distinct leases, reports present, classifier healthy.
    Callers mutate one dimension per test.
    """
    return {
        "files_a": ["tools/alpha.py"],
        "files_b": ["tools/beta.py"],
        "shared_schema": False,
        "dependent_output": False,
        "orphan_process": False,
        "unpushed": False,
        "closed_unmerged": False,
        "squash_merged": False,
        "cloud_workspace": "present",
        "report_present": True,
        "classifier_ok": True,
        "leases_distinct": True,
        "open_pr": False,
        "active_writer": False,
    }


def _entries_of(corpus: Any) -> List[Dict[str, Any]]:
    if isinstance(corpus, dict):
        entries = corpus.get("entries")
    else:
        entries = corpus
    if not isinstance(entries, list):
        return []
    return entries


def validate_parallel_corpus(corpus: Any) -> Tuple[List[str],
                                                   List[Dict[str, Any]]]:
    """Validate the frozen parallelism fixture oracle.

    Returns (findings, entries); an empty findings list means
    the corpus is a valid frozen oracle: frozen marker set,
    stable provenance, at least 11 entries, unique well-formed
    IDs, every entry computing its expected rule and verdict,
    and all 11 parallelism rules covered.
    """
    if isinstance(corpus, dict):
        if corpus.get("_frozen") is not True:
            return (["parallel corpus is not frozen: set "
                     "\"_frozen\": true"], [])
        provenance = str(corpus.get("_provenance", ""))
        if "Stage 49 #140" not in provenance:
            return (["parallel corpus provenance must name "
                      "\"Stage 49 #140\""], [])
    elif not isinstance(corpus, list):
        return (["parallel corpus must be a JSON object with an "
                 "'entries' array (or a bare array)"], [])
    entries = _entries_of(corpus)
    findings: List[str] = []
    if len(entries) < 11:
        findings.append("parallel corpus holds %d entries, want "
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
                            "safe-parallelism.<class>.<nn>" % cid)
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
                            "frozen Stage 49 parallelism rule"
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
        result = decide(entry.get("proposal", {}))
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
                            "parallelism rules are required)"
                            % rule)
    return findings, entries
