"""T20 Standard half: completion receipts (MERGED/CLEANED/excluded).

Issue completion is recorded as distinguishable receipts —
MERGED (remote merge truth only), CLEANED (only after a #214
cleanup receipt; CLEANUP_PENDING and RECOVERY_REQUIRED stay
visible and distinct), and owner-excluded (rationale URL,
never counted delivered) — on existing issues, with parent
closure gated on required children plus parent integration
proof, duplicate close/receipt events as idempotent no-ops, and
membership races refusing close. Entirely inside the existing
tracker: no second tracker, ledger, or state store (Q12).
MERGED never equals CLEANED.

Pure functions: no I/O, no network — data in, violations out.
Frozen rules, stable output order.
"""

from typing import Any, Dict, List, Optional, Set, Tuple

# Receipt states. CLEANUP_PENDING and RECOVERY_REQUIRED are
# visible states, never collapsed into CLEANED.
RECEIPT_STATES = (
    "MERGED",
    "CLEANED",
    "CLEANUP_PENDING",
    "RECOVERY_REQUIRED",
    "EXCLUDED",
)


def check_merged_receipt(receipt: Any) -> List[str]:
    """Return violations for a non-remote MERGED receipt.

    MERGED records only on remote merge truth (PR state + merge
    commit via API); a local-only or squash-aware-local receipt
    never produces MERGED.
    """
    violations: List[str] = []
    if not isinstance(receipt, dict):
        return ["merged receipt must be a mapping"]
    if receipt.get("local_only"):
        return ["MERGED from local-only evidence refused: "
                "remote merge truth (PR state + merge commit via "
                "API) only"]
    if not receipt.get("pr_state") or not receipt.get("merge_commit"):
        violations.append(
            "MERGED needs PR state + merge commit via API")
    return violations


def check_cleaned_receipt(receipt: Any,
                          cleanup_receipt: Any) -> List[str]:
    """Return violations for CLEANED without cleanup proof.

    CLEANED records only after #214-predicate cleanup succeeds
    with its cleanup receipt; CLEANUP_PENDING and
    RECOVERY_REQUIRED remain distinct and are never collapsed
    into CLEANED; a CLEANED without a #214 receipt is
    forbidden.
    """
    violations: List[str] = []
    if not isinstance(receipt, dict):
        return ["cleaned receipt must be a mapping"]
    state = receipt.get("state")
    if state in ("CLEANUP_PENDING", "RECOVERY_REQUIRED"):
        if state == "CLEANED":
            pass
        return []
    if state == "CLEANED" and not cleanup_receipt:
        return ["CLEANED without a #214 cleanup receipt "
                "forbidden"]
    if state not in RECEIPT_STATES and state != "CLEANED":
        violations.append("unknown receipt state %r" % (state,))
    return violations


def check_exclusion(item: Any) -> List[str]:
    """Return violations for miscounted exclusions.

    Owner exclusion is a distinct receipt with a rationale URL;
    excluded items are never counted delivered;
    duplicate/not-planned closes are excluded, never delivered.
    """
    violations: List[str] = []
    if not isinstance(item, dict):
        return ["exclusion item must be a mapping"]
    if item.get("excluded"):
        if not item.get("rationale_url"):
            violations.append(
                "exclusion needs a rationale URL")
        if item.get("counted_delivered"):
            violations.append(
                "excluded item counted delivered: excluded is "
                "never delivered")
    if item.get("close_reason") in ("duplicate", "not-planned"):
        if item.get("counted_delivered"):
            violations.append(
                "%s closes are excluded, never delivered"
                % item.get("close_reason"))
    return violations


