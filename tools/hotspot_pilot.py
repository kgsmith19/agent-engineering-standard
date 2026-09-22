"""T16 Standard half: single measured hotspot pilot.

The single hotspot (location + scope boundaries) is declared
before any measurement; measuring an undeclared area fails the
proof. Read/edit/impact scopes (T12 vocabulary) are recorded
before the run; out-of-scope edits during the pilot fail it.
Shared contracts, schemas, and Molds stay byte-identical before
and after (frozen-Mold receipt); any contract change fails the
pilot. Both measurements start cold (no warm cache/state) on
matched #212-baseline tasks with repeats; total effort is
recorded on both sides. A no-benefit result is NO_CHANGE with
data — never re-run, never massaged. Nothing outside the
declared scope carries the pilot change (repo-wide copy fails).

Pure functions: no I/O, no network — data in, violations out.
Frozen rules, stable output order.
"""

from typing import Any, Dict, List, Optional, Tuple

# Pilot legs: declared scope, frozen contracts, cold matched
# measurement, honest verdict, contained change.
PILOT_REQUIRED = ("hotspot", "scopes", "contracts_frozen",
                  "cold", "verdict", "contained")


def check_hotspot_declared(pilot: Any) -> List[str]:
    """Return violations when measurement precedes declaration.

    The hotspot location + scope boundaries are named before any
    measurement; a pilot measuring an undeclared area fails
    naming the area.
    """
    violations: List[str] = []
    if not isinstance(pilot, dict):
        return ["pilot record must be a mapping"]
    if not pilot.get("hotspot"):
        return ["hotspot not declared: name location + scope "
                "boundaries before measuring"]
    measured = pilot.get("measured") or []
    scope = pilot.get("scope") or []
    for area in measured:
        if area not in scope and area != pilot.get("hotspot"):
            violations.append(
                "undeclared area measured: %r is outside the "
                "declared hotspot scope" % (area,))
    return violations


def check_scope_containment(pilot: Any) -> List[str]:
    """Return violations for out-of-scope pilot edits.

    Read/edit/impact scopes are recorded before the run; any edit
    outside the declared edit scope fails naming the edit.
    """
    violations: List[str] = []
    if not isinstance(pilot, dict):
        return ["pilot record must be a mapping"]
    allowed = pilot.get("edit_scope") or []
    for edit in pilot.get("edits") or []:
        if edit not in allowed:
            violations.append(
                "out-of-scope edit during pilot: %r is outside "
                "the recorded edit scope" % (edit,))
    if not allowed and (pilot.get("edits") or []):
        violations.append(
            "pilot records no edit scope (T12 vocabulary "
            "required before the run)")
    return violations


def check_contracts_frozen(before: Any, after: Any) -> List[str]:
    """Return violations when the pilot moves shared contracts.

    Shared contracts, schemas, and Molds are byte-identical
    before and after (frozen-Mold receipt); any drift fails
    naming the contract — benefit may never come from a moved
    contract.
    """
    violations: List[str] = []
    if not isinstance(before, dict) or not isinstance(after, dict):
        return ["contract snapshots must be mappings"]
    for name in sorted(set(list(before) + list(after))):
        if before.get(name) != after.get(name):
            violations.append(
                "contract drift during pilot: %r changed "
                "(frozen-Mold receipt broken)" % (name,))
    return violations


def check_cold_matched(measurement: Any) -> List[str]:
    """Return violations for warm or unmatched measurement.

    Both legs start cold (no warm cache/state) on matched
    baseline tasks with repeats; a warm leg, an unmatched task
    set, or zero repeats fails naming the flaw. Total effort is
    recorded on both sides.
    """
    violations: List[str] = []
    if not isinstance(measurement, dict):
        return ["measurement must be a mapping"]
    for leg in ("before", "after"):
        side = measurement.get(leg)
        if not isinstance(side, dict):
            violations.append("measurement missing %r leg" % (leg,))
            continue
        if side.get("warm"):
            violations.append(
                "warm-cache %r leg: cold start required" % (leg,))
        if not side.get("matched_tasks"):
            violations.append(
                "%r leg has no matched baseline tasks" % (leg,))
        if not side.get("repeats"):
            violations.append(
                "%r leg records no repeats" % (leg,))
        if not side.get("total_effort"):
            violations.append(
                "%r leg records no total effort" % (leg,))
    before = measurement.get("before") or {}
    after = measurement.get("after") or {}
    if (isinstance(before, dict) and isinstance(after, dict)
            and before.get("matched_tasks") and after.get(
                "matched_tasks")
            and before.get("matched_tasks") != after.get(
                "matched_tasks")):
        violations.append(
            "unmatched before/after task sets: matched tasks "
            "required on both sides")
    return violations


