"""T23 Standard half: full parallel lifecycle benchmark (unit fixtures).

Two independent slices each complete the full lifecycle in
parallel (authorized issue -> readiness -> bounded task ->
isolated leased worker -> exact-head verification -> PR Gate ->
merge -> child update -> parent proof -> cleanup) with no lost
or duplicated effects; one conflicting slice is refused at claim
or merge time without corrupting either clean slice; a fresh
handoff resumes from ledger + Git/tracker state with no
orphaned or duplicated work; child update + parent proof follow
#215 receipt semantics (integration proof, never counts alone);
cleanup validates through #214 predicates with receipts and a
restart replay reconciles idempotently via an exactly-once
ledger; cost/latency/cleanup/false-block accounting is recorded
and measured results (not the unit test alone) gate any
production enablement. Stage 64/65 machinery is reused, never
replaced; no production configuration changes.

Pure functions: no I/O, no network — data in, violations out.
Frozen rules, stable output order.
"""

from typing import Any, Dict, List, Optional, Set, Tuple

# Lifecycle legs each clean slice completes.
LIFECYCLE_LEGS = (
    "authorized_issue",
    "readiness",
    "bounded_task",
    "leased_worker",
    "exact_head_verification",
    "pr_gate",
    "merge",
    "child_update",
    "parent_proof",
    "cleanup",
)


def check_parallel_slices(slices: Any) -> List[str]:
    """Return violations when parallel slices lose/duplicate effects.

    Both slices complete every lifecycle leg; the union of
    effects shows each effect exactly once (no loss, no
    duplication); a slice bypassing the PR Gate or landing via
    local merge fails.
    """
    violations: List[str] = []
    if not isinstance(slices, list):
        return ["slices must be a list"]
    if len(slices) != 2:
        return ["benchmark needs exactly two clean slices, got %r"
                % (len(slices),)]
    seen: Dict[str, int] = {}
    for index, slc in enumerate(slices):
        label = "slice[%d]" % index
        if not isinstance(slc, dict):
            violations.append("%s must be a mapping" % label)
            continue
        for leg in LIFECYCLE_LEGS:
            if not slc.get(leg):
                violations.append(
                    "%s missing lifecycle leg %r" % (label, leg))
        if slc.get("bypassed_gate"):
            violations.append(
                "%s bypassed the PR Gate" % label)
        if slc.get("local_merge"):
            violations.append(
                "%s landed via local merge commands" % label)
        for effect in slc.get("effects") or []:
            seen[effect] = seen.get(effect, 0) + 1
    for effect in sorted(seen):
        if seen[effect] != 1:
            violations.append(
                "effect %r attributed %d times (want exactly once)"
                % (effect, seen[effect]))
    return violations


def check_conflict_refusal(clean_before: Any, conflict: Any,
                           clean_after: Any) -> List[str]:
    """Return violations for a corrupting conflict refusal.

    The conflicting slice is refused with reason and produces
    no partial effects; both clean slices' ledgers are
    unchanged post-refusal.
    """
    violations: List[str] = []
    if not isinstance(conflict, dict):
        return ["conflict record must be a mapping"]
    if not conflict.get("refused"):
        violations.append("conflicting slice was not refused")
    if not conflict.get("reason"):
        violations.append("refusal records no reason")
    if conflict.get("partial_effects"):
        violations.append(
            "conflicting slice left partial effects: %r"
            % (conflict.get("partial_effects"),))
    if clean_before != clean_after:
        violations.append(
            "clean slices corrupted by the refusal")
    return violations


def check_fresh_handoff(before: Any, after: Any) -> List[str]:
    """Return violations for a lossy handoff.

    A fresh session resumes from ledger + Git/tracker state and
    completes its slice with no orphaned or duplicated work:
    the resumed effect set equals the handed-off set plus
    exactly the new completion effects.
    """
    violations: List[str] = []
    if not isinstance(before, dict) or not isinstance(after, dict):
        return ["handoff records must be mappings"]
    if not before.get("ledger") or not before.get("git_state"):
        violations.append(
            "handoff resumes from ledger + Git/tracker state: "
            "sources missing")
    orphaned = (after.get("orphaned") or [])
    if orphaned:
        violations.append("handoff orphaned work: %r" % (orphaned,))
    duplicated = (after.get("duplicated") or [])
    if duplicated:
        violations.append("handoff duplicated work: %r" % (duplicated,))
    if not after.get("completed"):
        violations.append("resumed slice did not complete")
    return violations


def check_child_parent_proof(proof: Any) -> List[str]:
    """Return violations for count-only parent proof.

    Child update + parent proof follow #215 receipt semantics:
    required children MERGED/CLEANED/excluded plus parent
    integration proof; counts alone refuse.
    """
    violations: List[str] = []
    if not isinstance(proof, dict):
        return ["proof record must be a mapping"]
    for child in proof.get("children") or []:
        if isinstance(child, dict) and child.get("state") not in (
                "MERGED", "CLEANED", "EXCLUDED"):
            violations.append(
                "child %r is %r (need MERGED/CLEANED/EXCLUDED)"
                % (child.get("id", "?"), child.get("state")))
    if not proof.get("integration_proof"):
        violations.append(
            "parent proof reduced to child counts: integration "
            "proof required per #215")
    return violations


