"""T19 Standard half: cleanup with proven-merge, head-match, and receipt.

Cleanup runs only behind a revalidated merge receipt (intended
branch + merged head + merge commit re-queried from the remote
tracker; local-only receipts never substitute). Head-match or
content-equivalence is required; clean tree + preserved evidence
(90-day retention) is required; unique/unpushed work is refused
(missing upstream = uncertainty, never safety); active/unknown
writers are refused (never converted to safe); dependents,
locked worktrees, and closed-but-unmerged items are preserved.
Predicates re-check immediately before mutation; deletion is
conditional native exact-target deletion, never pattern/bulk.
Every attempt writes a receipt; restarts reconcile idempotently;
ambiguous orphans quarantine for owner decision — never silent
delete, never silent adopt.

Pure functions: no I/O, no network — data in, violations out.
The live path (standardctl worktrees) revalidates against the
remote; these helpers pin the predicate semantics so tests prove
each refusal without touching the network.
"""

from typing import Any, Dict, List, Optional, Tuple

# T19 predicate names (plan 10 T19 fixture set).
PREDICATES = (
    "merge_receipt",
    "head_match",
    "clean_tree",
    "no_unpushed",
    "no_active_writer",
    "no_dependents",
    "pre_mutation_recheck",
    "receipt",
    "quarantine",
)


def check_merge_receipt(receipt: Any) -> List[str]:
    """Return violations when the merge receipt is not remote truth.

    The receipt carries intended branch + merged head + merge
    commit re-queried from the remote tracker at cleanup time; a
    local-only receipt (including squash-aware local checks)
    never substitutes remote merge truth.
    """
    violations: List[str] = []
    if not isinstance(receipt, dict):
        return ["merge receipt must be a mapping"]
    for field in ("branch", "merged_head", "merge_commit"):
        if not receipt.get(field):
            violations.append(
                "merge receipt missing %r: intended branch + "
                "merged head + merge commit required" % (field,))
    if receipt.get("local_only"):
        violations.append(
            "local-only receipt refused: re-query the remote "
            "tracker at cleanup time (remote merge truth only)")
    if not receipt.get("remote_revalidated"):
        violations.append(
            "merge receipt not revalidated: re-query the remote "
            "tracker at cleanup time")
    return violations


def check_head_match(local: Any, merged: Any,
                     equivalent: bool = False) -> List[str]:
    """Return violations when the worktree diverges from merged.

    The local head equals the merged head or is
    content-equivalent to the merged tree; any other divergence
    blocks deletion naming both heads.
    """
    if equivalent:
        return []
    if str(local) != str(merged):
        return ["head mismatch: local %r != merged %r; "
                "head-match or content-equivalence required"
                % (local, merged)]
    return []


def check_clean_tree(state: Any) -> List[str]:
    """Return violations when the tree carries information.

    No uncommitted or untracked changes that carry information;
    required evidence/artifacts preserved (90-day retention)
    before any deletion. A dirty tree or missing evidence
    blocks deletion.
    """
    violations: List[str] = []
    if not isinstance(state, dict):
        return ["tree state must be a mapping"]
    if state.get("dirty"):
        violations.append(
            "dirty tree: uncommitted/untracked changes carry "
            "information; deletion blocked")
    if state.get("evidence_preserved") is False:
        violations.append(
            "evidence not preserved: 90-day retention before "
            "any deletion")
    return violations


def check_no_unpushed(commits: Any, upstream: Any) -> List[str]:
    """Return violations for unique/unpushed work.

    Any commit not provably upstream blocks deletion; a missing
    upstream ref is uncertainty (blocks), never safety.
    """
    if upstream is None:
        return ["missing upstream ref: uncertainty, never safety; "
                "deletion blocked"]
    ahead = commits if isinstance(commits, int) else 0
    if ahead > 0:
        return ["%d unpushed commit(s): unique work blocks "
                "deletion" % (ahead,)]
    return []


def check_no_active_writer(writer: Any) -> List[str]:
    """Return violations for active/unknown writers.

    Owned sessions stopped, leases revoked, writer activity
    confirmed via APIs; an active or unknown writer blocks
    deletion and is never converted to safe/complete.
    """
    if not isinstance(writer, dict):
        return ["writer state must be a mapping"]
    state = writer.get("state", "unknown")
    if state in ("active", "unknown"):
        return ["%s writer blocks deletion: never convert to "
                "safe/complete" % (state,)]
    return []


