"""Std#300 runtime-neutral role/authority contract.

The Standard pins WHAT MUST BE PROVEN for an agent action, never how
the agent is hosted. ``decide`` answers one question: may this grant
authorize this action now? It is pure data (no I/O, no runtime) and
reuses the path, role, provider-separation and owner-override rules of
``tools/role_authority.py``. It never imports or depends on any
external agent system.

Fail closed: any missing, extra or invalid field refuses with a rule
id. Rule ids are returned in ``RULES`` order; an empty list with
``allowed`` True is the only allow outcome. ``action-invalid`` and
``owner-override`` are the two ids beyond the contract's grant rules:
the first refuses a malformed action, the second an owner override that
is not honored.

Std#301 adds ``record``, which wraps ``decide`` in a collaboration
receipt. The three ids appended to ``RULES`` are ``privilege-escalation``
(a delegated grant from a grantor who holds no such duty), ``parallel-write``
(overlapping builder or remediator scope on one head) and
``missing-evidence`` (a verifier or reviewer with an unproven acceptance
id). Specialty is recorded on the receipt only, never as authority.
"""

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import role_authority as ra

RULES = (
    "grant-invalid",
    "action-invalid",
    "grant-expired",
    "stale-head",
    "self-grant",
    "unverified-provenance",
    "out-of-scope",
    "forbidden-self-review",
    "unauthorized-github-write",
    "owner-override",
    "privilege-escalation",
    "parallel-write",
    "missing-evidence",
)

KINDS = ("write", "review", "verify", "post", "mutate_github")

# An owner override may waive these two rules and nothing else.
WAIVABLE = ("grant-expired", "stale-head")

MAX_WINDOW_SECONDS = 3600

GRANT_KEYS = (
    "actor_id",
    "run_id",
    "duty",
    "scope",
    "head_sha",
    "provider",
    "provenance",
    "issued_at",
    "expires_at",
    "grantor",
)

OPTIONAL_GRANT_KEYS = ("github_identity",)

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


def _parse_ts(value: Any) -> Optional[datetime]:
    """Parse an ISO-8601 UTC 'Z' timestamp; None when malformed."""
    if not isinstance(value, str) or not _TS_RE.match(value):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc)
    except ValueError:
        return None


