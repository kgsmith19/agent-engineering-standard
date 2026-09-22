"""T14 Standard half: size/complexity profile with ratchet (pilot/advisory).

The profile triple-measures every scoped unit (source-LOC
post-format plus physical bytes plus complexity); a single
measure alone never decides. The ratchet blocks only new growth
(a change beyond its scope's recorded baseline fails; unrelated
legacy never fails because of this change). The builder cannot
self-exempt (exemptions need an owner identity distinct from the
builder); every exemption carries owner + reason + scope +
alternative + revisit; trusted exclusions (generated files) are
explicit and verified; file-split/reformat/complexity-hiding
dodge fixtures fail. Enforcement text waits for owner D2
approval — until then thresholds run pilot/advisory only — and
the joint amendment (#128 body + Prompt 37 + templates + adopter
text) lands atomically or not at all.

Pure functions: no I/O, no network — data in, violations out.
Frozen rules, stable output order.
"""

from typing import Any, Dict, List, Optional, Tuple

# Triple measure: post-format LOC + bytes + complexity. One
# measure alone never decides.
TRIPLE_MEASURES = ("loc_post_format", "bytes", "complexity")

# Exemption record: every field required.
EXEMPTION_FIELDS = ("owner", "reason", "scope", "alternative",
                    "revisit")


def check_triple_measure(profile: Any) -> List[str]:
    """Return violations when the profile is not triple-measured.

    Every scoped unit records all three measures; a profile
    using raw pre-format LOC only, or any single measure alone,
    fails naming the unit and the gap.
    """
    violations: List[str] = []
    if not isinstance(profile, dict):
        return ["profile must be a mapping of unit to measures"]
    for unit in sorted(profile):
        measures = profile[unit]
        if not isinstance(measures, dict):
            violations.append(
                "unit %r has no measure mapping" % (unit,))
            continue
        for measure in TRIPLE_MEASURES:
            if measures.get(measure) is None:
                violations.append(
                    "unit %r missing %r: triple measure required "
                    "(post-format LOC + bytes + complexity)"
                    % (unit, measure))
        if measures.get("loc_pre_format") is not None and not any(
                measures.get(measure) is not None
                for measure in TRIPLE_MEASURES):
            violations.append(
                "unit %r uses raw pre-format LOC only" % (unit,))
    return violations


def check_ratchet(change: Any, baseline: Any) -> List[str]:
    """Return violations for new growth beyond the baseline.

    A change increasing any triple measure beyond its scope's
    recorded baseline fails naming the growth; unchanged or
    shrinking scopes pass; scopes outside the change never fail
    (unrelated legacy is never blamed on this change).
    """
    violations: List[str] = []
    if not isinstance(change, dict) or not isinstance(baseline, dict):
        return ["change and baseline must be mappings"]
    scope = change.get("scope")
    if scope is None:
        return ["change names no scope"]
    if scope not in baseline:
        return ["change scope %r has no recorded baseline" % (
            scope,)]
    for measure in TRIPLE_MEASURES:
        before = (baseline[scope] or {}).get(measure)
        after = (change.get("measures") or {}).get(measure)
        if (isinstance(before, (int, float))
                and isinstance(after, (int, float))
                and after > before):
            violations.append(
                "ratchet: scope %r %s grew %r -> %r (new growth "
                "blocked)" % (scope, measure, before, after))
    return violations


def check_exemption_owner(exemption: Any, builder: Any) -> List[str]:
    """Return violations for self-exemptions.

    The builder cannot mark their own change exempt: the
    exemption owner must be present and distinct from the
    builder identity.
    """
    if not isinstance(exemption, dict):
        return ["exemption must be a mapping"]
    owner = exemption.get("owner")
    if not owner:
        return ["exemption names no owner: the builder cannot "
                "self-exempt"]
    if owner == builder:
        return ["self-exemption refused: owner %r == builder; an "
                "exemption needs an owner distinct from the "
                "builder" % (owner,)]
    return []