def check_no_dependents(item: Any) -> List[str]:
    """Return violations for protected dependents.

    Worktrees/branches that are dependents of live work, locked
    worktrees, and closed-but-unmerged items are never deleted;
    any such flag blocks deletion naming the protection.
    """
    violations: List[str] = []
    if not isinstance(item, dict):
        return ["cleanup item must be a mapping"]
    for flag in ("dependent_of_live", "locked",
                 "closed_unmerged"):
        if item.get(flag):
            violations.append(
                "protected state %r: never delete dependents, "
                "locked worktrees, or closed-but-unmerged items"
                % (flag,))
    return violations


def check_premutation_recheck(predicates: Any) -> List[str]:
    """Return violations when predicates are stale at mutation.

    Predicates re-check immediately before mutation and deletion
    is conditional on them still holding via the native
    exact-target path; a stale recheck or a pattern/bulk target
    fails naming the break.
    """
    violations: List[str] = []
    if not isinstance(predicates, dict):
        return ["predicate recheck must be a mapping"]
    if not predicates.get("fresh"):
        violations.append(
            "stale predicates: re-check immediately before "
            "mutation")
    target = predicates.get("target", "")
    if predicates.get("bulk") or "*" in str(target):
        violations.append(
            "pattern/bulk deletion forbidden: exact-target "
            "native deletion only")
    if not target:
        violations.append("deletion names no exact target")
    return violations


def check_receipt_written(attempt: Any) -> List[str]:
    """Return violations when an attempt leaves no receipt.

    Every cleanup attempt (success or refusal) writes a receipt;
    a restart reconciles idempotently (already-cleaned state is
    recognized, not re-deleted). A missing receipt fails; a
    double-effect restart fails.
    """
    violations: List[str] = []
    if not isinstance(attempt, dict):
        return ["cleanup attempt must be a mapping"]
    if not attempt.get("receipt"):
        violations.append(
            "no cleanup receipt: every attempt (success or "
            "refusal) writes one")
    if attempt.get("double_effect"):
        violations.append(
            "restart double-effect: already-cleaned state is "
            "recognized, not re-deleted")
    return violations


def check_quarantine(item: Any) -> List[str]:
    """Return violations for mishandled ambiguous orphans.

    Ambiguous orphans (uncertain state) quarantine for owner
    decision; silent deletion or silent adoption as safe fails
    naming the mishandling.
    """
    violations: List[str] = []
    if not isinstance(item, dict):
        return ["orphan item must be a mapping"]
    if not item.get("ambiguous"):
        return []
    if item.get("silently_deleted"):
        violations.append(
            "ambiguous orphan silently deleted: quarantine for "
            "owner decision instead")
    if item.get("adopted_safe"):
        violations.append(
            "ambiguous orphan adopted as safe: quarantine for "
            "owner decision instead")
    if not item.get("quarantined"):
        violations.append(
            "ambiguous orphan not quarantined: report for owner "
            "decision")
    return violations


def validate_cleanup_corpus(corpus: Any) -> Tuple[List[str], List[Any]]:
    """Validate the frozen cleanup fixture oracle.

    Returns (findings, entries). Every entry carries an id, a
    target surface (receipt, head, tree, unpushed, writer,
    dependents, recheck, attempt, quarantine), a record, and the
    expected violation fragment ("" means clean).
    """
    if not isinstance(corpus, dict):
        return (["cleanup corpus must be a mapping"], [])
    if corpus.get("_frozen") is not True:
        return (["cleanup corpus is not frozen: set "
                 "\"_frozen\": true"], [])
    entries = corpus.get("entries")
    if not isinstance(entries, list):
        return (["cleanup corpus entries must be a list"], [])
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
        if target == "receipt":
            violations = check_merge_receipt(record)
        elif target == "head":
            violations = check_head_match(
                (record or {}).get("local"),
                (record or {}).get("merged"),
                (record or {}).get("equivalent", False))
        elif target == "tree":
            violations = check_clean_tree(record)
        elif target == "unpushed":
            violations = check_no_unpushed(
                (record or {}).get("ahead", 0),
                (record or {}).get("upstream"))
        elif target == "writer":
            violations = check_no_active_writer(record)
        elif target == "dependents":
            violations = check_no_dependents(record)
        elif target == "recheck":
            violations = check_premutation_recheck(record)
        elif target == "attempt":
            violations = check_receipt_written(record)
        elif target == "quarantine":
            violations = check_quarantine(record)
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


def clean_receipt() -> Dict[str, Any]:
    """One revalidated remote merge receipt."""
    return {"branch": "issue/1-x", "merged_head": "abc",
            "merge_commit": "def", "remote_revalidated": True}
