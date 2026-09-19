"""Stage 30 Standard half: verification role separation and path authority.

Separate Spec Author/Critic, Mold Designer/Qualifier, Builder,
Verifier, Reviewer, and Remediator responsibilities. Every role
holds write authority only inside its own roots; a defect lets a
role write outside its authorized paths or fake independence.

Write authority matrix (frozen, documented precedence):

- ``spec_author`` may write: ``specs/``, ``plans/`` (receipts and
  draft spec texts under caller-defined work roots). May NOT
  write: ``src/``, ``tools/``, ``Canonical/``.
- ``spec_critic`` may write only: ``evidence/critic-findings/``.
  Everything else forbidden.
- ``mold_designer`` may write: ``verification/pending/`` (mold
  drafts), ``evidence/``. May NOT write: ``src/``, ``tools/``,
  ``Canonical/corpus/`` (frozen corpora are immutable to all
  roles). Fixtures stay frozen, so no direct corpus writes.
- ``mold_qualifier`` may write only: ``evidence/qualification/``.
- ``builder`` may write: ``src/``, ``plans/`` (local plans),
  ``evidence/builder-notes/``. May NOT write: ``Canonical/``,
  ``tools/``, ``.github/``, ``evidence/`` outside its own dir.
- ``verifier`` may write only: ``evidence/verification/``. May
  NOT write ``src/`` (a verifier touching src is the classic
  self-review contamination).
- ``reviewer`` may write only: ``evidence/review/`` (verdicts).
  May NOT write ``src/``, ``tools/``, ``Canonical/``.
- ``remediator`` may write: the bounded remediation scope handed
  from findings: ``src/``, ``evidence/remediation/``. May NOT
  write: ``Canonical/corpus/``, ``tools/``, ``.github/``.
- ALL roles are forbidden from frozen corpora: any write whose
  normalized target starts with ``Canonical/corpus/`` is refused
  regardless of role (``FROZEN_ROOTS``).

Matching precedence (first listed first applied, stable output):

1. ``unknown-role`` — role not in ROLES.
2. ``no-receipt`` — no receipts presented.
3. ``self-promotion`` — no receipt carries the requested role
   (a builder receipt presented for a verifier write).
4. ``stale-receipt`` — matching receipt head != current head.
5. ``path-traversal`` — normalized target escapes (``..`` above
   root).
6. ``frozen-root`` — target under ``FROZEN_ROOTS``.
7. ``forbidden-path`` — target under role FORBIDDEN_PATHS, or
   outside role WRITE_PATHS (default deny).
8. ``write-root`` — target under role WRITE_PATHS (allowed).

Receipts are plain dicts (no I/O): ``issue_receipt`` mints one
with fields ``("role", "agent", "provider", "head", "seq",
"granted_by")``. ``validate_receipt`` returns repair strings
(stale head, unknown/unauthorized role). Same-agent reuse of
distinct roles is never silently independent: ``disclose_roles``
names the agent and roles. Provider separation guards R2/R3
blocking review (reviewer family != builder family). Owner
override is explicit-only (owner ``kgsmith19`` plus non-empty
decision and scope). Child receipts derive only from the granted
role (``via: <parent agent>``) and never escalate.

Mold qualification logic is explicitly NOT implemented here
(Stage 31). This module consumes roles/paths/receipts as plain
data and performs no filesystem access itself.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

RISKS = ("R0", "R1", "R2", "R3")

FINDING_FIELDS = ("id", "rule", "finding", "severity", "excerpt")

SEVERITIES = ("blocker", "major", "minor")

RULES = (
    "write-root",
    "forbidden-path",
    "frozen-root",
    "stale-receipt",
    "self-promotion",
    "owner-override",
    "unknown-role",
    "path-traversal",
    "no-receipt",
)

ROLES = (
    "spec_author",
    "spec_critic",
    "mold_designer",
    "mold_qualifier",
    "builder",
    "verifier",
    "reviewer",
    "remediator",
)

RECEIPT_FIELDS = ("role", "agent", "provider", "head", "seq",
                  "granted_by")

OWNER_LOGIN = "kgsmith19"

FROZEN_ROOTS = ("Canonical/corpus/",)

WRITE_PATHS: Dict[str, tuple] = {
    "spec_author": ("specs/", "plans/"),
    "spec_critic": ("evidence/critic-findings/",),
    "mold_designer": ("verification/pending/", "evidence/"),
    "mold_qualifier": ("evidence/qualification/",),
    "builder": ("src/", "plans/", "evidence/builder-notes/"),
    "verifier": ("evidence/verification/",),
    "reviewer": ("evidence/review/",),
    "remediator": ("src/", "evidence/remediation/"),
}

FORBIDDEN_PATHS: Dict[str, tuple] = {
    "spec_author": ("src/", "tools/", "Canonical/"),
    "spec_critic": ("src/", "tools/", "Canonical/", "specs/",
                    "plans/", "verification/"),
    "mold_designer": ("src/", "tools/", "Canonical/corpus/"),
    "mold_qualifier": ("src/", "tools/", "Canonical/",
                       "verification/pending/"),
    "builder": ("Canonical/", "tools/", ".github/"),
    "verifier": ("src/", "tools/", "Canonical/", ".github/"),
    "reviewer": ("src/", "tools/", "Canonical/", ".github/"),
    "remediator": ("Canonical/corpus/", "tools/", ".github/"),
}

_CANARY_ID_RE = re.compile(r"^role-authority\.[a-z-]+\.\d{2}$")


@dataclass
class AuthDecision:
    """One authorization outcome for one role write."""

    allowed: bool = False
    rule: str = "forbidden-path"
    finding: Optional[Dict[str, str]] = None


def _make_finding(rule: str, message: str, excerpt: str,
                  severity: str = "blocker") -> Dict[str, str]:
    """Build one structured finding dict for a refused write."""
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
    repairs: List[str] = []
    for field_name in FINDING_FIELDS:
        if field_name not in finding:
            repairs.append("missing field %r: add it to the finding"
                           % field_name)
        elif not str(finding[field_name]).strip():
            repairs.append("field %r must be a non-empty string"
                           % field_name)
    for key in finding:
        if key not in FINDING_FIELDS:
            repairs.append("unknown field %r: remove it from the finding"
                           % key)
    severity = finding.get("severity")
    if severity is not None and severity not in SEVERITIES:
        repairs.append("unknown severity %r: severity is one of %s"
                       % (severity, ", ".join(SEVERITIES)))
    rule = finding.get("rule")
    if rule is not None and rule not in RULES:
        repairs.append("unknown rule %r: rule is one of %s"
                       % (rule, ", ".join(RULES)))
    return repairs


def _normalize_path(path: Any) -> Tuple[str, bool]:
    """Normalize a write target; return (normalized, is_traversal).

    Leading slashes are stripped, backslashes become slashes, ``.``
    segments collapse, and ``..`` pops one segment. A ``..`` with
    no segment to pop escapes the root and is traversal.
    """
    raw = str(path if isinstance(path, str) else (path or ""))
    raw = raw.replace("\\", "/").strip()
    raw = raw.lstrip("/")
    parts: List[str] = []
    for segment in raw.split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            if not parts:
                return raw, True
            parts.pop()
            continue
        parts.append(segment)
    return "/".join(parts), False


def _matches_prefix(normalized: str, prefix: str) -> bool:
    """True when a normalized path sits at or under a prefix root.

    Prefixes end with ``/``; the bare directory itself (without the
    trailing slash) also matches. Matching is on whole segments,
    never substrings (``src/`` never matches ``src-evil/``).
    """
    if not prefix.endswith("/"):
        prefix = prefix + "/"
    stem = prefix[:-1]
    if normalized == stem:
        return True
    return normalized.startswith(prefix)


def _under_any(normalized: str, prefixes: tuple) -> bool:
    return any(_matches_prefix(normalized, prefix)
               for prefix in prefixes)


def issue_receipt(role: str, agent: str, provider: str, head: str,
                  seq: int) -> Dict[str, Any]:
    """Mint one role receipt as plain data (no I/O)."""
    return {
        "role": str(role),
        "agent": str(agent),
        "provider": str(provider),
        "head": str(head),
        "seq": int(seq),
        "granted_by": str(agent),
    }


def validate_receipt(receipt: Any, *, current_head: str,
                     authorized_roles: Any) -> List[str]:
    """Return repair strings for one receipt; empty means fresh."""
    if not isinstance(receipt, dict):
        return ["receipt must be a mapping of plain data, not %s"
                % type(receipt).__name__]
    repairs: List[str] = []
    for field_name in RECEIPT_FIELDS:
        if field_name not in receipt:
            repairs.append("missing field %r: add it to the receipt"
                           % field_name)
    role = str(receipt.get("role", ""))
    if role not in ROLES:
        repairs.append("unknown role %r: role is one of %s"
                       % (role, ", ".join(ROLES)))
    elif isinstance(authorized_roles, (list, tuple, set)) \
            and role not in authorized_roles:
        repairs.append("unauthorized role %r: not in the authorized set"
                       % role)
    if str(receipt.get("head", "")) != str(current_head):
        repairs.append("stale receipt: head %r != current head %r; "
                       "re-issue at the current head"
                       % (str(receipt.get("head", "")),
                          str(current_head)))
    return repairs


def disclose_roles(receipts: Any) -> List[str]:
    """Require disclosure when one agent holds distinct roles.

    Same-agent reuse of normally-independent roles (e.g.
    builder+verifier) is never silently independent: returns one
    disclosure string per agent holding two or more distinct
    roles, naming the agent and roles. Empty means independent.
    """
    if not isinstance(receipts, list):
        return []
    by_agent: Dict[str, set] = {}
    for receipt in receipts:
        if not isinstance(receipt, dict):
            continue
        agent = str(receipt.get("agent", ""))
        role = str(receipt.get("role", ""))
        if not agent or not role:
            continue
        by_agent.setdefault(agent, set()).add(role)
    disclosures: List[str] = []
    for agent in sorted(by_agent):
        roles = sorted(by_agent[agent])
        if len(roles) >= 2:
            disclosures.append(
                "agent %s holds roles %s: disclosure required; "
                "same-agent reuse is not independent"
                % (agent, "+".join(roles)))
    return disclosures


def _family(provider: Any) -> str:
    text = str(provider or "").strip().lower()
    if "/" in text:
        return text.split("/", 1)[0].strip()
    return text


def provider_separation_ok(builder_provider: str,
                           reviewer_provider: str,
                           risk: str) -> Tuple[bool, str]:
    """Enforce provider separation for R2/R3 blocking review.

    R2/R3 blocking review requires reviewer family != builder
    family (family is the text before ``/``); same family is
    blocked. R0/R1 is advisory and always passes.
    """
    level = str(risk or "").upper()
    if level not in RISKS:
        level = "R1"
    if level in ("R0", "R1"):
        return True, "advisory: R0/R1 review needs no separation"
    if _family(builder_provider) == _family(reviewer_provider):
        return False, ("blocked: reviewer family %r equals builder "
                       "family %r at %s; blocking review must be "
                       "independent"
                       % (_family(reviewer_provider),
                          _family(builder_provider), level))
    return True, ("ok: reviewer family %r differs from builder "
                  "family %r at %s"
                  % (_family(reviewer_provider),
                     _family(builder_provider), level))


def owner_override_ok(override: Any) -> Tuple[bool, str]:
    """Honor an owner override explicitly, never implicitly.

    Honored ONLY when ``override`` carries owner ``kgsmith19``
    with a non-empty decision and a non-empty scope. Anything
    less (missing scope, empty decision, wrong owner) is
    refused.
    """
    if not isinstance(override, dict):
        return False, "refused: override must be an explicit mapping"
    owner = str(override.get("owner", ""))
    decision = str(override.get("decision", ""))
    scope = str(override.get("scope", ""))
    if owner != OWNER_LOGIN:
        return False, ("refused: owner %r is not %r; only the owner "
                       "may override" % (owner, OWNER_LOGIN))
    if not decision.strip():
        return False, "refused: decision must be a non-empty string"
    if not scope.strip():
        return False, "refused: scope must be a non-empty string"
    return True, ("honored: explicit owner override for scope %r"
                  % scope[:120])


def inherit(child_role: str,
            parent_receipts: Any) -> List[Dict[str, Any]]:
    """Derive child receipts for one granted role (no escalation).

    The child gets receipts ONLY for ``child_role`` entries
    derivable from the parent set; each child receipt carries
    ``via: <parent agent>`` and no role the parent did not hold.
    A parent that cannot delegate yields an empty list.
    """
    if child_role not in ROLES:
        return []
    if not isinstance(parent_receipts, list):
        return []
    children: List[Dict[str, Any]] = []
    for receipt in parent_receipts:
        if not isinstance(receipt, dict):
            continue
        if str(receipt.get("role", "")) != child_role:
            continue
        parent_agent = str(receipt.get("agent", ""))
        child = {
            "role": child_role,
            "agent": str(receipt.get("agent", "")),
            "provider": str(receipt.get("provider", "")),
            "head": str(receipt.get("head", "")),
            "seq": int(receipt.get("seq", 1))
            if str(receipt.get("seq", "1")).lstrip("-").isdigit()
            else 1,
            "granted_by": parent_agent,
            "via": parent_agent,
        }
        children.append(child)
    return children


def authorize(role: str, path: str, receipt: Any = None, *,
              current_head: Any = None) -> AuthDecision:
    """Authorize one write for one role against one receipt.

    With a receipt, freshness and role match are enforced before
    the path matrix; without one, only the path matrix applies.
    Pure data, no I/O.
    """
    if role not in ROLES:
        return AuthDecision(
            allowed=False, rule="unknown-role",
            finding=_make_finding(
                "unknown-role",
                "unknown role %r: role is one of %s"
                % (str(role), ", ".join(ROLES)),
                str(path)))
    receipts = [receipt] if receipt is not None else []
    head = (str(current_head) if current_head is not None
            else (str(receipt.get("head", ""))
                  if isinstance(receipt, dict) else None))
    return check_write(role, receipts, path, current_head=head)


def check_write(role: str, receipts: Any, path: str, *,
                current_head: Any = None) -> AuthDecision:
    """Authorize one write: receipt freshness, role match, path.

    The receipt must be fresh (head matches ``current_head``
    when given) and must carry the requested role
    (self-promotion refused); then the path is checked against
    frozen roots, forbidden paths, and write roots. Pure data,
    no I/O.
    """
    if role not in ROLES:
        return AuthDecision(
            allowed=False, rule="unknown-role",
            finding=_make_finding(
                "unknown-role",
                "unknown role %r: role is one of %s"
                % (str(role), ", ".join(ROLES)),
                str(path)))
    if not isinstance(receipts, list) or not receipts:
        return AuthDecision(
            allowed=False, rule="no-receipt",
            finding=_make_finding(
                "no-receipt",
                "no receipt for role %r: present a fresh %s receipt"
                % (role, role),
                str(path)))
    matching = [r for r in receipts
                if isinstance(r, dict)
                and str(r.get("role", "")) == role]
    if not matching:
        held = sorted({str(r.get("role", "?")) for r in receipts
                       if isinstance(r, dict)})
        return AuthDecision(
            allowed=False, rule="self-promotion",
            finding=_make_finding(
                "self-promotion",
                "role %r holds %s: a %s receipt cannot authorize "
                "a %s write"
                % (role, "+".join(held) or "nothing", "+".join(held)
                   or "nothing", role),
                str(path)))
    receipt = matching[0]
    if current_head is not None \
            and str(receipt.get("head", "")) != str(current_head):
        return AuthDecision(
            allowed=False, rule="stale-receipt",
            finding=_make_finding(
                "stale-receipt",
                "stale receipt: head %r != current head %r; "
                "re-issue at the current head"
                % (str(receipt.get("head", "")),
                   str(current_head)),
                str(path)))
    normalized, traversal = _normalize_path(path)
    if traversal:
        return AuthDecision(
            allowed=False, rule="path-traversal",
            finding=_make_finding(
                "path-traversal",
                "path traversal: %r escapes its root; normalize "
                "before authorizing" % str(path),
                str(path)))
    if _under_any(normalized, FROZEN_ROOTS) \
            or normalized == "Canonical/corpus":
        return AuthDecision(
            allowed=False, rule="frozen-root",
            finding=_make_finding(
                "frozen-root",
                "frozen corpus: %r sits under Canonical/corpus/; "
                "frozen corpora are immutable to all roles"
                % normalized,
                str(path)))
    if _under_any(normalized,
                  FORBIDDEN_PATHS.get(role, ())):
        return AuthDecision(
            allowed=False, rule="forbidden-path",
            finding=_make_finding(
                "forbidden-path",
                "role %r may not write %r: outside its authorized "
                "roots" % (role, normalized),
                str(path)))
    if _under_any(normalized, WRITE_PATHS.get(role, ())):
        return AuthDecision(allowed=True, rule="write-root",
                            finding=None)
    return AuthDecision(
        allowed=False, rule="forbidden-path",
        finding=_make_finding(
            "forbidden-path",
            "role %r may not write %r: outside its authorized "
            "roots" % (role, normalized),
            str(path)))


def evaluate_canary(entry: Dict[str, Any]) -> AuthDecision:
    """Compute the authorization decision for one frozen canary."""
    entry = entry if isinstance(entry, dict) else {}
    role = str(entry.get("role", ""))
    path = str(entry.get("path", ""))
    if "override" in entry:
        ok, reason = owner_override_ok(entry.get("override"))
        if ok:
            return AuthDecision(allowed=True, rule="owner-override",
                                finding=None)
        return AuthDecision(
            allowed=False, rule="owner-override",
            finding=_make_finding("owner-override", reason, path))
    if "parent_roles" in entry:
        parents = entry.get("parent_roles")
        parent_receipts: List[Dict[str, Any]] = []
        if isinstance(parents, list):
            for index, parent_role in enumerate(parents):
                parent_receipts.append(issue_receipt(
                    str(parent_role), "parent-1",
                    "anthropic/claude",
                    str(entry.get("current_head",
                                  entry.get("receipt_head",
                                            "canary-head"))),
                    index + 1))
        child = inherit(role, parent_receipts)
        return check_write(
            role, child, path,
            current_head=entry.get("current_head",
                                   entry.get("receipt_head",
                                             "canary-head")))
    receipt_role = str(entry.get("receipt_role",
                                 entry.get("role", "")))
    receipt_head = str(entry.get("receipt_head",
                                 entry.get("current_head",
                                           "canary-head")))
    current = entry.get("current_head", receipt_head)
    receipt = issue_receipt(
        receipt_role, str(entry.get("agent", "canary-agent")),
        str(entry.get("provider", "anthropic/claude")),
        receipt_head, int(entry.get("seq", 1))
        if str(entry.get("seq", "1")).lstrip("-").isdigit() else 1)
    return check_write(role, [receipt], path, current_head=current)


def validate_canaries(corpus: Any) -> Tuple[List[str],
                                            List[Dict[str, Any]]]:
    """Validate the frozen role-authority canary oracle.

    Returns (findings, entries); an empty findings list means the
    corpus is a valid frozen oracle: frozen marker set, stable
    provenance, unique well-formed IDs, all 8 roles covered, and
    every entry computing its expected outcome
    (allowed or refused-with-expected_rule).
    """
    entries: List[Dict[str, Any]] = []
    if isinstance(corpus, dict):
        raw = corpus.get("entries")
        if corpus.get("_frozen") is not True:
            return (["canary corpus is not frozen: set "
                     "\"_frozen\": true"], [])
        provenance = str(corpus.get("_provenance", ""))
        if "Stage 30 #121" not in provenance:
            return (["canary corpus provenance must name "
                     "\"Stage 30 #121\""], [])
        entries = raw if isinstance(raw, list) else []
    elif isinstance(corpus, list):
        entries = corpus
    else:
        return (["canary corpus must be a JSON object with an "
                 "'entries' array (or a bare array)"], [])
    findings: List[str] = []
    seen: Dict[str, int] = {}
    roles_found = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            findings.append("entries[%d] is not a mapping" % index)
            continue
        cid = str(entry.get("id", ""))
        if not _CANARY_ID_RE.match(cid):
            findings.append(
                "entry %r: id is not role-authority.<class>.<nn>"
                % cid)
        if cid in seen:
            findings.append(
                "duplicate canary id %s (entries %d and %d)"
                % (cid, seen[cid], index))
        else:
            seen[cid] = index
        role = str(entry.get("role", ""))
        if role not in ROLES:
            findings.append(
                "entry %s: unknown role %r" % (cid, role))
        else:
            roles_found.add(role)
        expected = entry.get("expected")
        if expected not in ("allowed", "refused"):
            findings.append(
                "entry %s: expected must be allowed|refused" % cid)
        expected_rule = str(entry.get("expected_rule", ""))
        if expected_rule not in RULES:
            findings.append(
                "entry %s: unknown expected_rule %r" % (cid,
                                                        expected_rule))
        if not str(entry.get("note", "")).strip():
            findings.append(
                "entry %s: a one-line adjudication note is required"
                % cid)
        if not str(entry.get("path", "")).strip():
            findings.append(
                "entry %s: path must be a non-empty string" % cid)
        if expected in ("allowed", "refused") \
                and expected_rule in RULES:
            decision = evaluate_canary(entry)
            if expected == "allowed" and not decision.allowed:
                findings.append(
                    "entry %s: expected allowed but computed refused "
                    "(%s)" % (cid, decision.rule))
            elif expected == "refused" and decision.allowed:
                findings.append(
                    "entry %s: expected refused but computed allowed"
                    % cid)
            elif decision.rule != expected_rule:
                findings.append(
                    "entry %s: expected_rule %r != computed %r"
                    % (cid, expected_rule, decision.rule))
    for role in ROLES:
        if role not in roles_found:
            findings.append(
                "role %r has no canaries (all 8 roles are required)"
                % role)
    return findings, entries