def check_exemption_record(exemption: Any) -> List[str]:
    """Return violations for incomplete exemption records.

    Every exemption carries owner + reason + scope +
    alternative considered + revisit date/condition; any missing
    field rejects the exemption naming the field.
    """
    violations: List[str] = []
    if not isinstance(exemption, dict):
        return ["exemption must be a mapping"]
    for field in EXEMPTION_FIELDS:
        if not exemption.get(field):
            violations.append(
                "exemption missing %r: owner + reason + scope + "
                "alternative + revisit all required" % (field,))
    return violations


def check_trusted_exclusions(paths: Any, trusted: Any) -> List[str]:
    """Return violations for unlisted exclusion claims.

    Trusted exclusions (generated files) are listed explicitly
    and verified; a path claiming exclusion without a listing
    fails naming the path.
    """
    violations: List[str] = []
    listed = set(trusted) if isinstance(trusted, list) else set()
    for path in (paths or []):
        if str(path).startswith("generated:"):
            claimed = str(path)[len("generated:"):]
            if claimed not in listed and path not in listed:
                violations.append(
                    "unlisted exclusion %r: trusted exclusions "
                    "are explicit and verified" % (path,))
    return violations


def check_anti_gaming(change: Any) -> List[str]:
    """Return violations for gaming fixtures.

    File-split-to-dodge, reformat-to-dodge, and
    complexity-hiding are detected: a change flagged with any
    dodge shape fails naming the dodge. Clean changes pass.
    """
    violations: List[str] = []
    if not isinstance(change, dict):
        return ["change must be a mapping"]
    for dodge in ("split_to_dodge", "reformat_to_dodge",
                  "complexity_hiding"):
        if change.get(dodge):
            violations.append(
                "anti-gaming: %r detected (triple measure + "
                "ratchet cannot be evaded)" % (dodge,))
    return violations


def check_d2_gate(enforcement: Any, d2_approved: bool) -> List[str]:
    """Return violations when enforcement precedes D2 approval.

    No enforcement text lands and no authoritative form is
    amended until owner D2 approval is recorded; before
    approval, thresholds run pilot/advisory only.
    """
    if enforcement and not d2_approved:
        return ["D2 gate: enforcement text waits for owner D2 "
                "approval (pilot/advisory only until then)"]
    return []


def check_joint_atomicity(parts: Any) -> List[str]:
    """Return violations for partial joint amendments.

    The #128 body + Prompt 37 + templates + adopter text amend
    together; amending only a subset fails naming the missing
    parts.
    """
    violations: List[str] = []
    required = ("issue_128", "prompt_37", "templates", "adopter")
    if not isinstance(parts, dict):
        return ["amendment parts must be a mapping"]
    missing = [part for part in required if not parts.get(part)]
    if missing and any(parts.get(part) for part in required):
        violations.append(
            "joint amendment partial: missing %s (amend together "
            "or not at all)" % ", ".join(sorted(missing)))
    return violations


def validate_profile_corpus(corpus: Any) -> Tuple[List[str], List[Any]]:
    """Validate the frozen size-profile fixture oracle.

    Returns (findings, entries). Every entry carries an id, a
    target surface (triple, ratchet, owner, record, exclusions,
    gaming, d2, joint), a record, and the expected violation
    fragment ("" means clean).
    """
    if not isinstance(corpus, dict):
        return (["profile corpus must be a mapping"], [])
    if corpus.get("_frozen") is not True:
        return (["profile corpus is not frozen: set "
                 "\"_frozen\": true"], [])
    entries = corpus.get("entries")
    if not isinstance(entries, list):
        return (["profile corpus entries must be a list"], [])
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
        if target == "triple":
            violations = check_triple_measure(record)
        elif target == "ratchet":
            violations = check_ratchet(
                record, entry.get("baseline", {}))
        elif target == "owner":
            violations = check_exemption_owner(
                record, entry.get("builder"))
        elif target == "record":
            violations = check_exemption_record(record)
        elif target == "exclusions":
            violations = check_trusted_exclusions(
                record, entry.get("trusted", []))
        elif target == "gaming":
            violations = check_anti_gaming(record)
        elif target == "d2":
            violations = check_d2_gate(
                record, entry.get("d2_approved", False))
        elif target == "joint":
            violations = check_joint_atomicity(record)
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


def clean_profile() -> Dict[str, Any]:
    """One triple-measured profile unit."""
    return {"tools/a.py": {"loc_post_format": 100, "bytes": 3000,
                           "complexity": 5}}
