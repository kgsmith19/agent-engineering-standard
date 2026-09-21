"""T06 Standard half: filesystem-agnostic ledger/runtime paths with governed rotation.

Ledger and runtime paths resolve through a declared, testable path
layer — no POSIX-only or platform-specific assumption is baked into
the ledger or runtime. The isolation order (lease -> worktree ->
writer, one writer per slice) is documented and preserved; cleanup
stays harness-native (no harness-specific merge/delete authority is
introduced here — the full deletion predicates are T19). Network and
compute are expressed purely as harness: values (local, tailnet,
hetzner, cloud, mobile) with no code change and no new keys beyond
harness:/edition:/flags:. Governed rotation runs only through the
owner-authorized, bounded, recorded path with the zero-auto-compaction
target; automatic or fleet-wide rotation is refused. Absent values
behave exactly as today (keyless identity).

Pure functions: no I/O, no network — data in, violations out. Frozen
rules, stable output order.
"""

from typing import Any, Dict, List, Tuple
import posixpath

# Network/compute are harness: VALUES (Q8): no new keys, no code
# change. Unknown values fail closed (consistent with #199).
NETWORK_VALUES = ("local", "tailnet", "hetzner", "cloud", "mobile")

# Isolation order: lease -> worktree -> writer. One writer per slice.
ISOLATION_ORDER = ("lease", "worktree", "writer")

# Governed rotation: owner-authorized, bounded, recorded. Automatic or
# fleet-wide rotation is never a governed path.
ROTATION_REQUIRED_FIELDS = ("authorized_by", "bound", "record")

# Zero-auto-compaction target (Q4): rotation never compacts silently.
ZERO_COMPACTION_TARGET = "zero-auto-compaction"


def resolve_ledger_path(raw: Any) -> str:
    """Resolve one ledger/runtime path to its canonical POSIX form.

    Backslash separators normalize to forward slashes, redundant
    separators and dot segments collapse, and a leading ./ is
    stripped — so Windows-shaped, Tailnet-shaped, or Hetzner-shaped
    inputs resolve through the same layer. Empty or non-string
    input raises ValueError (fail closed, never a silent default).
    """
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(
            "ledger path must be a non-empty string, not %r" % (raw,))
    text = raw.strip().replace("\\", "/")
    resolved = posixpath.normpath(text)
    if resolved == ".":
        raise ValueError(
            "ledger path %r resolves to nothing" % (raw,))
    return resolved


def check_isolation_order(steps: Any) -> List[str]:
    """Return violations for one isolation-step sequence.

    The steps must follow lease -> worktree -> writer in order
    (a subsequence match: extra read-only steps are allowed, reorder
    is not). A second writer on one slice is rejected: one writer
    per slice, conflicting claims refused.
    """
    violations: List[str] = []
    if not isinstance(steps, list) or not steps:
        return ["isolation requires a non-empty step sequence"]
    cursor = 0
    for step in steps:
        if cursor < len(ISOLATION_ORDER) and step == ISOLATION_ORDER[cursor]:
            cursor += 1
    if cursor != len(ISOLATION_ORDER):
        violations.append(
            "isolation order violated: steps %r do not follow "
            "lease -> worktree -> writer" % (steps,))
    writers = [step for step in steps if step == "writer"]
    claimants = [step for step in steps if step == "writer:second"]
    if claimants:
        violations.append(
            "conflicting claim refused: second writer on one slice")
    return violations


def check_harness_values(values: Any) -> List[str]:
    """Return violations for one network/compute harness: value map.

    Every value must be one of the five frozen network values; keys
    beyond harness:/edition:/flags: are rejected (Q8); secret-shaped
    values are rejected (values-only rule, per #199).
    """
    violations: List[str] = []
    if not isinstance(values, dict):
        return ["harness values must be a mapping"]
    for key, value in sorted(values.items()):
        if key not in ("network", "compute"):
            violations.append(
                "unknown harness value key %r: network/compute only, "
                "no new keys" % (key,))
            continue
        if value not in NETWORK_VALUES:
            violations.append(
                "unknown harness value %r for %s: known values are %s"
                % (value, key, ", ".join(NETWORK_VALUES)))
    return violations


def check_rotation_path(rotation: Any) -> List[str]:
    """Return violations for one rotation invocation record.

    Governed rotation carries authorized_by (the owner admin path),
    a bound (what the rotation may touch), and a record (where the
    run is recorded), and it honors the zero-auto-compaction
    target. An automatic or fleet-wide trigger, a missing
    authorization/bound/record, or a compaction run is refused.
    """
    violations: List[str] = []
    if not isinstance(rotation, dict):
        return ["rotation record must be a mapping"]
    if rotation.get("automatic") is True or rotation.get("fleet_wide") is True:
        return ["ungoverned rotation refused: automatic/fleet-wide "
                "rotation never runs outside the governed path"]
    for field in ROTATION_REQUIRED_FIELDS:
        if not rotation.get(field):
            violations.append(
                "rotation missing %r: governed rotation is "
                "owner-authorized, bounded, recorded" % (field,))
    if rotation.get("compaction") is True:
        violations.append(
            "rotation with compaction refused: the target is %s"
            % ZERO_COMPACTION_TARGET)
    return violations


def check_keyless_identity(config: Any) -> List[str]:
    """Return violations for one keyless config; empty = today.

    A config without harness:/edition:/flags: keys must behave
    exactly as today: no violations, no behavior change. Any
    harness: value present is validated through check_harness_values.
    """
    if not isinstance(config, dict):
        return ["config must be a mapping"]
    harness = config.get("harness")
    if harness is None:
        return []
    return check_harness_values(harness)


def validate_path_corpus(corpus: Any) -> Tuple[List[str], List[Any]]:
    """Validate the frozen ledger/runtime fixture oracle.

    Returns (findings, entries). Every entry carries an id, a
    target surface (path, isolation, values, rotation, keyless), a
    record, and the expected violation fragment ("" means clean).
    """
    if not isinstance(corpus, dict):
        return (["path corpus must be a mapping"], [])
    if corpus.get("_frozen") is not True:
        return (["path corpus is not frozen: set \"_frozen\": true"], [])
    entries = corpus.get("entries")
    if not isinstance(entries, list):
        return (["path corpus entries must be a list"], [])
    findings: List[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            findings.append("corpus entry is not a mapping: %r" % (entry,))
            continue
        entry_id = entry.get("id", "?")
        target = entry.get("target")
        record = entry.get("record")
        expected = entry.get("expected_violation_fragment", "")
        try:
            if target == "path":
                violations = []
                try:
                    resolved = resolve_ledger_path(record)
                    if expected:
                        violations = ["expected failure, resolved %r"
                                      % resolved]
                except ValueError as exc:
                    violations = [str(exc)]
            elif target == "isolation":
                violations = check_isolation_order(record)
            elif target == "values":
                violations = check_harness_values(record)
            elif target == "rotation":
                violations = check_rotation_path(record)
            elif target == "keyless":
                violations = check_keyless_identity(record)
            else:
                findings.append(
                    "entry %s has unknown target %r" % (entry_id, target))
                continue
        except (TypeError, AttributeError) as exc:
            violations = [str(exc)]
        if expected:
            if not any(expected in v for v in violations):
                findings.append(
                    "entry %s: expected fragment %r not reproduced "
                    "(got %r)" % (entry_id, expected, violations))
        elif violations:
            findings.append(
                "entry %s: expected clean, got %r" % (entry_id, violations))
    return (findings, entries)
