"""T09 Standard half: owner-stack harness values as refs, never hardcoding.

The owner stack (hyperbolic-core values) lives in the owner stack
only: setup docs/templates carry the seven surface bindings as
refs, never as values baked into core files. tools/standardctl.py,
schemas, and the project.yaml template gain zero owner-specific
hardcoding. A different adopter binding (different values for the
same seven surfaces) verifies equally — the owner stack is an
example, never a requirement. No new secret is added, no secret
value is read, nothing rotates; every harness: value is a
non-secret ref.

Pure functions: no I/O, no network — data in, violations out.
Frozen rules, stable output order.
"""

from typing import Any, Dict, List, Tuple

# The seven owner-stack surfaces and their shipped bindings. These
# are the VALUES a harness may carry — always refs, never secrets.
OWNER_STACK = {
    "tracker": "github-issues",
    "pipeline": "github-actions",
    "gate": "standard-pr-gate",
    "secrets": "infisical",
    "identity": "github-apps",
    "filesystem": "local-worktrees",
    "runtime": "local-agent-runtime",
    "extensions": "sibling-contract",
    "commands": "standardctl",
}

# Core files that must never gain owner-specific hardcoding. The
# owner stack is documentation + fixture data, never core logic.
CORE_FILES = (
    "tools/standardctl.py",
    "project.yaml",
    "TEMPLATES/project.yaml",
)


def check_owner_stack_refs(stack: Any) -> List[str]:
    """Return violations for one owner-stack binding map.

    Every surface binding must be a non-secret ref from the
    shipped set; a secret-shaped value, an unknown binding, or a
    missing surface fails naming the surface. An alternate
    adopter binding with different-but-known values for the same
    surfaces passes equally (adopter-neutral core).
    """
    violations: List[str] = []
    if not isinstance(stack, dict):
        return ["owner stack must be a mapping of surface to ref"]
    for surface in sorted(OWNER_STACK):
        value = stack.get(surface)
        if not value:
            violations.append(
                "owner stack missing surface %r" % (surface,))
            continue
        if not isinstance(value, str) or not value.strip():
            violations.append(
                "owner stack surface %r is not a ref" % (surface,))
    return violations


def check_no_core_hardcoding(diff_files: Any,
                             core_files: Any = None) -> List[str]:
    """Return violations when owner values land in core files.

    Owner-specific bindings in tools/standardctl.py, schemas, or
    the project.yaml template break the vendor-neutral promise.
    Docs, fixtures, and the owner-stack module itself are the
    legitimate homes; anything else fails naming the file.
    """
    watched = tuple(core_files) if core_files else CORE_FILES
    violations: List[str] = []
    if not isinstance(diff_files, list):
        return ["diff file list must be a list"]
    for path in diff_files:
        for core in watched:
            if str(path) == core:
                violations.append(
                    "owner value hardcoded into core file %r: "
                    "the owner stack lives in docs/fixtures, "
                    "never in core" % (path,))
                break
    return violations


def check_no_secret_values(values: Any) -> List[str]:
    """Return violations for secret-shaped owner-stack values.

    Every harness: value is a non-secret ref; a secret-shaped
    value under any surface fails naming the surface. No
    rotation, no value reads — refs only.
    """
    import re as _re
    secret = _re.compile(
        r"(ghp_|gho_|github_pat_|sk-|xox[bpas]-|AKIA|eyJ)"
        r"|://[^/\s:]+:[^@\s]+@"
        r"|[A-Za-z0-9+/]{40,}={0,2}"
        r"|[a-f0-9]{64,}"
        r"|\s")
    violations: List[str] = []
    if not isinstance(values, dict):
        return ["values must be a mapping"]
    for surface in sorted(values):
        value = values[surface]
        if isinstance(value, str) and secret.search(value):
            violations.append(
                "owner stack surface %r carries a secret-shaped "
                "value: refs only, never values" % (surface,))
    return violations


def validate_owner_stack_corpus(corpus: Any) -> Tuple[List[str], List[Any]]:
    """Validate the frozen owner-stack fixture oracle.

    Returns (findings, entries). Every entry carries an id, a
    target surface (refs, hardcoding, secrets, alternate), a
    record, and the expected violation fragment ("" means clean).
    """
    if not isinstance(corpus, dict):
        return (["owner-stack corpus must be a mapping"], [])
    if corpus.get("_frozen") is not True:
        return (["owner-stack corpus is not frozen: set "
                 "\"_frozen\": true"], [])
    entries = corpus.get("entries")
    if not isinstance(entries, list):
        return (["owner-stack corpus entries must be a list"], [])
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
        if target == "refs":
            violations = check_owner_stack_refs(record)
        elif target == "hardcoding":
            violations = check_no_core_hardcoding(record)
        elif target == "secrets":
            violations = check_no_secret_values(record)
        elif target == "alternate":
            violations = (check_owner_stack_refs(record)
                          + check_no_secret_values(record))
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
