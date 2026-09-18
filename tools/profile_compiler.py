"""Stage 20b Standard half: metadata-first profile-compiler candidate
selection.

The compiler consumes Stage 20a SkillDescriptor-shaped records (contract
v1.0.0, additive-only) as plain data and selects candidates from
descriptors alone: routing sees names, blurbs, budget estimates, and
dependency edges — never bodies. Bodies are resolved JIT after task
selection by an injected Stage 20a ``resolve_body`` callable; this module
performs no filesystem access itself.

Selection semantics (fail closed, with repair guidance):

- Requests are semantic IDs (``capability.<slug>``), bare slugs, or
  keywords. A keyword hitting several descriptors is refused as
  ambiguous with the tied candidates named; it is never silently picked.
- Capability-level dependencies expand transitively: a dependency entry
  whose ``capability.<slug>`` exists in the index is a skill-level
  dependency and is selected before its dependent. Entries with no such
  capability are Stage 20a body-asset directories (``agents``,
  ``references``, ...) — inert here, resolved JIT alongside the body.
  Cycles are findings.
- The activated set is budget-checked as a whole: an over-budget
  selection is rejected, never truncated.
- The normal policy is one process skill plus one domain skill body;
  more top-level capabilities than that are refused. Policy changes stay
  with the Standard, not this mechanism.
- The provider label is recorded for audit and never affects selection.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

CONTRACT_VERSION = "1.0.0"

DESCRIPTOR_FIELDS = (
    "name",
    "semantic_id",
    "description",
    "body_bytes",
    "body_tokens_est",
    "dependencies",
    "body_digest",
    "source_path",
)

PROCESS_PLUS_DOMAIN_BUDGET = 2

SEMANTIC_ID_RE = re.compile(r"^capability\.[A-Za-z0-9][A-Za-z0-9_-]*$")

_STR_FIELDS = ("name", "semantic_id", "description", "body_digest",
               "source_path")
_INT_FIELDS = ("body_bytes", "body_tokens_est")


def validate_descriptor(record: Dict[str, Any]) -> List[str]:
    """Return repair strings; empty means the record is a valid Stage 20a
    descriptor."""
    repairs: List[str] = []
    for name in DESCRIPTOR_FIELDS:
        if name not in record:
            repairs.append("descriptor missing %r: Stage 20a descriptors "
                           "need it" % name)
    for name in _STR_FIELDS:
        if name in record and not str(record[name] or "").strip():
            repairs.append("descriptor field %r must be a non-empty string"
                           % name)
    for name in _INT_FIELDS:
        value = record.get(name)
        if name in record and (not isinstance(value, int)
                               or isinstance(value, bool) or value < 0):
            repairs.append("descriptor field %r must be a non-negative int"
                           % name)
    if "dependencies" in record and not isinstance(
            record.get("dependencies"), list):
        repairs.append("descriptor field 'dependencies' must be a list")
    semantic_id = str(record.get("semantic_id", ""))
    if semantic_id and not SEMANTIC_ID_RE.match(semantic_id):
        repairs.append("semantic_id %r is not capability.<slug>" % semantic_id)
    return repairs


def discovery_tokens(descriptors: List[Dict[str, Any]]) -> int:
    """Routing-time metadata cost: ~tokens to discover the whole catalog
    from descriptors alone (names + semantic IDs + blurbs)."""
    chars = 0
    for d in descriptors:
        chars += len(str(d.get("name", "")))
        chars += len(str(d.get("semantic_id", "")))
        chars += len(str(d.get("description", "")))
    return chars // 4


def build_index(descriptors: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Routing table keyed by semantic ID; duplicate capabilities fail
    closed, matching the Stage 20a discovery index."""
    table: Dict[str, Dict[str, Any]] = {}
    for d in descriptors:
        semantic_id = str(d.get("semantic_id", ""))
        if semantic_id in table:
            raise ValueError(
                "duplicate capability in discovery index: %s" % semantic_id)
        table[semantic_id] = d
    return table


@dataclass
class CompileResult:
    """One candidate-selection outcome from descriptors alone."""

    selected: List[Dict[str, Any]] = field(default_factory=list)
    findings: List[str] = field(default_factory=list)
    discovery_tokens: int = 0
    body_tokens_est: int = 0
    provider: str = ""
    requested: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.findings


