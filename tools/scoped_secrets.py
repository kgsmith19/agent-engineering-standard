"""T22 Standard half: scoped secret references with independent recovery.

Secrets are referenced by role + environment scope (never by raw
value); every ref validates against a least-privilege scope
before use. Expired and denied refs are distinct explicit
fail-closed modes (denial never reported as absence, absence
never impersonates denial). Receipts, logs, artifacts, capsules,
and PR content contain no secret values — references and
metadata only. A documented recovery route independent of the
primary store session exists with break-glass solely kgsmith19
via the owner admin path, rehearsed by drill. The
migration-inventory schema is metadata-only (zero value
retrievals). Infisical stays the default binding with OIDC
seams; the #201 six-dimension separation holds; no second
production vault. D5 bounds are recorded before any gated live
change. Two native LINK follow-ups (INT-08 extensions,
INT-09 hyperbolic) are declared with owning repo + parent, to
be filed natively — never duplicated here.

Pure functions: no I/O, no network — data in, violations out.
No secret value is ever read, transported, stored, or printed.
Frozen rules, stable output order.
"""

from typing import Any, Dict, List, Optional, Tuple
import re

DEFAULT_BINDING = "infisical"

# Failure taxonomy: expired vs denied vs absent are distinct.
REF_FAILURES = ("expired", "denied", "absent")

# D5 bounds recorded before any gated live change.
D5_BOUNDS = (
    "retention-90-day",
    "git-immutable-history",
    "break-glass-kgsmith19",
    "offline-recovery-export",
)

# Native LINK follow-ups: declared here, filed natively.
LINK_FOLLOW_UPS = (
    ("INT-08", "kgsmith19/agent-extensions"),
    ("INT-09", "kgsmith19/hyperbolic-core"),
)

_SECRET_SHAPED_RE = re.compile(
    r"(ghp_|gho_|github_pat_|sk-|xox[bpas]-|AKIA|eyJ)"
    r"|://[^/\s:]+:[^@\s]+@"
    r"|[A-Za-z0-9+/]{40,}={0,2}"
    r"|[a-f0-9]{64,}"
    r"|\s")


def check_scoped_ref(ref: Any) -> List[str]:
    """Return violations for an unscoped secret reference.

    Every ref carries role + environment scope and validates
    against least privilege before use; an out-of-scope ref, a
    ref without scope, or a raw value as ref fails naming the
    ref.
    """
    violations: List[str] = []
    if not isinstance(ref, dict):
        return ["secret ref must be a mapping"]
    name = ref.get("ref", "?")
    if ref.get("raw_value"):
        return ["raw secret value as ref %r forbidden: refs "
                "only, never values" % (name,)]
    if not ref.get("role") or not ref.get("env"):
        violations.append(
            "ref %r missing role/env scope" % (name,))
    if ref.get("out_of_scope"):
        violations.append(
            "ref %r out of least-privilege scope: use refused"
            % (name,))
    return violations


def check_expiry_denial(ref: Any) -> List[str]:
    """Return violations for ambiguous ref failures.

    Expired and denied refs fail closed with distinct named
    modes; denial is never reported as absence and absence
    never impersonates denial; a valid ref passes.
    """
    violations: List[str] = []
    if not isinstance(ref, dict):
        return ["secret ref must be a mapping"]
    name = ref.get("ref", "?")
    if ref.get("expired"):
        violations.append(
            "ref %r expired: fail closed (distinct from denial)"
            % (name,))
    if ref.get("denied"):
        violations.append(
            "ref %r denied: fail closed (distinct from absence)"
            % (name,))
    if ref.get("reported_as") == "absent" and ref.get("denied"):
        violations.append(
            "ref %r denial reported as absence: forbidden" % (name,))
    if ref.get("reported_as") == "denied" and ref.get(
            "absent") and not ref.get("denied"):
        violations.append(
            "absence impersonates denial for %r: forbidden" % (name,))
    return violations


def check_no_raw_secrets(output: Any) -> List[str]:
    """Return violations when output carries secret values.

    Receipts/logs/artifacts/capsules/PR content hold references
    and metadata only; any secret-shaped leaf fails naming the
    leak. A planted-token canary passes only when redacted.
    """
    violations: List[str] = []
    leaves: List[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, str):
            leaves.append(value)

    walk(output)
    for leaf in leaves:
        if _SECRET_SHAPED_RE.search(leaf):
            violations.append(
                "raw secret value in output: refs and metadata "
                "only (redact values)")
            break
    return violations


