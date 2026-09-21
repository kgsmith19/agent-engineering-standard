"""T08 Standard half: edition-aware standardctl UX with harness-aware doctor.

The edition UX rides on the frozen T02 schema: --edition selects
the run scope exactly as the edition: key would (absent flag = no
behavior change); --set harness.<surface>=<value> lands only as
config/binding values validated against the registry (unknown
surface/value fails closed); edition-scoped verify runs only
edition-selected checks within the current --select groups and
reports skipped-vs-passed distinctly. doctor --live stays
read-only by default (mutations need explicit --apply), reports
each surface binding status, and redacts secret-shaped values in
all output. Single-file stdlib-only is preserved; the lock is
still written LAST.

Pure functions: no I/O, no network — data in, verdicts out. The
CLI wiring calls into these helpers so tests pin the behavior
without subprocesses.
"""

import re
from typing import Any, Dict, List, Optional, Set, Tuple

# Secret-shaped values are redacted in ALL doctor output (AC4).
_SECRET_SHAPED_RE = re.compile(
    r"(ghp_|gho_|github_pat_|sk-|xox[bpas]-|AKIA|eyJ)"
    r"|://[^/\s:]+:[^@\s]+@"
    r"|[A-Za-z0-9+/]{40,}={0,2}"
    r"|[a-f0-9]{64,}"
    r"|\s"
)

REDACTED = "[redacted]"


def is_secret_shaped(value: Any) -> bool:
    """True when a value looks like a secret, never a ref."""
    if not isinstance(value, str):
        return False
    return bool(_SECRET_SHAPED_RE.search(value))


def redact_value(value: Any) -> Any:
    """Redact secret-shaped values; pass everything else through."""
    if is_secret_shaped(value):
        return REDACTED
    return value


def redact_mapping(mapping: Any) -> Dict[str, Any]:
    """Redact every secret-shaped leaf of a mapping (one level)."""
    if not isinstance(mapping, dict):
        return {}
    return {key: redact_value(value)
            for key, value in mapping.items()}


def parse_edition_arg(value: Any, editions: Any) -> List[str]:
    """Return violations for one --edition argument value.

    The value must name a known edition; unknown editions fail
    closed naming the value. Absent (None/"") yields [] so the
    flag-off path behaves exactly as today.
    """
    if value is None or str(value) == "":
        return []
    if str(value) not in set(editions):
        return ["unknown edition %r: must be one of %s" % (
            value, ", ".join(editions))]
    return []


def parse_harness_set(pair: Any, capabilities: Any) -> List[str]:
    """Return violations for one --set harness.<surface>=<value>.

    The pair must have the harness.<surface>=<value> shape with a
    known surface and a known binding value; secret-shaped values
    are rejected (refs only, never secrets). Unknown surfaces or
    values fail closed naming the key.
    """
    violations: List[str] = []
    if not isinstance(pair, str) or "=" not in pair:
        return ["--set expects harness.<surface>=<value>, got %r"
                % (pair,)]
    key, _, value = pair.partition("=")
    if not key.startswith("harness."):
        return ["--set expects harness.<surface>=<value>, got %r"
                % (pair,)]
    surface = key[len("harness."):]
    if surface not in capabilities:
        violations.append(
            "unknown harness surface %r: known surfaces are %s"
            % (surface, ", ".join(sorted(capabilities))))
        return violations
    if is_secret_shaped(value):
        violations.append(
            "harness.%s value is secret-shaped: values are refs "
            "only, never secret values" % surface)
        return violations
    if value not in capabilities[surface]:
        violations.append(
            "unknown harness value %r for %s: known bindings are "
            "%s" % (value, surface,
                    ", ".join(capabilities[surface])))
    return violations


def edition_scoped_checks(all_checks: Any,
                          selected_flags: Any) -> Tuple[List[str], List[str]]:
    """Split check names into (run, skipped) under edition scope.

    Edition selects within the run: selected checks run, the rest
    are reported skipped — never reported as passed. Skipped and
    passed are disjoint by construction.
    """
    selected = set(selected_flags) if selected_flags else set()
    run = [name for name in (all_checks or []) if name in selected]
    skipped = [name for name in (all_checks or []) if name not in selected]
    return (run, skipped)


def binding_status(bindings: Any) -> Dict[str, str]:
    """Report each configured surface's binding status (redacted).

    Every reported value passes through redact_value, so no
    secret-shaped value ever reaches doctor output.
    """
    if not isinstance(bindings, dict):
        return {}
    return {str(surface): str(redact_value(value))
            for surface, value in sorted(bindings.items())}


def requires_apply(mutating: bool, apply: bool) -> List[str]:
    """Return violations when a live mutation lacks explicit opt-in.

    Default doctor --live is read-only: any mutating path without
    --apply is refused. With --apply, the path records what it
    changed (caller-owned receipt).
    """
    if mutating and not apply:
        return ["live mutation requires explicit --apply: "
                "default doctor --live is read-only"]
    return []