def check_honest_verdict(pilot: Any) -> List[str]:
    """Return violations for a massaged or suppressed verdict.

    NO_CHANGE with data is a complete outcome; a re-run-until-
    green flag, a missing-data NO_CHANGE, or a suppressed
    verdict fails naming the honesty break.
    """
    violations: List[str] = []
    if not isinstance(pilot, dict):
        return ["pilot record must be a mapping"]
    if pilot.get("rerun_until_green"):
        violations.append(
            "re-run until green forbidden: NO_CHANGE with data "
            "is a complete outcome")
    verdict = pilot.get("verdict")
    if verdict == "NO_CHANGE" and not pilot.get("data"):
        violations.append(
            "NO_CHANGE without data: record the measurement")
    if verdict not in ("IMPROVED", "NO_CHANGE", "REGRESSED", None):
        violations.append("unknown pilot verdict %r" % (verdict,))
    return violations


def check_containment(pilot: Any) -> List[str]:
    """Return violations when the pilot change escapes its scope.

    No file outside the declared hotspot scope carries the
    change; a repo-wide-copy fixture (the change applied
    elsewhere) fails naming the escape.
    """
    violations: List[str] = []
    if not isinstance(pilot, dict):
        return ["pilot record must be a mapping"]
    scope = pilot.get("scope") or []
    for path in pilot.get("changed_files") or []:
        if path not in scope and not any(
                str(path).startswith(str(root)) for root in scope):
            violations.append(
                "pilot change escaped scope: %r is outside the "
                "declared hotspot" % (path,))
    return violations


def validate_pilot_corpus(corpus: Any) -> Tuple[List[str], List[Any]]:
    """Validate the frozen hotspot-pilot fixture oracle.

    Returns (findings, entries). Every entry carries an id, a
    target surface (hotspot, scope, contracts, cold, verdict,
    containment), a record (plus after for contracts), and the
    expected violation fragment ("" means clean).
    """
    if not isinstance(corpus, dict):
        return (["pilot corpus must be a mapping"], [])
    if corpus.get("_frozen") is not True:
        return (["pilot corpus is not frozen: set "
                 "\"_frozen\": true"], [])
    entries = corpus.get("entries")
    if not isinstance(entries, list):
        return (["pilot corpus entries must be a list"], [])
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
        if target == "hotspot":
            violations = check_hotspot_declared(record)
        elif target == "scope":
            violations = check_scope_containment(record)
        elif target == "contracts":
            violations = check_contracts_frozen(
                record, entry.get("after", {}))
        elif target == "cold":
            violations = check_cold_matched(record)
        elif target == "verdict":
            violations = check_honest_verdict(record)
        elif target == "containment":
            violations = check_containment(record)
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


def clean_pilot() -> Dict[str, Any]:
    """One fully-declared, cold, matched, contained pilot."""
    scope = ["tools/hotspot.py"]
    leg = {"warm": False, "matched_tasks": ["task-local"],
           "repeats": 3, "total_effort": "4h"}
    return {
        "hotspot": "tools/hotspot.py",
        "scope": list(scope),
        "measured": ["tools/hotspot.py"],
        "edit_scope": list(scope),
        "edits": ["tools/hotspot.py"],
        "contracts_before": {"mold-v1": "abc"},
        "contracts_after": {"mold-v1": "abc"},
        "measurement": {"before": dict(leg), "after": dict(leg)},
        "verdict": "NO_CHANGE",
        "data": "before=4h after=4h, no significant benefit",
        "changed_files": ["tools/hotspot.py"],
    }