def check_cleanup_restart(legs: Any) -> List[str]:
    """Return violations for non-idempotent cleanup replay.

    Cleanup validates through #214 predicates with receipts; a
    restart replay reconciles idempotently (replayed run
    changes nothing new; receipts reconcile; no double-count).
    """
    violations: List[str] = []
    if not isinstance(legs, dict):
        return ["cleanup legs must be a mapping"]
    if not legs.get("predicates_hold"):
        violations.append(
            "#214 predicates do not hold on the cleanup legs")
    if not legs.get("cleanup_receipts"):
        violations.append("cleanup receipts missing")
    replay = legs.get("replay") or {}
    if replay.get("new_effects"):
        violations.append(
            "restart replay double-counts: replayed run changes "
            "nothing new")
    if replay.get("double_count"):
        violations.append(
            "restart replay re-executes completed effects")
    return violations


def check_accounting(report: Any) -> List[str]:
    """Return violations for missing benchmark accounting.

    Cost, latency, cleanup, and false-block metrics are all
    present with measured values; a missing metric fails. A
    production-enablement claim without measured evidence
    fails: measured results gate enablement, never the unit
    test alone.
    """
    violations: List[str] = []
    if not isinstance(report, dict):
        return ["accounting report must be a mapping"]
    for metric in ("cost", "latency", "cleanup", "false_blocks"):
        if report.get(metric) is None:
            violations.append(
                "accounting missing %r with measured values"
                % (metric,))
    if report.get("production_enablement") and not report.get(
            "measured_evidence"):
        violations.append(
            "production enablement without measured benchmark "
            "evidence: unit test alone never enables")
    return violations


def check_no_production_change(files: Any) -> List[str]:
    """Return violations for production config changes.

    No production configuration changes land from this
    benchmark; any production path in the diff fails.
    """
    violations: List[str] = []
    if not isinstance(files, list):
        return ["file list must be a list"]
    for path in files:
        text = str(path)
        if text.startswith("prod/") or text.startswith(
                "production/") or text == "production.yaml":
            violations.append(
                "production configuration change %r forbidden: "
                "no production enablement from this benchmark"
                % (path,))
    return violations


def validate_lifecycle_corpus(corpus: Any) -> Tuple[List[str], List[Any]]:
    """Validate the frozen lifecycle-benchmark fixture oracle.

    Returns (findings, entries). Every entry carries an id, a
    target surface (parallel, conflict, handoff, proof,
    restart, accounting, production), a record, and the
    expected violation fragment ("" means clean).
    """
    if not isinstance(corpus, dict):
        return (["lifecycle corpus must be a mapping"], [])
    if corpus.get("_frozen") is not True:
        return (["lifecycle corpus is not frozen: set "
                 "\"_frozen\": true"], [])
    entries = corpus.get("entries")
    if not isinstance(entries, list):
        return (["lifecycle corpus entries must be a list"], [])
    findings: List[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            findings.append("corpus entry is not a mapping: %r"
                            % (entry,))
            continue
        entry_id = entry.get("id", "?")
        target = entry.get("target")
        record = entry.get("record")
        expected = entry.get("expected_violation_fragment", "")
        if target == "parallel":
            violations = check_parallel_slices(record)
        elif target == "conflict":
            violations = check_conflict_refusal(
                entry.get("before"), record,
                entry.get("after"))
        elif target == "handoff":
            violations = check_fresh_handoff(
                entry.get("before", {}), record)
        elif target == "proof":
            violations = check_child_parent_proof(record)
        elif target == "restart":
            violations = check_cleanup_restart(record)
        elif target == "accounting":
            violations = check_accounting(record)
        elif target == "production":
            violations = check_no_production_change(record)
        else:
            findings.append(
                "entry %s has unknown target %r" % (entry_id, target))
            continue
        if expected:
            if not any(expected in v for v in violations):
                findings.append(
                    "entry %s: expected fragment %r not reproduced "
                    "(got %r)" % (entry_id, expected, violations))
        elif violations:
            findings.append(
                "entry %s: expected clean, got %r" % (entry_id,
                                                      violations))
    return (findings, entries)


def clean_slice(name: str) -> Dict[str, Any]:
    """One clean slice completing every lifecycle leg."""
    slc: Dict[str, Any] = {"name": name,
                           "effects": ["%s:merge" % name,
                                       "%s:receipt" % name,
                                       "%s:cleanup" % name]}
    for leg in LIFECYCLE_LEGS:
        slc[leg] = True
    return slc
