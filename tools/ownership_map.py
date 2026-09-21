"""T12 Standard half: declarative ownership map with read/edit/impact scopes.

Every repository root is mapped with declared read scope, edit
scope, and impact scope plus roots/interfaces/direction/commands
metadata. Legitimate multi-root ownership is supported when
declared (ALA-01+02, both IDs retained); undeclared sprawl is
flagged. Touches to the five invariant classes (shared schema,
global state, dynamic wiring, external consumer, security) widen
the required verification scope beyond the local slice. A stale map
entry (edit scope no longer matching reality) fails; a write
outside the touched root's declared edit scope is blocked. The map
is declarative metadata consumed by the verification scoping path —
never a second tracker or workflow system.

Pure functions: no I/O, no network — data in, violations out.
Frozen rules, stable output order.
"""

from typing import Any, Dict, List, Optional, Set, Tuple

# Five invariant classes that force wider verification.
INVARIANT_CLASSES = (
    "shared-schema",
    "global-state",
    "dynamic-wiring",
    "external-consumer",
    "security",
)

# Map entry metadata: every entry records these four fields.
ENTRY_METADATA = ("roots", "interfaces", "direction", "commands")

# Scope kinds declared per root.
SCOPE_KINDS = ("read", "edit", "impact")


def check_map_coverage(tree_roots: Any, entries: Any) -> List[str]:
    """Return violations for map-vs-tree coverage.

    Every root in the tree must appear in the map's entries; an
    unmapped root fails naming the root, so no edit lands on
    unowned ground.
    """
    violations: List[str] = []
    if not isinstance(tree_roots, list):
        return ["tree roots must be a list"]
    if not isinstance(entries, dict):
        return ["map entries must be a mapping of root to entry"]
    for root in tree_roots:
        if str(root) not in entries:
            violations.append(
                "unmapped root %r: every repository root needs "
                "declared read/edit/impact scopes" % (root,))
    return violations


def check_entry_metadata(entry: Any) -> List[str]:
    """Return violations for one map entry's metadata completeness.

    Each entry records roots, interfaces, direction (who
    reads/writes whom), and commands, plus read/edit/impact
    scopes. A missing field fails naming the field, so scope
    decisions never lack inputs.
    """
    violations: List[str] = []
    if not isinstance(entry, dict):
        return ["map entry must be a mapping"]
    for field in ENTRY_METADATA:
        if not entry.get(field):
            violations.append(
                "map entry missing %r: roots/interfaces/direction/"
                "commands are all required" % (field,))
    scopes = entry.get("scopes")
    if not isinstance(scopes, dict):
        return violations + ["map entry missing scopes mapping"]
    for kind in SCOPE_KINDS:
        if kind not in scopes:
            violations.append(
                "map entry missing %r scope: read/edit/impact all "
                "required" % (kind,))
    return violations


def check_multi_root(entries: Any) -> List[str]:
    """Return violations for undeclared multi-root sprawl.

    An owner spanning multiple roots is legitimate when every
    spanned root declares the shared owner (both ALA-01+02 IDs
    retained in the declaration). Edits spanning roots without
    that declaration are flagged as undeclared sprawl — except
    they are not a loophole: declaration never widens edit rights
    beyond the declared scopes.
    """
    violations: List[str] = []
    if not isinstance(entries, dict):
        return ["map entries must be a mapping of root to entry"]
    owner_roots: Dict[str, List[str]] = {}
    for root, entry in entries.items():
        if not isinstance(entry, dict):
            continue
        owner = entry.get("owner")
        if owner:
            owner_roots.setdefault(str(owner), []).append(str(root))
    declared = set()
    for owner, roots in owner_roots.items():
        if len(roots) > 1:
            declared.add(owner)
    for owner in sorted(declared):
        roots = owner_roots[owner]
        for root in roots:
            entry = entries[root]
            others = [r for r in roots if r != root]
            if not entry.get("multi_root_declared"):
                violations.append(
                    "undeclared sprawl: owner %r spans %s but %r "
                    "lacks the multi-root declaration" % (
                        owner, sorted(roots), root))
    return violations


def check_invariant_widening(touched: Any, entry: Any) -> List[str]:
    """Return the widened verification scope for one change.

    A change touching any invariant class (shared schema, global
    state, dynamic wiring, external consumer, security) widens the
    required verification scope beyond the local slice; the
    returned violation names the widening so the scoping path can
    enforce it. Local-only touches return [].
    """
    if not isinstance(touched, list):
        return ["touched invariants must be a list"]
    widened = [name for name in touched if name in INVARIANT_CLASSES]
    if not widened:
        return []
    return ["verification widens beyond the local slice: "
            "invariant touch %s" % sorted(widened)]


def check_stale_map(entry: Any, reality: Any) -> List[str]:
    """Return violations when the map no longer matches reality.

    The deliberately-stale canary: a map entry whose edit scope
    does not cover the paths the root actually owns fails naming
    the staleness, so a decorative-but-wrong map is never
    trusted.
    """
    violations: List[str] = []
    if not isinstance(entry, dict) or not isinstance(reality, dict):
        return ["stale-map check needs entry and reality mappings"]
    claimed = entry.get("edit_scope") or []
    actual = reality.get("owned_paths") or []
    for path in actual:
        if path not in claimed:
            violations.append(
                "stale map: root owns %r but the edit scope no "
                "longer covers it" % (path,))
    return violations


def check_protected_write(path: Any, entry: Any) -> List[str]:
    """Return violations for an out-of-scope write.

    A write to a path outside the touched root's declared edit
    scope is blocked; the violation names the path and the scope,
    so the protected-write canary proves enforcement.
    """
    if not isinstance(entry, dict):
        return ["map entry must be a mapping"]
    scope = entry.get("edit_scope") or []
    if path in scope:
        return []
    return ["protected write blocked: %r is outside the declared "
            "edit scope %r" % (path, sorted(scope))]


def validate_ownership_corpus(corpus: Any) -> Tuple[List[str], List[Any]]:
    """Validate the frozen ownership-map fixture oracle.

    Returns (findings, entries). Every entry carries an id, a
    target surface (coverage, metadata, multiroot, widening,
    stale, protected), a record (plus reality for stale, path for
    protected, touched for widening), and the expected violation
    fragment ("" means clean).
    """
    if not isinstance(corpus, dict):
        return (["ownership corpus must be a mapping"], [])
    if corpus.get("_frozen") is not True:
        return (["ownership corpus is not frozen: set "
                 "\"_frozen\": true"], [])
    entries = corpus.get("entries")
    if not isinstance(entries, list):
        return (["ownership corpus entries must be a list"], [])
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
        if target == "coverage":
            violations = check_map_coverage(
                record, entry.get("entries", {}))
        elif target == "metadata":
            violations = check_entry_metadata(record)
        elif target == "multiroot":
            violations = check_multi_root(record)
        elif target == "widening":
            violations = check_invariant_widening(record, {})
        elif target == "stale":
            violations = check_stale_map(
                record, entry.get("reality", {}))
        elif target == "protected":
            violations = check_protected_write(
                entry.get("path", ""), record)
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


def clean_entry(owner: str = "tools-owner") -> Dict[str, Any]:
    """One complete map entry (metadata + scopes + edit scope)."""
    return {
        "owner": owner,
        "roots": ["tools/"],
        "interfaces": ["standardctl verify"],
        "direction": "tools writes tools/",
        "commands": ["python tools/standardctl.py verify"],
        "scopes": {"read": ["tools/"], "edit": ["tools/a.py"],
                   "impact": ["tools/"]},
        "edit_scope": ["tools/a.py"],
    }
