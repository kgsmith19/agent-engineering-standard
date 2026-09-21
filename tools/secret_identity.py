"""T04 Standard half: secret-store and identity contracts (values-only).

The secret-store contract is **location-agnostic**: acquire, expire,
rotate, and verify capabilities are expressed against any store, with
Infisical recorded as the shipped default binding — never a second
production vault. Identity separation binds six distinct, independently
attributable dimensions (role, task, harness, model, environment,
service principal); provider-alias normalization maps model-provider
aliases to canonical providers without ever conflating the harness
dimension with the model dimension. Every credential acquisition
records provenance metadata only — provider, role, scope, expiry —
and tokens are short-lived with explicit expiry.

The values-only rule (plan §14/D5) is absolute: refs and metadata
only — no secret value is retrieved, stored, logged, or required by
any contract key. A secret-shaped value under any contract key is
rejected. There is no long-lived credential issuance and no
owner-fallback credential path; break-glass is solely the owner
(``kgsmith19``) via the owner administrative path. INT-07 (scoped
secret-ref + recovery contract) is referenced as a proposal label
until its native number exists; INT-08/INT-09 are linked natively in
their owning repos, never duplicated here.

Pure functions: no I/O, no network, no value handling — data in,
violations out. Frozen rejection rules, stable output order.
"""

import re
from typing import Any, Dict, List, Tuple

DEFAULT_BINDING = "infisical"

STORE_CAPABILITIES = ("acquire", "expire", "rotate", "verify")

IDENTITY_DIMENSIONS = (
    "role", "task", "harness", "model", "env", "service_principal",
)

PROVENANCE_FIELDS = ("provider", "role", "scope", "expiry")

# Short-lived tokens only: an explicit expiry is required and the
# time-to-live may never exceed one hour.
SHORT_LIVED_MAX_SECONDS = 3600

# Frozen model-provider alias table: aliases normalize to real
# providers for the MODEL dimension only. The harness dimension is
# never rewritten through this table (harness != model).
PROVIDER_ALIASES = {
    "anthropic": "anthropic",
    "claude": "anthropic",
    "openai": "openai",
    "openai-compatible": "openai",
    "gpt": "openai",
    "google": "google",
    "gemini": "google",
    "kilo": "kilo",
}

_HARNESS_BINDINGS = (
    "github-actions", "local-worktrees", "standardctl",
    "pi", "claude-code", "codex",
)

_REF_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

# Secret-shaped values: token prefixes, URLs with credentials, long
# base64/hex runs, or anything with embedded whitespace. Contract
# keys carry refs and metadata only.
_SECRET_SHAPED_RE = re.compile(
    r"^(ghp_|gho_|github_pat_|sk-|xox[bpas]-|AKIA|eyJ)"
    r"|://[^/\s:]+:[^@\s]+@"
    r"|^[A-Za-z0-9+/]{40,}={0,2}$"
    r"|^[a-f0-9]{64,}$"
    r"|\s"
)


def is_secret_shaped(value: Any) -> bool:
    """True when a value looks like a secret, never a ref."""
    if not isinstance(value, str):
        return False
    return bool(_SECRET_SHAPED_RE.search(value))