def check_parent_gate(parent: Any) -> List[str]:
    """Return violations for premature parent closure.

    A parent closes only when every required child is
    MERGED/CLEANED or explicitly owner-excluded AND the parent
    integration proof exists; child counts alone never close a
    parent; an open required child refuses the close.
    """
    violations: List[str] = []
    if not isinstance(parent, dict):
        return ["parent record must be a mapping"]
    children = parent.get("children") or []
    if not parent.get("closing"):
        return []
    for child in children:
        if not isinstance(child, dict):
            violations.append("child record must be a mapping")
            continue
        state = child.get("state")
        if state not in ("MERGED", "CLEANED", "EXCLUDED"):
            violations.append(
                "parent close refused: required child %r is %r "
                "(need MERGED/CLEANED/EXCLUDED)" % (
                    child.get("id", "?"), state))
    if not parent.get("integration_proof"):
        violations.append(
            "parent close refused: child counts alone never "
            "close a parent; parent integration proof required")
    return violations


def check_duplicate_noop(first: Any, replay: Any) -> List[str]:
    """Return violations when a replay double-effects.

    Duplicate close/receipt events are idempotent no-ops:
    replaying the same event never double-counts, re-closes, or
    re-effects. A count delta or a second effect on replay
    fails.
    """
    violations: List[str] = []
    if not isinstance(first, dict) or not isinstance(replay, dict):
        return ["receipt events must be mappings"]
    if replay.get("count_delta", 0) != 0:
        violations.append(
            "duplicate replay double-counts: delta %r (want 0)"
            % (replay.get("count_delta"),))
    if replay.get("second_effect"):
        violations.append(
            "duplicate replay re-effects: idempotent no-op "
            "required")
    return violations


def check_membership_race(close: Any) -> List[str]:
    """Return violations when a race is silently swallowed.

    A child added to (or a receipt racing) a parent's required
    set at close time makes the close refuse and re-evaluate —
    never silently succeed.
    """
    violations: List[str] = []
    if not isinstance(close, dict):
        return ["close record must be a mapping"]
    if close.get("membership_changed") and close.get(
            "outcome") == "closed":
        violations.append(
            "membership race silently succeeded: close must "
            "refuse and re-evaluate")
    if close.get("membership_changed") and close.get(
            "outcome") not in ("refused", "re-evaluate", "closed"):
        violations.append(
            "race outcome %r is not a visible refuse/re-evaluate"
            % (close.get("outcome"),))
    return violations


def check_tracker_math(counts: Any) -> List[str]:
    """Return violations for wrong #197 tracker math.

    Completed/total updates come only from merged-child
    receipts; owner-excluded with rationale is never delivered;
    a deliberately wrong count is rejected naming the delta.
    """
    violations: List[str] = []
    if not isinstance(counts, dict):
        return ["tracker counts must be a mapping"]
    receipts = counts.get("merged_child_receipts", 0)
    completed = counts.get("completed", 0)
    excluded = counts.get("excluded", 0)
    if completed != receipts:
        violations.append(
            "tracker math wrong: completed %r != merged-child "
            "receipts %r" % (completed, receipts))
    if counts.get("counts_excluded_delivered"):
        violations.append(
            "tracker counts excluded as delivered: excluded is "
            "never delivered")
    _ = excluded
    return violations


def validate_receipt_corpus(corpus: Any) -> Tuple[List[str], List[Any]]:
    """Validate the frozen completion-receipt fixture oracle.

    Returns (findings, entries). Every entry carries an id, a
    target surface (merged, cleaned, exclusion, parent,
    duplicate, race, tracker), a record, and the expected
    violation fragment ("" means clean).
    """
    if not isinstance(corpus, dict):
        return (["receipt corpus must be a mapping"], [])
    if corpus.get("_frozen") is not True:
        return (["receipt corpus is not frozen: set "
                 "\"_frozen\": true"], [])
    entries = corpus.get("entries")
    if not isinstance(entries, list):
        return (["receipt corpus entries must be a list"], [])
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
        if target == "merged":
            violations = check_merged_receipt(record)
        elif target == "cleaned":
            violations = check_cleaned_receipt(
                record, entry.get("cleanup_receipt"))
        elif target == "exclusion":
            violations = check_exclusion(record)
        elif target == "parent":
            violations = check_parent_gate(record)
        elif target == "duplicate":
            violations = check_duplicate_noop(
                record, entry.get("replay", {}))
        elif target == "race":
            violations = check_membership_race(record)
        elif target == "tracker":
            violations = check_tracker_math(record)
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
