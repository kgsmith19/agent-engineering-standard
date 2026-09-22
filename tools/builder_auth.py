"""Stage 35 Standard half: Builder implementation authorization gate.

Arc A (Stage 34) decides whether one slice may advance toward
Builder authorization; Stage 35 (Risk R3) is the exact gate
itself — the irreversible seam between no-code Arc A and
production mutation. ``authorize`` denies production mutation
until phase, role receipt, exclusive lease, exact head,
digest binding, protected paths, scope, context, disposition,
and frozen-oracle policy are all valid. A suspected Mold
defect never proceeds: it reopens back to Arc A.

Authorization request shape (plain data; missing keys fall
back to total defaults, never a crash)::

    {"phase": str,               # arc_gate phase (want IMPLEMENT_AUTHORIZED)
     "role": str,                # requesting role (want "builder")
     "receipts": [{...}],        # role_authority receipts
     "lease": {...},             # {"holder": str, "generation": int,
                                 #  "exclusive": bool}
     "head": str,                # head this decision executes at
     "mold_digest": str,         # Mold digest this request binds
     "qualified_digest": str,    # digest the qualification receipt binds
     "run_digest": str,          # run digest this request binds
     "qualified_run_digest": str,# run digest the receipt binds
     "files": [str, ...],        # production files this grant would write
     "protected_paths": [str, ...],
     "scope": {...},             # {"claims": [...] | {"paths": [...]}} or {}
     "allowed_scope": {...},     # authorized boundary (same shape)
     "disposition": str,         # want IMPLEMENT
     "observation_head": str,    # head the observation binds
     "owner_hold": bool,         # owner hold blocks even a clean grant
     "frozen_ok": bool,          # frozen-oracle policy (freeze binds)
     "provider": str}

Frozen rules (first listed first checked; findings appended in
this order, so output order is stable):

1. ``phase-not-authorized`` — Arc A phase is not
   IMPLEMENT_AUTHORIZED (anything earlier reopens to Arc A).
2. ``role-not-builder`` — requesting role is not builder.
3. ``receipt-missing`` — no fresh builder receipt at the exact
   head (missing, wrong role, or stale head).
4. ``lease-conflict`` — no exclusive lease held by this
   builder at a current fencing generation (absent holder,
   shared lease, stale generation, or чужой holder).
5. ``head-stale`` — observation head differs from the decision
   head (exact-head binding).
6. ``digest-drift`` — Mold digest or run digest differs from
   the qualified binding (altered expected value).
7. ``protected-path`` — a granted file sits at or under a
   protected path (no Builder may alter a protected Mold).
8. ``scope-expansion`` — a granted claim/path lies outside the
   authorized scope (no scope broadening after authorization).
9. ``context-overrun`` — footprint status is RECOVERY_REQUIRED
   or ROTATE_NOW_READ_ONLY (context overrun).
10. ``disposition-blocked`` — disposition is not IMPLEMENT
    (NO_CHANGE terminates the grant the same way it terminates
    Arc A advancement).
11. ``owner-hold`` — an owner hold blocks the grant even when
    every other condition is valid.
12. ``frozen-policy`` — the frozen-oracle policy does not bind
    (freeze drift without reopen-and-requalify).

``authorize`` returns one decision (allowed plus ordered
findings; empty means GRANTED). ``validate_builder_corpus``
checks the frozen oracle. Pure functions: no I/O,
deterministic in their inputs.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

try:
    import context_budget as _context_budget
except Exception:
    _context_budget = None

RULES = (
    "phase-not-authorized",
    "role-not-builder",
    "receipt-missing",
    "lease-conflict",
    "head-stale",
    "digest-drift",
    "protected-path",
    "scope-expansion",
    "context-overrun",
    "disposition-blocked",
    "owner-hold",
    "frozen-policy",
)

DISPOSITIONS = (
    "IMPLEMENT",
    "NO_CHANGE",
    "INSUFFICIENT_EVIDENCE",
    "OWNER_DECISION",
)

_ENTRY_ID_RE = None  # compiled lazily (stdlib re import below)

import re as _re

_ENTRY_ID_RE = _re.compile(r"^builder-auth\.[a-z-]+\.\d{2}$")


def _make_finding(rule: str, message: str, excerpt: str,
                  severity: str = "blocker") -> Dict[str, str]:
    """Build one structured finding dict for a refused grant."""
    return {
        "id": "%s-1" % rule,
        "rule": rule,
        "finding": message,
        "severity": severity,
        "excerpt": excerpt[:200],
    }


def validate_finding(finding: Any) -> List[str]:
    """Return repair strings for one finding; empty means valid."""
    if not isinstance(finding, dict):
        return ["finding must be a mapping of plain data, not %s"
                % type(finding).__name__]
    repairs = []
    for key in ("id", "rule", "finding", "severity", "excerpt"):
        if key not in finding:
            repairs.append("finding is missing required key %r" % key)
    rule = finding.get("rule")
    if "rule" in finding and rule not in RULES:
        repairs.append("finding rule %r is not a frozen Stage 35 "
                       "builder rule" % (rule,))
    if "severity" in finding and finding.get("severity") not in (
            "blocker", "major", "minor"):
        repairs.append("finding severity %r must be "
                       "blocker|major|minor" % (finding.get("severity"),))
    return repairs


def _path_touched(touched: str, protected: str) -> bool:
    """True when a touched path is at or under a protected path."""
    clean = str(touched or "").replace("\\", "/").strip().lstrip("/")
    guard = str(protected or "").replace("\\", "/").strip().lstrip("/")
    if not clean or not guard:
        return False
    if clean == guard:
        return True
    return clean.startswith(guard.rstrip("/") + "/")


def _normalize_request(request: Any) -> Dict[str, Any]:
    """Fill total defaults so partial input never crashes."""
    request = request if isinstance(request, dict) else {}
    files = request.get("files")
    protected = request.get("protected_paths")
    receipts = request.get("receipts")
    lease = request.get("lease")
    scope = request.get("scope")
    allowed = request.get("allowed_scope")
    footprint = request.get("footprint")
    return {
        "phase": str(request.get("phase", "")),
        "role": str(request.get("role", "")),
        "agent": str(request.get("agent", "")),
        "receipts": [r for r in receipts if isinstance(r, dict)]
        if isinstance(receipts, list) else [],
        "lease": dict(lease) if isinstance(lease, dict) else {},
        "head": str(request.get("head", "")),
        "mold_digest": str(request.get("mold_digest", "")),
        "qualified_digest": str(request.get("qualified_digest", "")),
        "run_digest": str(request.get("run_digest", "")),
        "qualified_run_digest": str(request.get(
            "qualified_run_digest", "")),
        "files": [str(v) for v in files
                  if isinstance(v, (str, int, float))]
        if isinstance(files, list) else [],
        "protected_paths": [str(v) for v in protected
                            if isinstance(v, (str, int, float))]
        if isinstance(protected, list) else [],
        "scope": dict(scope) if isinstance(scope, dict) else {},
        "allowed_scope": dict(allowed)
        if isinstance(allowed, dict) else {},
        "footprint": dict(footprint)
        if isinstance(footprint, dict) else {},
        "context_polluted": bool(request.get("context_polluted",
                                             False)),
        "context_missing": bool(request.get("context_missing",
                                            False)),
        "disposition": str(request.get("disposition",
                                       "IMPLEMENT")),
        "observation_head": str(request.get("observation_head",
                                            "")),
        "owner_hold": bool(request.get("owner_hold", False)),
        "frozen_ok": bool(request.get("frozen_ok", True)),
        "provider": str(request.get("provider", "")),
    }


def _check_phase(request: Dict[str, Any]) -> List[Dict[str, str]]:
    """Phase gate: Arc A must stand at IMPLEMENT_AUTHORIZED."""
    if request["phase"] != "IMPLEMENT_AUTHORIZED":
        return [_make_finding(
            "phase-not-authorized",
            "Arc A phase is %r, not IMPLEMENT_AUTHORIZED: "
            "reopen back to Arc A instead of proceeding"
            % (request["phase"] or "(no phase)"),
            request["phase"] or "(no phase)")]
    return []


def _check_role(request: Dict[str, Any]) -> List[Dict[str, str]]:
    """Role gate: only the builder role may take the grant."""
    if request["role"] != "builder":
        return [_make_finding(
            "role-not-builder",
            "requesting role is %r, not builder: only a builder "
            "receipt authorizes production mutation"
            % (request["role"] or "(no role)"),
            request["role"] or "(no role)")]
    return []


def _check_receipt(request: Dict[str, Any]) -> List[Dict[str, str]]:
    """Receipt gate: a fresh builder receipt at the exact head."""
    matching = [r for r in request["receipts"]
                if str(r.get("role", "")) == "builder"]
    if not matching:
        return [_make_finding(
            "receipt-missing",
            "no builder receipt: present a fresh builder receipt "
            "at the exact head",
            request["role"] or "(no role)")]
    head = request["head"]
    for receipt in matching:
        if head and str(receipt.get("head", "")) != head:
            return [_make_finding(
                "receipt-missing",
                "builder receipt is stale (receipt %.12s != head "
                "%.12s): re-issue at the current head"
                % (str(receipt.get("head", ""))[:12],
                   head[:12]),
                str(receipt.get("head", ""))[:200])]
    return []


def _check_lease(request: Dict[str, Any]) -> List[Dict[str, str]]:
    """Lease gate: one exclusive lease, current generation, held here.

    The lease is temporary exclusive write authority with a
    fencing generation (outcome_terms): the holder must equal
    this builder agent, ``exclusive`` must be true (a second
    writer is refused), and ``generation`` must be current
    (>= ``min_generation`` — a stale generation is a fenced
    writer and is refused).
    """
    lease = request["lease"]
    agent = request["agent"]
    holder = str(lease.get("holder", "") or "")
    if not holder:
        return [_make_finding(
            "lease-conflict",
            "no lease held: one exclusive lease per slice; claim "
            "it before production mutation",
            "(no lease)")]
    if agent and holder != agent:
        return [_make_finding(
            "lease-conflict",
            "lease held by %r, not this builder %r: a second "
            "writer is refused" % (holder, agent),
            holder[:200])]
    if not lease.get("exclusive", False):
        return [_make_finding(
            "lease-conflict",
            "lease for %r is shared: production mutation needs "
            "exclusive write authority" % holder,
            holder[:200])]
    try:
        generation = int(lease.get("generation", 0))
    except (TypeError, ValueError):
        return [_make_finding(
            "lease-conflict",
            "lease generation %r is not a fencing counter: "
            "mint a current generation" % (lease.get(
                "generation", ""),),
            holder[:200])]
    try:
        minimum = int(lease.get("min_generation", 0))
    except (TypeError, ValueError):
        minimum = 0
    if generation < minimum:
        return [_make_finding(
            "lease-conflict",
            "lease generation %d is fenced (minimum %d): a stale "
            "writer is refused" % (generation, minimum),
            holder[:200])]
    if generation <= 0:
        return [_make_finding(
            "lease-conflict",
            "lease generation %d is not current: mint a current "
            "fencing generation" % generation,
            holder[:200])]
    return []


def _check_head(request: Dict[str, Any]) -> List[Dict[str, str]]:
    """Exact-head gate: the observation binds the decision head."""
    head = request["head"]
    observed = request["observation_head"]
    if not head or not observed:
        return [_make_finding(
            "head-stale",
            "no exact head binding: record the decision head and "
            "the observation head before mutating",
            "(no head)")]
    if observed != head:
        return [_make_finding(
            "head-stale",
            "observation head %.12s != decision head %.12s: "
            "re-observe at the current head"
            % (observed[:12], head[:12]),
            observed[:200])]
    return []


def _check_digests(request: Dict[str, Any]) -> List[Dict[str, str]]:
    """Digest gate: Mold and run digests match the qualification."""
    if not request["mold_digest"] or not request["qualified_digest"]:
        return [_make_finding(
            "digest-drift",
            "no digest binding: bind the Mold digest to its "
            "qualification receipt before mutating",
            "(no digest)")]
    if request["mold_digest"] != request["qualified_digest"]:
        return [_make_finding(
            "digest-drift",
            "Mold digest %.12s != qualified %.12s: an altered "
            "expected value reopens to Arc A"
            % (request["mold_digest"][:12],
               request["qualified_digest"][:12]),
            request["mold_digest"][:200])]
    if request["run_digest"] and request["qualified_run_digest"] \
            and request["run_digest"] != \
            request["qualified_run_digest"]:
        return [_make_finding(
            "digest-drift",
            "run digest %.12s != qualified %.12s: the run moved "
            "after qualification"
            % (request["run_digest"][:12],
               request["qualified_run_digest"][:12]),
            request["run_digest"][:200])]
    return []


def _check_protected(request: Dict[str, Any]) -> List[Dict[str, str]]:
    """Protected-path gate: no Builder alters a protected path."""
    protected = tuple(request["protected_paths"])
    for path in request["files"]:
        if _path_touched(path, "Canonical/corpus") \
                or path == "Canonical/corpus":
            return [_make_finding(
                "protected-path",
                "protected path %r: frozen corpora are immutable "
                "to builders" % path,
                path[:200])]
        for guard in protected:
            if _path_touched(path, guard) or path == guard:
                return [_make_finding(
                    "protected-path",
                    "protected path %r: no Builder may alter a "
                    "protected Mold or path" % path,
                    path[:200])]
    return []


def _scope_items(scope: Any) -> List[str]:
    """Flatten one scope mapping to its bounded items."""
    if not isinstance(scope, dict):
        return []
    items: List[str] = []
    for key in ("claims", "paths"):
        value = scope.get(key)
        if isinstance(value, list):
            items.extend(str(v) for v in value
                         if isinstance(v, (str, int, float)))
    return items


def _check_scope(request: Dict[str, Any]) -> List[Dict[str, str]]:
    """Scope gate: the grant stays inside the authorized scope."""
    granted = _scope_items(request["scope"])
    allowed = _scope_items(request["allowed_scope"])
    if not granted:
        return [_make_finding(
            "scope-expansion",
            "grant names no scoped claims or paths: bound the "
            "mutation before authorizing it",
            "(no scope)")]
    if not allowed:
        return [_make_finding(
            "scope-expansion",
            "no authorized scope recorded: authorize the scope in "
            "Arc A before mutating",
            granted[0][:200] if granted else "(no scope)")]
    for item in granted:
        if item not in allowed:
            return [_make_finding(
                "scope-expansion",
                "grant %r lies outside the authorized scope: no "
                "scope broadening after authorization" % item,
                item[:200])]
    return []


def _check_context(request: Dict[str, Any]) -> List[Dict[str, str]]:
    """Context gate: no overrun past the rotation boundary."""
    if _context_budget is None:
        raise RuntimeError(
            "builder-auth requires sibling tool 'context_budget' "
            "on the import path (tools/): refusing to pass the "
            "gate without it")
    context_budget = _context_budget
    footprint = request["footprint"]
    if not footprint:
        return [_make_finding(
            "context-overrun",
            "no context footprint: record the working set "
            "before authorization",
            "(no footprint)")]
    clean: Dict[str, int] = {}
    for key, value in footprint.items():
        try:
            clean[str(key)] = int(value)
        except (TypeError, ValueError):
            return [_make_finding(
                "context-overrun",
                "footprint entry %r is not a byte count: fix "
                "the working set" % str(key),
                "(bad footprint)")]
    verdict = context_budget.govern(
        clean,
        polluted=request["context_polluted"],
        missing_load_bearing=request["context_missing"])
    if verdict.get("status") in ("RECOVERY_REQUIRED",
                                 "ROTATE_NOW_READ_ONLY"):
        return [_make_finding(
            "context-overrun",
            "context overrun (%s): rotate from the capsule "
            "before production mutation"
            % "; ".join(verdict.get("reasons", []))[:120],
            "(working set)")]
    return []


def _check_disposition(request: Dict[str, Any]) -> List[Dict[str, str]]:
    """Disposition gate: only IMPLEMENT authorizes the grant."""
    disposition = request["disposition"]
    if disposition not in DISPOSITIONS:
        return [_make_finding(
            "disposition-blocked",
            "unknown disposition %r: state IMPLEMENT with a "
            "complete observation" % disposition,
            disposition[:200] or "(no disposition)")]
    if disposition != "IMPLEMENT":
        return [_make_finding(
            "disposition-blocked",
            "disposition is %s, not IMPLEMENT: a NO_CHANGE (or "
            "weaker) verdict terminates the grant"
            % disposition,
            disposition[:200])]
    return []


def _check_owner_hold(request: Dict[str, Any]) -> List[Dict[str, str]]:
    """Owner-hold gate: an owner hold blocks even a clean grant."""
    if request["owner_hold"]:
        return [_make_finding(
            "owner-hold",
            "owner hold is set: the grant waits for the owner "
            "even though every other condition is valid",
            "(owner hold)")]
    return []


def _check_frozen(request: Dict[str, Any]) -> List[Dict[str, str]]:
    """Frozen-oracle gate: the freeze must still bind."""
    if not request["frozen_ok"]:
        return [_make_finding(
            "frozen-policy",
            "frozen-oracle policy does not bind (freeze drift "
            "without reopen-and-requalify): reopen to Arc A",
            "(freeze drift)")]
    return []


@dataclass
class BuilderDecision:
    """One Builder authorization outcome for one request."""

    allowed: bool = False
    findings: List[Dict[str, str]] = field(default_factory=list)

    @property
    def granted(self) -> bool:
        return self.allowed \
            and not any(f.get("severity") == "blocker"
                        for f in self.findings)


def authorize(request: Any) -> BuilderDecision:
    """Decide one Builder authorization request as plain data.

    All twelve frozen gates run in order; any finding refuses
    the grant. A fully clean request is GRANTED with zero
    findings. Pure function: no I/O, deterministic in its
    input. This decides; it never mutates, never writes, never
    implements — the grant is a decision record only.
    """
    normalized = _normalize_request(request)
    findings: List[Dict[str, str]] = []
    findings.extend(_check_phase(normalized))
    findings.extend(_check_role(normalized))
    findings.extend(_check_receipt(normalized))
    findings.extend(_check_lease(normalized))
    findings.extend(_check_head(normalized))
    findings.extend(_check_digests(normalized))
    findings.extend(_check_protected(normalized))
    findings.extend(_check_scope(normalized))
    findings.extend(_check_context(normalized))
    findings.extend(_check_disposition(normalized))
    findings.extend(_check_owner_hold(normalized))
    findings.extend(_check_frozen(normalized))
    if findings:
        return BuilderDecision(allowed=False, findings=findings)
    return BuilderDecision(allowed=True, findings=[])


def _entries_of(corpus: Any) -> List[Dict[str, Any]]:
    if isinstance(corpus, dict):
        entries = corpus.get("entries")
    else:
        entries = corpus
    if not isinstance(entries, list):
        return []
    return entries


def validate_builder_corpus(corpus: Any) -> Tuple[List[str],
                                                  List[Dict[str, Any]]]:
    """Validate the frozen Builder authorization fixture oracle.

    Returns (findings, entries); an empty findings list means
    the corpus is a valid frozen oracle: frozen marker set,
    stable provenance, at least 12 entries, unique
    well-formed IDs, every entry computing its expected rules
    and grant flag, and all 12 builder rules covered.
    """
    if isinstance(corpus, dict):
        if corpus.get("_frozen") is not True:
            return (["builder corpus is not frozen: set "
                     "\"_frozen\": true"], [])
        provenance = str(corpus.get("_provenance", ""))
        if "Stage 35 #126" not in provenance:
            return (["builder corpus provenance must name "
                      "\"Stage 35 #126\""], [])
    elif not isinstance(corpus, list):
        return (["builder corpus must be a JSON object with an "
                 "'entries' array (or a bare array)"], [])
    entries = _entries_of(corpus)
    findings: List[str] = []
    if len(entries) < 12:
        findings.append("builder corpus holds %d entries, want "
                        "at least 12" % len(entries))
    seen: Dict[str, int] = {}
    covered = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            findings.append("entries[%d] is not a mapping" % index)
            continue
        cid = str(entry.get("id", ""))
        if not _ENTRY_ID_RE.match(cid):
            findings.append("entry %r: id is not "
                            "builder-auth.<class>.<nn>" % cid)
        if cid in seen:
            findings.append("duplicate entry id %s (entries %d "
                            "and %d)" % (cid, seen[cid], index))
        else:
            seen[cid] = index
        if not str(entry.get("note", "")).strip():
            findings.append("entry %s: a one-line adjudication note "
                            "is required" % cid)
        expected = entry.get("expected_rules")
        if not isinstance(expected, list):
            findings.append("entry %s: expected_rules must be a list"
                            % cid)
            continue
        for rule in expected:
            if rule not in RULES:
                findings.append("entry %s: unknown expected rule %r"
                                % (cid, rule))
        covered.update(str(r) for r in expected
                       if isinstance(r, str))
        if "expected_granted" not in entry:
            findings.append("entry %s: expected_granted is required"
                            % cid)
        result = authorize(entry.get("request", {}))
        computed = sorted({f["rule"] for f in result.findings})
        if sorted(str(r) for r in expected) != computed:
            findings.append("entry %s: expected_rules %r != "
                            "authorize %r"
                            % (cid, sorted(str(r)
                                           for r in expected),
                               computed))
        if bool(entry.get("expected_granted")) != result.granted:
            findings.append("entry %s: expected_granted %r != "
                            "authorize %r" % (cid, entry.get(
                                "expected_granted"),
                                result.granted))
    for rule in RULES:
        if rule not in covered:
            findings.append("rule %r has no entries (all 12 "
                            "builder rules are required)"
                            % rule)
    return findings, entries


def clean_request() -> Dict[str, Any]:
    """One clean Builder authorization request (GRANTED).

    Every gate holds: IMPLEMENT_AUTHORIZED phase, builder role
    with a fresh receipt at the exact head, an exclusive lease
    at a current fencing generation held by this builder, bound
    observation head, matching Mold/run digests, tools-only
    files, in-scope claims, a healthy footprint, IMPLEMENT
    disposition, no owner hold, and a binding freeze. Callers
    mutate one dimension per test.
    """
    head = "a" * 40
    mold_digest = ("aebc4e7beecafd257a8329577e5234955bae455f5033f"
                   "db525e6e78f66469fc6")
    run_digest = "r" * 40
    return {
        "phase": "IMPLEMENT_AUTHORIZED",
        "role": "builder",
        "agent": "builder-1",
        "receipts": [{
            "role": "builder",
            "agent": "builder-1",
            "provider": "anthropic/claude",
            "head": head,
            "seq": 1,
            "granted_by": "builder-1",
        }],
        "lease": {
            "holder": "builder-1",
            "generation": 3,
            "min_generation": 3,
            "exclusive": True,
        },
        "head": head,
        "mold_digest": mold_digest,
        "qualified_digest": mold_digest,
        "run_digest": run_digest,
        "qualified_run_digest": run_digest,
        "files": ["tools/builder_auth.py"],
        "protected_paths": ["src/protected-impl.py"],
        "scope": {"claims": ["claim-total"]},
        "allowed_scope": {"claims": ["claim-total",
                                     "claim-extra"]},
        "footprint": {
            "capsule": 1000,
            "rules": 1000,
            "files": 1000,
            "skills": 500,
            "mcp": 100,
            "tool_output": 500,
        },
        "context_polluted": False,
        "context_missing": False,
        "disposition": "IMPLEMENT",
        "observation_head": head,
        "owner_hold": False,
        "frozen_ok": True,
        "provider": "anthropic/claude",
    }