def check_recovery_route(route: Any) -> List[str]:
    """Return violations for a dependent recovery route.

    The route is documented, independent of the primary store
    session, break-glass solely kgsmith19 via owner admin, and
    rehearsed by drill; any gap fails naming the gap.
    """
    violations: List[str] = []
    if not isinstance(route, dict):
        return ["recovery route must be a mapping"]
    if not route.get("documented"):
        violations.append("recovery route not documented")
    if not route.get("independent_of_primary"):
        violations.append(
            "recovery needs the primary session: independence "
            "required")
    if route.get("break_glass") != "kgsmith19-owner-admin":
        violations.append(
            "break-glass is solely kgsmith19 via owner admin "
            "(D5)")
    if not route.get("drill_recorded"):
        violations.append("recovery drill not recorded")
    return violations


def check_inventory_metadata(inventory: Any) -> List[str]:
    """Return violations for value-touching inventories.

    The migration inventory is metadata-only
    (names/roles/envs/expiry/scopes); any value retrieval,
    read, or write fails. Zero value retrievals in traces.
    """
    violations: List[str] = []
    if not isinstance(inventory, dict):
        return ["inventory must be a mapping"]
    if inventory.get("value_retrievals"):
        violations.append(
            "inventory retrieved secret values: metadata-only, "
            "zero value retrievals")
    return violations


def check_authority(config: Any) -> List[str]:
    """Return violations for authority drift.

    Infisical stays the default binding with OIDC seams; the
    six-dimension separation holds; no second production vault
    or new secret authority appears.
    """
    violations: List[str] = []
    if not isinstance(config, dict):
        return ["authority config must be a mapping"]
    if config.get("default_binding", DEFAULT_BINDING) != DEFAULT_BINDING:
        violations.append(
            "default binding %r != infisical: Infisical-first "
            "authority preserved" % (
                config.get("default_binding"),))
    if config.get("second_vault"):
        violations.append(
            "second production vault forbidden")
    if config.get("owner_fallback"):
        violations.append(
            "owner fallback in adapters forbidden: break-glass "
            "is owner-admin only, never a code path")
    return violations


def check_d5_bounds(record: Any) -> List[str]:
    """Return violations when a gated change skips D5 bounds.

    Any live credential change first records all four D5 bounds
    in its task body before the gated step runs; a missing
    bound blocks the step.
    """
    violations: List[str] = []
    if not isinstance(record, dict):
        return ["D5 record must be a mapping"]
    if not record.get("gated_change"):
        return []
    recorded = record.get("d5_recorded") or []
    for bound in D5_BOUNDS:
        if bound not in recorded:
            violations.append(
                "D5 bound %r not recorded before the gated step"
                % (bound,))
    return violations


def check_link_declaration(links: Any) -> List[str]:
    """Return violations for misfiled LINK follow-ups.

    Both LINKs are declared with owning repo + parent and filed
    natively later, each separately authorized; filing them here
    or duplicating their criteria fails.
    """
    violations: List[str] = []
    if not isinstance(links, list):
        return ["links must be a list"]
    seen = set()
    for link in links:
        if not isinstance(link, dict):
            violations.append("link must be a mapping: %r" % (link,))
            continue
        name = link.get("name")
        seen.add(name)
        if not link.get("owning_repo") or not link.get("parent"):
            violations.append(
                "link %r missing owning repo + parent" % (name,))
        if link.get("filed_here"):
            violations.append(
                "link %r filed here: file natively in the owning "
                "repo" % (name,))
    for name, _repo in LINK_FOLLOW_UPS:
        if name not in seen:
            violations.append(
                "link %r not declared" % (name,))
    return violations


def validate_secret_ref_corpus(corpus: Any) -> Tuple[List[str], List[Any]]:
    """Validate the frozen scoped-secret fixture oracle.

    Returns (findings, entries). Every entry carries an id, a
    target surface (scope, expiry, raw, recovery, inventory,
    authority, d5, links), a record, and the expected violation
    fragment ("" means clean).
    """
    if not isinstance(corpus, dict):
        return (["secret-ref corpus must be a mapping"], [])
    if corpus.get("_frozen") is not True:
        return (["secret-ref corpus is not frozen: set "
                 "\"_frozen\": true"], [])
    entries = corpus.get("entries")
    if not isinstance(entries, list):
        return (["secret-ref corpus entries must be a list"], [])
    checkers = {
        "scope": check_scoped_ref,
        "expiry": check_expiry_denial,
        "raw": check_no_raw_secrets,
        "recovery": check_recovery_route,
        "inventory": check_inventory_metadata,
        "authority": check_authority,
        "d5": check_d5_bounds,
        "links": check_link_declaration,
    }
    findings: List[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            findings.append("corpus entry is not a mapping: %r"
                            % (entry,))
            continue
        entry_id = entry.get("id", "?")
        target = entry.get("target")
        checker = checkers.get(target)
        if checker is None:
            findings.append(
                "entry %s has unknown target %r" % (entry_id, target))
            continue
        expected = entry.get("expected_violation_fragment", "")
        violations = checker(entry.get("record"))
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


def clean_ref() -> Dict[str, Any]:
    """One valid role/env scoped reference."""
    return {"ref": "deploy/prod/api-key", "role": "deploy",
            "env": "prod"}