def _walk_strings(value: Any) -> List[str]:
    """Collect string leaves of a nested mapping/list."""
    found: List[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            found.extend(_walk_strings(key))
            found.extend(_walk_strings(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_walk_strings(item))
    elif isinstance(value, str):
        found.append(value)
    return found


def normalize_provider_alias(alias: Any) -> str:
    """Return the canonical model-provider for one alias.

    Unknown aliases normalize to their lowercase kebab ref without
    conflation: this function never rewrites a harness binding —
    the harness dimension is separate (``check_alias_separation``).
    """
    text = str(alias or "").strip().lower()
    return PROVIDER_ALIASES.get(text, text)


def check_alias_separation(harness: Any, model: Any) -> List[str]:
    """Return violations for harness/model conflation; empty = clean.

    The harness dimension and the model dimension stay distinct: a
    harness binding must never be normalized into a model provider,
    and a model label must never satisfy a harness role (model-label
    spoofing never satisfies separation).
    """
    violations: List[str] = []
    harness_text = str(harness or "").strip().lower()
    model_text = str(model or "").strip().lower()
    if not harness_text or not model_text:
        violations.append(
            "identity separation requires both a harness and a model "
            "dimension; neither may be empty")
        return violations
    if harness_text == model_text:
        violations.append(
            "harness/model conflation: harness %r equals model %r; "
            "the harness dimension is distinct from the model "
            "dimension" % (harness_text, model_text))
    if harness_text in PROVIDER_ALIASES and \
            normalize_provider_alias(harness_text) != harness_text \
            and harness_text in ("claude", "gpt", "gemini"):
        violations.append(
            "harness/model conflation: harness binding %r is a "
            "model-provider label, not a harness; harnesses are "
            "named agents (claude-code, codex, pi), never provider "
            "aliases" % harness_text)
    return violations


def check_identity_separation(identity: Any) -> List[str]:
    """Return violations for one identity record; empty means bound.

    All six dimensions must be present, non-empty, and mutually
    distinct. A model label spoofing another dimension (e.g., role
    set to a provider alias) is rejected.
    """
    record = identity if isinstance(identity, dict) else {}
    violations: List[str] = []
    values: Dict[str, str] = {}
    for dimension in IDENTITY_DIMENSIONS:
        raw = record.get(dimension)
        text = str(raw or "").strip()
        if not text:
            violations.append(
                "identity dimension %r is missing: all six dimensions "
                "(role, task, harness, model, env, service_principal) "
                "are required" % dimension)
            continue
        values[dimension] = text.lower()
    for dimension, value in values.items():
        if dimension in ("harness", "model", "env"):
            continue
        if value in PROVIDER_ALIASES and dimension in (
                "role", "task", "service_principal"):
            violations.append(
                "model-label spoofing: %s %r is a provider alias, "
                "never an identity dimension value" % (dimension,
                                                       value))
    distinct = list(values.values())
    if len(set(distinct)) != len(distinct):
        violations.append(
            "identity dimensions are not independently attributable: "
            "two or more dimensions share one value")
    return violations


def check_provenance(record: Any) -> List[str]:
    """Return violations for one provenance record; empty = clean.

    Provenance is metadata only: provider, role, scope, and expiry
    must be present, the token must be short-lived with an explicit
    expiry in seconds (0 < ttl <= SHORT_LIVED_MAX_SECONDS), and no
    field may carry a secret value.
    """
    item = record if isinstance(record, dict) else {}
    violations: List[str] = []
    for field in PROVENANCE_FIELDS:
        if field not in item or not str(item.get(field, "")).strip():
            violations.append(
                "provenance field %r is required: every credential "
                "acquisition names provider, role, scope, and expiry "
                "as metadata only" % field)
    ttl = item.get("ttl_seconds")
    if ttl is None:
        violations.append(
            "short-lived tokens only: an explicit ttl_seconds expiry "
            "is required (no long-lived credentials)")
    elif not isinstance(ttl, int) or isinstance(ttl, bool) \
            or ttl <= 0 or ttl > SHORT_LIVED_MAX_SECONDS:
        violations.append(
            "short-lived tokens only: ttl_seconds %r is outside "
            "1..%d" % (ttl, SHORT_LIVED_MAX_SECONDS))
    for key, value in item.items():
        if is_secret_shaped(value):
            violations.append(
                "values-only rule: provenance key %r carries a "
                "secret-shaped value; refs and metadata only" % key)
    return violations


def check_store_contract(store: Any) -> List[str]:
    """Return violations for one secret-store contract; empty = bound.

    The contract is location-agnostic: it must declare capabilities
    from the frozen store set, keep the binding a ref (Infisical is
    the shipped default), stay short-lived, and never carry a secret
    value, an owner-fallback path, or a second production vault.
    """
    record = store if isinstance(store, dict) else {}
    violations: List[str] = []
    binding = str(record.get("binding", "")).strip()
    if not binding:
        violations.append(
            "secret-store contract needs a binding ref (the shipped "
            "default is %r); the binding is a ref, never a value"
            % DEFAULT_BINDING)
    elif not _REF_RE.match(binding):
        violations.append(
            "secret-store binding %r is not a reference: values are "
            "refs only, never secret values" % binding[:12])
    capabilities = record.get("capabilities")
    if not isinstance(capabilities, list) or not capabilities:
        violations.append(
            "secret-store contract must declare capabilities from: "
            + ", ".join(STORE_CAPABILITIES))
    else:
        for capability in capabilities:
            if str(capability) not in STORE_CAPABILITIES:
                violations.append(
                    "unknown store capability %r: the location-"
                    "agnostic set is %s"
                    % (str(capability),
                       ", ".join(STORE_CAPABILITIES)))
    if record.get("owner_fallback"):
        violations.append(
            "owner-fallback credential path is forbidden: break-glass "
            "is solely kgsmith19 via the owner admin path, never a "
            "contract capability")
    ttl = record.get("max_ttl_seconds")
    if ttl is None:
        violations.append(
            "short-lived tokens only: the contract must cap token "
            "lifetime with max_ttl_seconds")
    elif not isinstance(ttl, int) or isinstance(ttl, bool) \
            or ttl <= 0 or ttl > SHORT_LIVED_MAX_SECONDS:
        violations.append(
            "short-lived tokens only: max_ttl_seconds %r is outside "
            "1..%d" % (ttl, SHORT_LIVED_MAX_SECONDS))
    for key, value in record.items():
        if key in ("max_ttl_seconds",):
            continue
        if is_secret_shaped(value):
            violations.append(
                "values-only rule: store-contract key %r carries a "
                "secret-shaped value; refs and metadata only" % key)
    for text in _walk_strings(record.get("notes", "")):
        if is_secret_shaped(text):
            violations.append(
                "values-only rule: contract notes carry a "
                "secret-shaped value")
            break
    return violations


def provenance(provider: Any, role: Any, scope: Any,
               ttl_seconds: int) -> Dict[str, Any]:
    """Mint one provenance metadata record (no I/O, no values)."""
    return {
        "provider": str(provider),
        "role": str(role),
        "scope": str(scope),
        "expiry": "ttl_seconds",
        "ttl_seconds": int(ttl_seconds),
    }


def validate_contract_corpus(corpus: Any) -> Tuple[List[str], List[Any]]:
    """Validate the frozen contract fixture oracle.

    Returns (findings, entries); empty findings means every entry
    reproduces its expected target and violations and the corpus
    covers all four contract surfaces (store, identity, alias,
    provenance).
    """
    entries = corpus.get("entries") if isinstance(corpus, dict) \
        else corpus
    if isinstance(corpus, dict) and corpus.get("_frozen") is not True:
        return (["contract corpus is not frozen: set "
                 "\"_frozen\": true"], [])
    if isinstance(corpus, dict):
        provenance_text = str(corpus.get("_provenance", ""))
        if "Stage T04 #201" not in provenance_text:
            return (["contract corpus provenance must name "
                     "\"Stage T04 #201\""], [])
    if not isinstance(entries, list):
        return (["contract corpus must hold an 'entries' array"], [])
    findings: List[str] = []
    checkers = {
        "store": check_store_contract,
        "identity": check_identity_separation,
        "alias": lambda entry: check_alias_separation(
            entry.get("harness"), entry.get("model")),
        "provenance": check_provenance,
    }
    seen: set = set()
    covered: set = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            findings.append("entries[%d] is not a mapping" % index)
            continue
        cid = str(entry.get("id", ""))
        if not re.match(r"^secret-ident\.[a-z-]+\.\d{2}$", cid):
            findings.append("entry %r: id is not "
                            "secret-ident.<class>.<nn>" % cid)
        if cid in seen:
            findings.append("duplicate entry id %s" % cid)
        seen.add(cid)
        target = str(entry.get("target", ""))
        if target not in checkers:
            findings.append("entry %s: unknown target %r"
                            % (cid, target))
            continue
        covered.add(target)
        expected = entry.get("expected_violation_fragment", "")
        violations = checkers[target](entry.get("record", entry))
        if expected:
            if not any(expected in v for v in violations):
                findings.append(
                    "entry %s: expected violation fragment %r not "
                    "computed (got %r)"
                    % (cid, expected,
                       [v[:60] for v in violations]))
        elif violations:
            findings.append(
                "entry %s: expected a clean contract, got %r"
                % (cid, [v[:60] for v in violations]))
    for target in sorted(checkers):
        if target not in covered:
            findings.append("target %r has no entries" % target)
    return findings, entries