@dataclass
class ActivationResult:
    """One JIT activation pass via an injected resolve_body callable."""

    bodies: Dict[str, str] = field(default_factory=dict)
    findings: List[str] = field(default_factory=list)
    body_tokens: int = 0

    @property
    def ok(self) -> bool:
        return not self.findings


def _resolve_request(request: str,
                     table: Dict[str, Dict[str, Any]]) -> List[str]:
    """Resolve one request to candidate semantic IDs ([] if absent).

    Order: exact semantic ID, then slug shorthand, then keyword match over
    name and description. Multiple keyword hits mean ambiguity, not a pick.
    """
    if request in table:
        return [request]
    slug_id = "capability.%s" % request
    if slug_id in table:
        return [slug_id]
    term = request.lower()
    hits = sorted(
        semantic_id
        for semantic_id, d in table.items()
        if term in str(d.get("name", "")).lower()
        or term in str(d.get("description", "")).lower()
    )
    return hits


def select_candidates(descriptors: List[Dict[str, Any]],
                      capabilities: List[str],
                      budget_tokens: Optional[int] = None,
                      provider: str = "claude") -> CompileResult:
    """Select the candidate set from descriptors alone — no body loading.

    Raises:
        ValueError: On duplicate capabilities (index integrity).
    """
    table = build_index(descriptors)
    result = CompileResult(
        discovery_tokens=discovery_tokens(descriptors),
        provider=provider,
        requested=list(capabilities),
    )
    findings = result.findings

    resolved: List[str] = []
    for request in capabilities:
        candidates = _resolve_request(str(request), table)
        if not candidates:
            findings.append(
                "capability %r absent from discovery index: repair the "
                "catalog or correct the request" % request)
            continue
        if len(candidates) > 1:
            findings.append(
                "ambiguous descriptor %r: %d candidates (%s); "
                "disambiguate by semantic ID" % (
                    request, len(candidates), ", ".join(candidates)))
            continue
        if candidates[0] not in resolved:
            resolved.append(candidates[0])

    if len(resolved) > PROCESS_PLUS_DOMAIN_BUDGET:
        findings.append(
            "%d top-level capabilities exceed the "
            "one-process-plus-one-domain policy (%d); narrow the selection"
            % (len(resolved), PROCESS_PLUS_DOMAIN_BUDGET))

    selected: List[Dict[str, Any]] = []
    visited: set = set()
    path: List[str] = []

    def expand(semantic_id: str) -> None:
        if semantic_id in visited:
            if semantic_id in path:
                cycle = " -> ".join(path + [semantic_id])
                findings.append(
                    "dependency cycle detected: %s; refuse binding" % cycle)
            return
        visited.add(semantic_id)
        path.append(semantic_id)
        descriptor = table[semantic_id]
        for dep in descriptor.get("dependencies", []) or []:
            dep_id = dep if str(dep).startswith("capability.") \
                else "capability.%s" % dep
            if dep_id in table:
                expand(dep_id)
        path.pop()
        selected.append(dict(descriptor))

    for semantic_id in resolved:
        expand(semantic_id)

    result.selected = selected
    result.body_tokens_est = sum(
        int(d.get("body_tokens_est", 0)) for d in selected)
    if budget_tokens is not None and result.body_tokens_est > budget_tokens:
        findings.append(
            "over budget: activated set needs %d tokens, budget is %d; "
            "selection rejected, not truncated"
            % (result.body_tokens_est, budget_tokens))
        result.selected = []
    return result


def activate_selected(selected: List[Dict[str, Any]],
                      resolve_body: Callable[..., str],
                      repo_root: Any) -> ActivationResult:
    """Resolve bodies JIT through the Stage 20a ``resolve_body`` contract.

    The compiler itself performs no I/O: ``resolve_body(descriptor,
    repo_root)`` is caller-supplied. Documented Stage 20a failures surface
    as repair findings: a missing body means the catalog is broken; a
    body-hash change means re-index before loading.
    """
    result = ActivationResult()
    tokens = 0
    for descriptor in selected:
        semantic_id = str(descriptor.get("semantic_id", ""))
        try:
            body = resolve_body(descriptor, repo_root)
        except FileNotFoundError:
            result.findings.append(
                "selected skill %r has no body on disk: repair the catalog "
                "or drop it from the profile" % semantic_id)
            continue
        except ValueError:
            result.findings.append(
                "body hash changed for %r: re-index before loading"
                % semantic_id)
            continue
        result.bodies[semantic_id] = body
        tokens += len(str(body).encode()) // 4
    result.body_tokens = tokens
    return result
