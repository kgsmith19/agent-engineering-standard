"""T13 Standard half: resource readiness gate with four distinct modes.

Readiness distinguishes four failure modes with no overlap: denied
access to an existing resource (denied-access), a run from the wrong
working directory (wrong-directory, expected vs actual named),
a reference to a nonexistent fixture/input (missing-fixture), and
an invocation of an absent command (unavailable-command). Where the
plan declares an optional tool with a supported alternative, the
presence of the alternative satisfies readiness. A readiness proof
that performs no check (empty/no-op) is rejected. The path never
reads secret values or provisions credentials, and it extends the
existing ready/readiness receipt shape — never a second Ready gate.

Pure functions: no I/O, no network — data in, verdicts out. Frozen
rules, stable output order.
"""

from typing import Any, Dict, List, Optional, Tuple

# The four distinct readiness modes. Each verdict names exactly one.
READINESS_MODES = (
    "denied-access",
    "wrong-directory",
    "missing-fixture",
    "unavailable-command",
)


def check_resource(resource: Any) -> List[str]:
    """Return verdicts for one resource probe; empty = ready.

    Exactly one mode fires per probe: denied access to an existing
    resource reports denied-access only; a missing resource reports
    missing-fixture only (never denied-access); the two never
    overlap, so triage routes to exactly one remediation.
    """
    if not isinstance(resource, dict):
        return ["missing-fixture: probe must be a mapping"]
    exists = resource.get("exists", True)
    accessible = resource.get("accessible", True)
    if not exists:
        return ["missing-fixture: %r does not exist" % (
            resource.get("name", "?"),)]
    if not accessible:
        return ["denied-access: %r exists but access is denied" % (
            resource.get("name", "?"),)]
    return []


def check_directory(actual: Any, expected: Any) -> List[str]:
    """Return verdicts for one working-directory probe.

    A run from the wrong directory reports wrong-directory with
    both expected and actual named, distinct from the other three
    modes. A match returns [].
    """
    if str(actual) != str(expected):
        return ["wrong-directory: expected %r, actual %r" % (
            expected, actual)]
    return []


def check_command(command: Any, available: Any) -> List[str]:
    """Return verdicts for one command-availability probe.

    An absent command reports unavailable-command naming the
    command, distinct from the other three modes. A present
    command returns [].
    """
    commands = set(available) if isinstance(available, list) else set()
    if str(command) not in commands:
        return ["unavailable-command: %r is not installed" % (
            command,)]
    return []


def check_optional_alternative(tool: Any, alternatives: Any,
                               present: Any) -> List[str]:
    """Return verdicts for one optional-tool probe.

    Where the plan declares an optional tool with a supported
    alternative, the presence of the alternative satisfies
    readiness (no failure recorded). An optional tool with
    neither itself nor any alternative present reports
    unavailable-command for the tool.
    """
    if not isinstance(alternatives, list):
        alternatives = []
    have = set(present) if isinstance(present, list) else set()
    if str(tool) in have:
        return []
    for alternative in alternatives:
        if str(alternative) in have:
            return []
    return ["unavailable-command: optional %r has no supported "
            "alternative present" % (tool,)]


def check_proof_performs(proof: Any) -> List[str]:
    """Return verdicts for one readiness proof record.

    A proof that performs no check (empty steps, zero probes, or
    an explicit no-op flag) is rejected: an empty proof never
    authorizes work.
    """
    if not isinstance(proof, dict):
        return ["no-op proof rejected: proof must be a mapping"]
    if proof.get("no_op") is True:
        return ["no-op proof rejected: the proof performs no check"]
    steps = proof.get("steps")
    if isinstance(steps, list) and not steps:
        return ["no-op proof rejected: the proof performs no check"]
    if not proof:
        return ["no-op proof rejected: the proof performs no check"]
    return []


def check_no_secrets(probe: Any) -> List[str]:
    """Return verdicts for secret handling in one probe record.

    The readiness path neither reads secret values nor provisions
    credentials: any probe carrying a secret value or a provision
    flag is rejected.
    """
    violations: List[str] = []
    if not isinstance(probe, dict):
        return []
    for key in ("secret_value", "token", "credential",
                "provision_credentials"):
        if probe.get(key):
            violations.append(
                "secret handling forbidden in readiness: %r must "
                "never be read or provisioned here" % (key,))
    return violations


def validate_readiness_corpus(corpus: Any) -> Tuple[List[str], List[Any]]:
    """Validate the frozen readiness fixture oracle.

    Returns (findings, entries). Every entry carries an id, a
    target surface (resource, directory, command, alternative,
    proof, secrets), a record, and the expected violation
    fragment ("" means ready/clean).
    """
    if not isinstance(corpus, dict):
        return (["readiness corpus must be a mapping"], [])
    if corpus.get("_frozen") is not True:
        return (["readiness corpus is not frozen: set "
                 "\"_frozen\": true"], [])
    entries = corpus.get("entries")
    if not isinstance(entries, list):
        return (["readiness corpus entries must be a list"], [])
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
        if target == "resource":
            violations = check_resource(record)
        elif target == "directory":
            violations = check_directory(
                (record or {}).get("actual"),
                (record or {}).get("expected"))
        elif target == "command":
            violations = check_command(
                (record or {}).get("command"),
                (record or {}).get("available", []))
        elif target == "alternative":
            violations = check_optional_alternative(
                (record or {}).get("tool"),
                (record or {}).get("alternatives", []),
                (record or {}).get("present", []))
        elif target == "proof":
            violations = check_proof_performs(record)
        elif target == "secrets":
            violations = check_no_secrets(record)
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