def _text(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _scope_prefixes(scope: Any) -> Optional[List[str]]:
    """Normalized scope prefixes, or None when the scope is malformed."""
    if not isinstance(scope, (list, tuple)) or not scope:
        return None
    prefixes: List[str] = []
    for entry in scope:
        if not _text(entry):
            return None
        normalized, traversal = ra._normalize_path(entry)
        if traversal or not normalized:
            return None
        prefixes.append(normalized)
    return prefixes


def _grant_malformed(grant: Any) -> bool:
    """True when a grant is missing, has extra keys, or is mistyped."""
    if not isinstance(grant, dict):
        return True
    if set(grant) - set(GRANT_KEYS) - set(OPTIONAL_GRANT_KEYS):
        return True
    if any(key not in grant for key in GRANT_KEYS):
        return True
    if not (_text(grant["actor_id"]) and _text(grant["run_id"])
            and _text(grant["grantor"])):
        return True
    if grant["duty"] not in ra.ROLES:
        return True
    if _scope_prefixes(grant["scope"]) is None:
        return True
    head = grant["head_sha"]
    if not (isinstance(head, str) and _SHA_RE.match(head)):
        return True
    provider = grant["provider"]
    if not isinstance(provider, dict) or set(provider) != {"family",
                                                          "model"}:
        return True
    if not (_text(provider["family"]) and _text(provider["model"])):
        return True
    provenance = grant["provenance"]
    if not isinstance(provenance, dict) or set(provenance) != {
            "source", "provider_observed"}:
        return True
    if not _text(provenance["source"]):
        return True
    if not isinstance(provenance["provider_observed"], str):
        return True
    issued = _parse_ts(grant["issued_at"])
    expires = _parse_ts(grant["expires_at"])
    if issued is None or expires is None:
        return True
    window = (expires - issued).total_seconds()
    if window <= 0 or window > MAX_WINDOW_SECONDS:
        return True
    if "github_identity" in grant \
            and not isinstance(grant["github_identity"], str):
        return True
    return False


def _action_malformed(action: Any) -> bool:
    """True when an action is not a known kind or has a bad path."""
    if not isinstance(action, dict):
        return True
    if set(action) - {"kind", "path", "risk"}:
        return True
    if action.get("kind") not in KINDS:
        return True
    if "path" in action and not isinstance(action["path"], str):
        return True
    return False


def _risk(action: dict) -> str:
    """Risk level; anything unrecognized is treated as R3."""
    level = action.get("risk")
    if isinstance(level, str) and level in ra.RISKS:
        return level
    return "R3"


def _owner_override_honored(override: Any, owner: Any) -> bool:
    """An override is honored only when role_authority accepts it and
    it names the owner the caller is deciding for."""
    ok, _ = ra.owner_override_ok(override)
    if not ok:
        return False
    return owner is None or str(override.get("owner")) == str(owner)


def _overlaps(first: str, second: str) -> bool:
    """True when one normalized scope prefix contains the other."""
    return ra._matches_prefix(first, second) or ra._matches_prefix(
        second, first)


def decide(grant: Any, action: Any, *, now: Any, current_head: Any,
           owner: Any = None, override: Any = None,
           other_grants: Any = (), delegated: bool = False
           ) -> Tuple[bool, List[str]]:
    """Decide whether one grant authorizes one action right now.

    ``now`` is an ISO-8601 UTC 'Z' string; an unparseable clock cannot
    prove the grant is live, so it refuses as grant-expired.
    ``owner`` is the owner login the decision is made for; the
    self-grant exemption applies only when it is the owner login.
    ``other_grants`` are the other grants in the same run; each must be
    well-formed or the decision refuses as grant-invalid.

    Returns ``(allowed, rules)``.
    """
    if not isinstance(other_grants, (list, tuple)) \
            or _grant_malformed(grant) \
            or any(_grant_malformed(other) for other in other_grants):
        return False, ["grant-invalid"]
    if _action_malformed(action):
        return False, ["action-invalid"]

    rules = set()
    actor = grant["actor_id"]
    duty = grant["duty"]
    head = grant["head_sha"]
    kind = action["kind"]
    risk = _risk(action)

    issued = _parse_ts(grant["issued_at"])
    expires = _parse_ts(grant["expires_at"])
    live_at = _parse_ts(now)
    if live_at is None or live_at >= expires or live_at < issued:
        rules.add("grant-expired")

    if head != current_head:
        rules.add("stale-head")

    grantor = grant["grantor"]
    if grantor == actor and not (owner == ra.OWNER_LOGIN
                                 and grantor == owner):
        rules.add("self-grant")

    observed = grant["provenance"]["provider_observed"]
    if not _text(observed) or ra._family(observed) != ra._family(
            grant["provider"]["family"]):
        rules.add("unverified-provenance")

    path = action.get("path")
    if path is None:
        if kind == "write":
            rules.add("out-of-scope")
    else:
        normalized, traversal = ra._normalize_path(path)
        in_scope = not traversal and any(
            ra._matches_prefix(normalized, prefix)
            for prefix in _scope_prefixes(grant["scope"]))
        receipt = ra.issue_receipt(duty, actor,
                                   grant["provider"]["family"], head, 1)
        matrix = ra.check_write(duty, [receipt], path,
                                current_head=head)
        if not (in_scope and matrix.allowed):
            rules.add("out-of-scope")

    if kind in ("review", "verify"):
        if duty == "builder":
            rules.add("forbidden-self-review")
        for other in other_grants:
            if other["duty"] != "builder" or other["head_sha"] != head:
                continue
            separated, _ = ra.provider_separation_ok(
                other["provider"]["family"],
                grant["provider"]["family"], risk)
            if other["actor_id"] == actor or not separated:
                rules.add("forbidden-self-review")

    if kind == "write":
        # safe_parallelism's same-files rule is exact-path only; this
        # contract compares scope prefixes, so src/ and src/api/ collide.
        mine = _scope_prefixes(grant["scope"])
        for other in other_grants:
            if other["actor_id"] == actor or other["head_sha"] != head:
                continue
            if other["duty"] in ("builder", "remediator") and any(
                    _overlaps(a, b) for a in mine
                    for b in _scope_prefixes(other["scope"])):
                rules.add("parallel-write")

    if delegated:
        # "controller" is not in ROLES, so the grantor must be the owner
        # or hold a grant of the same duty in this run.
        is_owner = owner == ra.OWNER_LOGIN and grantor == owner
        held = any(other["actor_id"] == grantor and other["duty"] == duty
                   for other in other_grants)
        if not (is_owner or held):
            rules.add("privilege-escalation")

    if kind in ("post", "mutate_github") \
            and not _text(grant.get("github_identity")):
        rules.add("unauthorized-github-write")

    if override is not None:
        if _owner_override_honored(override, owner):
            rules -= set(WAIVABLE)
        else:
            rules.add("owner-override")

    ordered = [rule for rule in RULES if rule in rules]
    return not ordered, ordered


def _artifacts_malformed(items: Any) -> bool:
    """True unless items is a list of {path, sha256} artifacts."""
    return not isinstance(items, (list, tuple)) or any(
        not isinstance(item, dict) or set(item) != {"path", "sha256"}
        or not _text(item["path"]) or not isinstance(item["sha256"], str)
        or not _HASH_RE.match(item["sha256"]) for item in items)


def _claim_malformed(claim: Any) -> bool:
    """True unless a claim has id, result and a list of artifact paths."""
    return (not isinstance(claim, dict) or not _text(claim.get("id"))
            or not _text(claim.get("result"))
            or not isinstance(claim.get("artifacts"), (list, tuple))
            or not all(_text(path) for path in claim["artifacts"]))


def _record_malformed(specialty: Any, acceptance_ids: Any, claims: Any,
                      inputs: Any, outputs: Any) -> bool:
    return ((specialty is not None and not _text(specialty))
            or not isinstance(acceptance_ids, (list, tuple))
            or not all(_text(item) for item in acceptance_ids)
            or not isinstance(claims, (list, tuple))
            or any(_claim_malformed(claim) for claim in claims)
            or _artifacts_malformed(inputs) or _artifacts_malformed(outputs))


def _unproven(acceptance_ids: Any, claims: Any, outputs: Any) -> bool:
    """True when no acceptance id is named, or one lacks a passing claim
    that lists an output artifact path."""
    if not acceptance_ids:
        return True
    produced = {artifact["path"] for artifact in outputs}
    return any(
        not any(claim["id"] == cid and claim["result"] == "pass"
                and produced & set(claim["artifacts"]) for claim in claims)
        for cid in acceptance_ids)


def _as_list(value: Any) -> list:
    return list(value) if isinstance(value, (list, tuple)) else []


def record(grant: Any, action: Any, *, task: Any, now: Any,
           current_head: Any, acceptance_ids: Any = (), claims: Any = (),
           input_artifacts: Any = (), output_artifacts: Any = (),
           specialty: Any = None, owner: Any = None, override: Any = None,
           other_grants: Any = (), delegated: bool = False
           ) -> Dict[str, Any]:
    """Decide one action and return its collaboration receipt.

    ``decide`` supplies the grant rules. A verifier or reviewer that
    would otherwise allow is refused as missing-evidence when an
    acceptance id has no passing claim listing an output artifact.
    Malformed record inputs refuse as action-invalid. ``specialty`` is
    recorded on the receipt only; it never grants authority.
    """
    allowed, decided = decide(
        grant, action, now=now, current_head=current_head, owner=owner,
        override=override, other_grants=other_grants, delegated=delegated)
    rules = set(decided)
    if _record_malformed(specialty, acceptance_ids, claims,
                         input_artifacts, output_artifacts):
        rules.add("action-invalid")
    elif allowed and grant["duty"] in ("verifier", "reviewer") \
            and _unproven(acceptance_ids, claims, output_artifacts):
        rules.add("missing-evidence")
    ordered = [rule for rule in RULES if rule in rules]
    fields = grant if isinstance(grant, dict) else {}
    return {
        "schema_version": 1,
        "task": task,
        "duty": fields.get("duty"),
        "specialty": specialty,
        "actor_id": fields.get("actor_id"),
        "run_id": fields.get("run_id"),
        "grantor": fields.get("grantor"),
        "provider": fields.get("provider"),
        "provenance": fields.get("provenance"),
        "scope": fields.get("scope"),
        "exact_sha": current_head,
        "input_artifacts": _as_list(input_artifacts),
        "output_artifacts": _as_list(output_artifacts),
        "acceptance_ids": _as_list(acceptance_ids),
        "claims": _as_list(claims),
        "decision": "refuse" if ordered else "allow",
        "rules": ordered,
        "decided_at": now,
    }
