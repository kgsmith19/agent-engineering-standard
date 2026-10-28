"""Std#300 runtime-neutral role/authority contract (RED stub).

Temporary scaffold so the conformance tests fail on assertions, not
imports. Replaced by the real decide() in the GREEN commit.
"""

import role_authority as ra  # noqa: F401  (reused path and provider rules)

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
)


def decide(grant, action, *, now, current_head, owner=None,
           override=None, other_grants=()):
    """Stub: refuses everything with no rule id."""
    return False, []
