"""T07 Standard half: extensions registry validation with native-link supply.

Catalog/profile/lock validate as a consistent set: catalog entries,
profile selections, and the lock agree, and any mismatch fails
closed naming the inconsistent artifact. Provider capabilities
referenced by edition/flags selections must exist in the capability
registry; unknown or absent capabilities fail closed. The capability
registry declaration is published: the single generated source of
truth is Canonical/capabilities.json plus its schemas. Supply-side
configurability routes by link to the native agent-extensions
issue(s) — no supply-side implementation lands in this repo or
issue (sibling additive-only, EXT-006 hard gate). Absent
edition/flags/catalog usage validates exactly as today
(additive-only).

Pure functions: no I/O, no network — data in, violations out.
Frozen rules, stable output order.
"""

from typing import Any, Dict, List, Set, Tuple

# Reserved top-level project.yaml keys (Q8): never schema keys.
RESERVED_KEYS = ("adapters", "profile")

# Registry triple: catalog entries, profile selections, lock pins
# must agree as a set.
REGISTRY_REQUIRED = ("catalog", "profile", "lock")


def check_registry_set(registry: Any) -> List[str]:
    """Return violations for one catalog/profile/lock triple.

    Every profile selection must name a catalog entry, and every
    profile selection must carry a lock pin (the lock agrees with
    the profile). A profile selecting a missing catalog entry, a
    selection missing from the lock, or a lock pin for an
    unselected entry fails closed naming the mismatch. Unknown
    top-level keys fail closed.
    """
    violations: List[str] = []
    if not isinstance(registry, dict):
        return ["registry record must be a mapping"]
    for key in sorted(registry):
        if key not in REGISTRY_REQUIRED:
            violations.append(
                "unknown registry key %r: catalog/profile/lock only"
                % (key,))
    catalog = registry.get("catalog")
    profile = registry.get("profile")
    lock = registry.get("lock")
    if not isinstance(catalog, list):
        return violations + ["catalog must be a list of entries"]
    if not isinstance(profile, list):
        return violations + ["profile must be a list of selections"]
    if not isinstance(lock, dict):
        return violations + ["lock must be a mapping of pins"]
    catalog_ids = {str(entry.get("id", "")) for entry in catalog
                   if isinstance(entry, dict)}
    for selection in profile:
        name = str(selection)
        if name not in catalog_ids:
            violations.append(
                "profile selects %r missing from the catalog: "
                "catalog/profile/lock mismatch" % (name,))
        if name not in lock:
            violations.append(
                "profile selects %r missing from the lock: "
                "catalog/profile/lock mismatch" % (name,))
    for pinned in sorted(lock):
        if pinned not in {str(selection) for selection in profile}:
            violations.append(
                "lock pins %r with no profile selection: "
                "catalog/profile/lock mismatch" % (pinned,))
    return violations


def check_capability_exists(selection: Any,
                            registry: Any) -> List[str]:
    """Return violations for one edition/flags capability selection.

    Every referenced provider capability must exist in the
    capability registry (a set of declared capability IDs). An
    unknown or absent capability fails closed naming the missing
    ID (consistent with #199 AC3).
    """
    violations: List[str] = []
    if not isinstance(selection, dict):
        return ["capability selection must be a mapping"]
    declared: Set[str] = set()
    if isinstance(registry, (list, set, tuple)):
        declared = {str(item) for item in registry}
    elif isinstance(registry, dict):
        declared = {str(key) for key in registry}
    for key in sorted(selection):
        for capability in selection[key] if isinstance(
                selection[key], list) else [selection[key]]:
            if str(capability) not in declared:
                violations.append(
                    "edition/flag %r references unknown capability "
                    "%r: it must exist in the capability registry"
                    % (key, capability))
    return violations


def check_reserved_keys(config: Any) -> List[str]:
    """Return violations for reserved project.yaml keys (Q8).

    adapters: and profile: stay reserved for a later stage; any use
    fails closed naming the reserved key.
    """
    violations: List[str] = []
    if not isinstance(config, dict):
        return ["config must be a mapping"]
    for key in RESERVED_KEYS:
        if key in config:
            violations.append(
                "reserved key %r is not a schema key; it is held "
                "for a later stage (Q8)" % (key,))
    return violations


def check_supply_boundary(diff_files: Any) -> List[str]:
    """Return violations when supply-side files land in this repo.

    Supply-side configurability is owned by the linked native
    agent-extensions issue(s); any supply-side implementation file
    (extension source, adapter implementation, or rewrite of the
    sibling contract) in this repo's diff fails review.
    """
    violations: List[str] = []
    if not isinstance(diff_files, list):
        return ["diff file list must be a list"]
    supply_markers = ("extensions/adapters/", "extensions/supply/",
                      "Canonical/sibling-contract.json")
    for path in diff_files:
        for marker in supply_markers:
            if str(path).startswith(marker):
                violations.append(
                    "supply-side file %r belongs in the linked "
                    "native agent-extensions issue, not this repo"
                    % (path,))
                break
    return violations


def validate_registry_corpus(corpus: Any) -> Tuple[List[str], List[Any]]:
    """Validate the frozen extensions-registry fixture oracle.

    Returns (findings, entries). Every entry carries an id, a
    target surface (set, capability, reserved, supply, keyless), a
    record, and the expected violation fragment ("" means clean).
    Capability entries carry a registry list alongside the record.
    """
    if not isinstance(corpus, dict):
        return (["registry corpus must be a mapping"], [])
    if corpus.get("_frozen") is not True:
        return (["registry corpus is not frozen: set "
                 "\"_frozen\": true"], [])
    entries = corpus.get("entries")
    if not isinstance(entries, list):
        return (["registry corpus entries must be a list"], [])
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
        if target == "set":
            violations = check_registry_set(record)
        elif target == "capability":
            violations = check_capability_exists(
                record, entry.get("registry", []))
        elif target == "reserved":
            violations = check_reserved_keys(record)
        elif target == "supply":
            violations = check_supply_boundary(record)
        elif target == "keyless":
            violations = (check_registry_set(record)
                          + check_reserved_keys(record))
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


def clean_triple() -> Dict[str, Any]:
    """One consistent catalog/profile/lock triple."""
    return {
        "catalog": [{"id": "lint-pack"}, {"id": "review-pack"}],
        "profile": ["lint-pack"],
        "lock": {"lint-pack": "1.0.0"},
    }
