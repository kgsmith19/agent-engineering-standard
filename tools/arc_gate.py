"""Stage 34 Standard half: Arc A no-production-code phase gate.

Arc A is the complete no-production-code deliverable: Thin Spec,
critic-clean Spec (assured R2/R3) or compact scope, qualified Mold
with RED proof, independent attack report, meta-test-clean session,
valid verification portfolio, frozen Mold with live invalidation,
DoR READY, IMPLEMENT disposition, phase-pure prompt, Builder-ready
capsule, and a context budget that is not already in recovery.
Stage 34 (Risk R2) is the formal Arc A completion boundary: the
phase-state machine (SPEC_READY through IMPLEMENT_AUTHORIZED)
decides whether one Arc A packet may advance toward Builder
authorization (owned by Stage 35); it authorizes no production
write itself.

Packet shape (plain data; missing keys fall back to total
defaults, never a crash)::

    {"spec": {...},            # Thin Spec (spec_critic shape)
     "mold_run": {...},        # qualification run (mold_qualification shape)
     "attack": {...},          # attack report (attack_report shape here)
     "session": {...},         # Arc A session claims (meta_tests shape)
     "project": {...},         # portfolio project (verification_portfolio shape)
     "freeze_run": {...},      # freeze check (proof_invalidation shape)
     "receipt": {...},         # DoR receipt (ready shape)
     "observation": {...},     # disposition observation (disposition shape)
     "prompt": {...},          # prompt contract (prompt_contract shape)
     "capsule_fields": {...},  # capsule fields (capsule shape)
     "footprint": {...},       # context footprint (context_budget shape)
     "files_touched": [str, ...],  # every file this packet would write
     "protected_paths": [str, ...],
     "provider": str}          # provider of the Arc A packet

Phase states (frozen, in order):

- ``SPEC_READY`` — Thin Spec present with behavior claims; critic
  scope resolved (assured R2/R3 critiqued clean of blockers, or
  compact scope skipped).
- ``MOLD_QUALIFIED`` — SPEC_READY plus a qualified Mold receipt
  (verdict qualified, digest-bound) with true RED in the run.
- ``ATTACK_CLEAN`` — MOLD_QUALIFIED plus an independent attack
  report: a different-provider attacker reviewed the Mold and
  either found nothing material (``verdict: clean``) or found an
  issue the Mold owner then fixed and requalified
  (``verdict: fixed-requalified`` with a new receipt).
- ``CHECKPOINTED`` — ATTACK_CLEAN plus meta-test-clean session
  (no production writes, no protected-path touches, controls
  ran, hashes match), a valid portfolio (no blocker/major
  findings), and a frozen Mold whose cached proof still binds
  (no invalidation findings).
- ``IMPLEMENT_AUTHORIZED`` — CHECKPOINTED plus DoR READY,
  IMPLEMENT disposition, a phase-pure prompt, a Builder-ready
  capsule (builds within budget, no forbidden content), a
  context budget outside RECOVERY_REQUIRED, zero production
  writes in this packet, and zero protected-path touches.
  This is the ONLY state that may advance toward Builder
  authorization; the Builder gate itself is Stage 35.

Frozen rules (first listed first checked; findings appended in
this order, so output order is stable):

1. ``no-spec`` — no Thin Spec outcome or behavior claims.
2. ``spec-blocked`` — assured R2/R3 Spec with blocker findings
   (compact scope never blocks: skipped is clean).
3. ``mold-unqualified`` — no qualified Mold receipt, receipt
   fails binding, or the run lacks true RED.
4. ``attack-missing`` — no attack report, same provider as the
   Mold run (not independent), an unrecognized verdict, or a
   ``fixed-requalified`` claim without a fresh receipt.
5. ``session-dirty`` — meta-test repairs (production writes,
   protected touches, missing controls, hash mismatches).
6. ``portfolio-invalid`` — portfolio blocker/major findings
   (budget exceeded, missing command, excessive portfolio).
7. ``freeze-invalid`` — proof-invalidation findings (payload /
   intent / command drift, protected-path touch, stale reuse).
8. ``not-ready`` — DoR receipt repairs (missing fields,
   thinness large, wrong disposition, budget flags false).
9. ``disposition-blocked`` — disposition is not IMPLEMENT
   (NO_CHANGE, INSUFFICIENT_EVIDENCE, OWNER_DECISION) or the
   observation is incomplete.
10. ``prompt-impure`` — prompt contract repairs (multi-phase,
    stale hashes, unsupported authority).
11. ``capsule-unready`` — capsule build failure (missing
    fields, forbidden content, over budget).
12. ``budget-recovery`` — context budget in RECOVERY_REQUIRED.
13. ``production-write`` — this packet writes a production path
    (``src/``, ``packages/``, ``apps/``, ``services/``) or a
    protected path. Arc A authorizes no production writes.

``advance`` returns the furthest phase state whose every gate
holds plus the ordered findings (empty means
IMPLEMENT_AUTHORIZED). ``validate_arc_corpus`` checks the
frozen oracle. Pure functions: no I/O, deterministic in
their inputs.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

try:
    import spec_critic as _spec_critic
except Exception:
    _spec_critic = None

try:
    import mold_qualification as _mold_qualification
except Exception:
    _mold_qualification = None

try:
    import meta_tests as _meta_tests
except Exception:
    _meta_tests = None

try:
    import verification_portfolio as _verification_portfolio
except Exception:
    _verification_portfolio = None

try:
    import proof_invalidation as _proof_invalidation
except Exception:
    _proof_invalidation = None

try:
    import ready as _ready
except Exception:
    _ready = None

try:
    import disposition as _disposition
except Exception:
    _disposition = None

try:
    import prompt_contract as _prompt_contract
except Exception:
    _prompt_contract = None

try:
    import capsule as _capsule
except Exception:
    _capsule = None

try:
    import context_budget as _context_budget
except Exception:
    _context_budget = None

PHASES = (
    "SPEC_READY",
    "MOLD_QUALIFIED",
    "ATTACK_CLEAN",
    "CHECKPOINTED",
    "IMPLEMENT_AUTHORIZED",
)

RULES = (
    "no-spec",
    "spec-blocked",
    "mold-unqualified",
    "attack-missing",
    "session-dirty",
    "portfolio-invalid",
    "freeze-invalid",
    "not-ready",
    "disposition-blocked",
    "prompt-impure",
    "capsule-unready",
    "budget-recovery",
    "production-write",
)

PRODUCTION_PREFIXES = ("src/", "packages/", "apps/", "services/")

ATTACK_VERDICTS = ("clean", "fixed-requalified")


def _require(name: str, module: Any) -> Any:
    """Return the sibling tool module or raise a naming error.

    Sibling tools live side by side under tools/; the import
    happens once at module load (try/except, mirroring
    verification_portfolio's verification_mold import), and every
    gate consumes its sibling by reference through this helper —
    never a reimplementation, never a silent fallback. A missing
    sibling fails the gate loudly instead of passing it.
    """
    if module is None:
        raise RuntimeError(
            "arc-gate requires sibling tool %r on the import "
            "path (tools/): refusing to pass the gate without it"
            % name)
    return module

_ENTRY_ID_RE = None  # compiled lazily (stdlib re import below)

import re as _re

_ENTRY_ID_RE = _re.compile(r"^arc-a\.[a-z-]+\.\d{2}$")


def _make_finding(rule: str, message: str, excerpt: str,
                  severity: str = "blocker") -> Dict[str, str]:
    """Build one structured finding dict for a rejected packet."""
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
        repairs.append("finding rule %r is not a frozen Stage 34 "
                       "arc rule" % (rule,))
    if "severity" in finding and finding.get("severity") not in (
            "blocker", "major", "minor"):
        repairs.append("finding severity %r must be "
                       "blocker|major|minor" % (finding.get("severity"),))
    return repairs


def _matches_prefix(normalized: str, prefix: str) -> bool:
    """True when a normalized path sits at or under a prefix.

    Whole-segment matching only (``src/`` never matches
    ``src-evil/``); the bare directory itself also matches.
    """
    cleaned = str(normalized or "").replace("\\", "/").strip()
    cleaned = cleaned.lstrip("/")
    while "/./" in cleaned or cleaned.startswith("./"):
        cleaned = cleaned.replace("/./", "/")
        if cleaned.startswith("./"):
            cleaned = cleaned[2:]
    if not prefix.endswith("/"):
        prefix = prefix + "/"
    stem = prefix[:-1]
    if cleaned == stem:
        return True
    return cleaned.startswith(prefix)


def _under_any(normalized: str, prefixes: Any) -> bool:
    if not isinstance(prefixes, (list, tuple)):
        return False
    return any(isinstance(prefix, str)
               and _matches_prefix(normalized, prefix
                                   if prefix.endswith("/")
                                   else prefix + "/")
               for prefix in prefixes)


def _path_touched(touched: str, protected: str) -> bool:
    """True when a touched path is at or under a protected path."""
    clean = str(touched or "").replace("\\", "/").strip().lstrip("/")
    guard = str(protected or "").replace("\\", "/").strip().lstrip("/")
    if not clean or not guard:
        return False
    if clean == guard:
        return True
    return clean.startswith(guard.rstrip("/") + "/")


def _family(provider: Any) -> str:
    """Canonical provider family: text before '/' (or the whole)."""
    text = str(provider or "").strip().lower()
    if "/" in text:
        text = text.split("/", 1)[0]
    return text


def _normalize_packet(packet: Any) -> Dict[str, Any]:
    """Fill total defaults so partial input never crashes."""
    packet = packet if isinstance(packet, dict) else {}
    files = packet.get("files_touched")
    protected = packet.get("protected_paths")
    return {
        "spec": dict(packet.get("spec"))
        if isinstance(packet.get("spec"), dict) else {},
        "mold_run": dict(packet.get("mold_run"))
        if isinstance(packet.get("mold_run"), dict) else {},
        "attack": dict(packet.get("attack"))
        if isinstance(packet.get("attack"), dict) else {},
        "session": dict(packet.get("session"))
        if isinstance(packet.get("session"), dict) else {},
        "project": dict(packet.get("project"))
        if isinstance(packet.get("project"), dict) else {},
        "freeze_run": dict(packet.get("freeze_run"))
        if isinstance(packet.get("freeze_run"), dict) else {},
        "receipt": dict(packet.get("receipt"))
        if isinstance(packet.get("receipt"), dict) else {},
        "observation": dict(packet.get("observation"))
        if isinstance(packet.get("observation"), dict) else {},
        "prompt": dict(packet.get("prompt"))
        if isinstance(packet.get("prompt"), dict) else {},
        "capsule_fields": dict(packet.get("capsule_fields"))
        if isinstance(packet.get("capsule_fields"), dict) else {},
        "footprint": dict(packet.get("footprint"))
        if isinstance(packet.get("footprint"), dict) else {},
        "files_touched": [str(v) for v in files
                          if isinstance(v, (str, int, float))]
        if isinstance(files, list) else [],
        "protected_paths": [str(v) for v in protected
                            if isinstance(v, (str, int, float))]
        if isinstance(protected, list) else [],
        "provider": str(packet.get("provider", "")),
        "receipt_compact": bool(packet.get("receipt_compact",
                                             False)),
        "context_polluted": bool(packet.get("context_polluted",
                                             False)),
        "context_missing": bool(packet.get("context_missing",
                                            False)),
        "disposition_value": str(packet.get("disposition_value",
                                             "IMPLEMENT") or "IMPLEMENT"),
        "satisfied": bool(packet.get("satisfied", False)),
        "code_is_remedy": bool(packet.get("code_is_remedy", True)),
        "missing": str(packet.get("missing", "") or ""),
        "ambiguity": str(packet.get("ambiguity", "") or ""),
    }


def _check_spec(packet: Dict[str, Any]) -> List[Dict[str, str]]:
    """SPEC_READY gate: Thin Spec present, critic clean of blockers.

    The Thin Spec outcome lives in ``spec["title"]`` (the one-sentence
    outcome) and its behavior claims in ``spec["criteria"]`` plus
    ``spec["statements"]`` — the spec_critic shape, never a second
    Spec schema. An assured R2/R3 Spec must critique clean of
    blockers; compact scope (skipped) is clean by construction.
    """
    spec_critic = _require("spec_critic", _spec_critic)
    spec = packet["spec"]
    outcome = str(spec.get("title", "") or "").strip()
    criteria = spec.get("criteria", [])
    statements = spec.get("statements", [])
    if isinstance(criteria, str):
        criteria = [criteria]
    if isinstance(statements, str):
        statements = [statements]
    has_claims = bool([c for c in list(criteria) + list(statements)
                       if str(c or "").strip()])
    if not outcome or not has_claims:
        return [_make_finding(
            "no-spec",
            "Thin Spec carries no outcome or behavior claims: "
            "Arc A cannot start without a stated outcome",
            outcome or "(no outcome)")]
    result = spec_critic.critique(spec)
    blockers = [f for f in result.findings
                if f.get("severity") == "blocker"]
    if blockers:
        return [_make_finding(
            "spec-blocked",
            "assured Spec blocked by %s: resolve critic blockers "
            "before Arc A proceeds"
            % "; ".join(sorted({str(f.get("rule", "?"))
                                for f in blockers})),
            outcome[:200])]
    return []


def _check_mold(packet: Dict[str, Any]) -> List[Dict[str, str]]:
    """MOLD_QUALIFIED gate: digest-bound receipt plus true RED."""
    mold_qualification = _require("mold_qualification", _mold_qualification)
    run = packet["mold_run"]
    result = mold_qualification.qualify(run)
    if result.verdict != "qualified" or result.receipt is None:
        rules = sorted({str(f.get("rule", "?"))
                        for f in result.findings})
        return [_make_finding(
            "mold-unqualified",
            "Mold is not qualified (%s): requalify before Arc A "
            "proceeds" % ("; ".join(rules) or "no receipt"),
            str(run.get("mold", "") or "(unnamed mold)")[:200])]
    repairs = mold_qualification.verify_receipt(result.receipt, run)
    if repairs:
        return [_make_finding(
            "mold-unqualified",
            "qualification receipt does not bind this run (%s): "
            "the receipt moved under the Mold" % repairs[0][:120],
            str(run.get("mold", "") or "(unnamed mold)")[:200])]
    return []


def _check_attack(packet: Dict[str, Any]) -> List[Dict[str, str]]:
    """ATTACK_CLEAN gate: independent different-provider report."""
    mold_qualification = _require("mold_qualification", _mold_qualification)
    attack = packet["attack"]
    verdict = str(attack.get("verdict", "") or "").strip()
    attacker = str(attack.get("attacker_provider", "") or "")
    mold_provider = str(packet["mold_run"].get("provider", "") or "")
    mold_name = str(packet["mold_run"].get("mold", "")
                    or "(unnamed mold)")
    if not verdict or not attacker.strip():
        return [_make_finding(
            "attack-missing",
            "no independent attack report: a different-provider "
            "attacker must review the Mold before checkpoint",
            mold_name[:200])]
    if verdict not in ATTACK_VERDICTS:
        return [_make_finding(
            "attack-missing",
            "attack verdict %r is not clean|fixed-requalified: "
            "the attacker must state its outcome plainly" % verdict,
            mold_name[:200])]
    if _family(attacker) == _family(mold_provider):
        return [_make_finding(
            "attack-missing",
            "attacker %r shares the Mold provider family %r: "
            "the attack is not independent" % (attacker,
                                               mold_provider),
            mold_name[:200])]
    if verdict == "fixed-requalified":
        receipt = attack.get("receipt")
        run = attack.get("run")
        if not isinstance(receipt, dict) or not isinstance(
                run, dict):
            return [_make_finding(
                "attack-missing",
                "fixed-requalified claims a new qualification "
                "without its receipt and run: attach both",
                mold_name[:200])]
        repairs = mold_qualification.verify_receipt(receipt, run)
        if repairs:
            return [_make_finding(
                "attack-missing",
                "fixed-requalified receipt does not bind its run "
                "(%s): requalify after the fix" % repairs[0][:120],
                mold_name[:200])]
        result = mold_qualification.qualify(run)
        if result.verdict != "qualified":
            return [_make_finding(
                "attack-missing",
                "fixed-requalified run is not qualified: the fix "
                "did not restore trust",
                mold_name[:200])]
    return []


def _check_session(packet: Dict[str, Any]) -> List[Dict[str, str]]:
    """CHECKPOINTED gate (a): meta-test-clean Arc A session."""
    meta_tests = _require("meta_tests", _meta_tests)
    repairs = meta_tests.check_meta(packet["session"])
    if repairs:
        return [_make_finding(
            "session-dirty",
            "Arc A session is dirty (%s): keep all writes "
            "outside production and protected paths, run every "
            "control, match every hash" % repairs[0][:140],
            str(packet["session"].get("production_writes", ""))[:200])]
    return []


def _check_portfolio(packet: Dict[str, Any]) -> List[Dict[str, str]]:
    """CHECKPOINTED gate (b): valid verification portfolio.

    Consumes verification_portfolio.select_portfolio by reference:
    the selection's own findings (budget_exceeded / missing_command
    / excessive_portfolio) decide. A blocker or major finding fails
    the gate; a clean or minor-only selection passes.
    """
    verification_portfolio = _require("verification_portfolio", _verification_portfolio)
    project = packet["project"]
    try:
        selection = verification_portfolio.select_portfolio(project)
    except Exception as exc:
        return [_make_finding(
            "portfolio-invalid",
            "portfolio selection failed (%s): repair the project "
            "shape" % str(exc)[:120],
            str(project.get("stack", "") or "(no stack)")[:200])]
    bad = [f for f in selection.findings
           if str(f.get("severity", "")) in ("blocker", "major")]
    if bad:
        return [_make_finding(
            "portfolio-invalid",
            "portfolio invalid (%s): fund every claim with a "
            "command-backed technique, never an excessive set"
            % "; ".join(sorted({str(f.get("rule", "?"))
                                for f in bad})),
            str(project.get("stack", "") or "(no stack)")[:200])]
    return []


def _check_freeze(packet: Dict[str, Any]) -> List[Dict[str, str]]:
    """CHECKPOINTED gate (c): frozen Mold proof still binds."""
    proof_invalidation = _require("proof_invalidation", _proof_invalidation)
    result = proof_invalidation.check_invalidation(
        packet["freeze_run"])
    if result.invalidated:
        rules = sorted({str(f.get("rule", "?"))
                        for f in result.findings})
        return [_make_finding(
            "freeze-invalid",
            "frozen proof no longer binds (%s): reopen and "
            "requalify before checkpoint" % "; ".join(rules),
            str(packet["freeze_run"].get("mold", "")
                or "(unnamed mold)")[:200])]
    return []


def _check_ready(packet: Dict[str, Any]) -> List[Dict[str, str]]:
    """IMPLEMENT_AUTHORIZED gate (a): DoR READY receipt.

    Compact form (R0/R1 scope: outcome+scope+proof) or full form
    (every FULL_FIELDS entry) — consumed by reference from
    ready.check_receipt, never reimplemented here. The packet
    carries ``receipt_compact: true`` for the R0/R1 compact form.
    """
    ready = _require("ready", _ready)
    compact = bool(packet.get("receipt_compact", False))
    repairs = ready.check_receipt(packet["receipt"],
                                  compact=compact)
    if repairs:
        return [_make_finding(
            "not-ready",
            "DoR not READY (%s): complete Arc A readiness "
            "before authorization" % repairs[0][:140],
            str(packet["receipt"].get("outcome", "")
                or "(no outcome)")[:200])]
    return []


def _check_disposition(packet: Dict[str, Any]) -> List[Dict[str, str]]:
    """IMPLEMENT_AUTHORIZED gate (b): IMPLEMENT disposition."""
    disposition = _require("disposition", _disposition)
    try:
        result = disposition.decide(
            packet.get("disposition_value", "IMPLEMENT"),
            observation=packet["observation"],
            satisfied=bool(packet.get("satisfied", False)),
            code_is_remedy=bool(packet.get("code_is_remedy", True)),
            missing=str(packet.get("missing", "")),
            ambiguity=str(packet.get("ambiguity", "")))
    except ValueError as exc:
        return [_make_finding(
            "disposition-blocked",
            "disposition refuses authorization (%s)" % str(exc)[:140],
            str(packet.get("disposition_value", "")
                or "(no disposition)")[:200])]
    if result.get("disposition") != "IMPLEMENT":
        return [_make_finding(
            "disposition-blocked",
            "disposition is %s, not IMPLEMENT: only a complete "
            "observation authorizes the Builder path"
            % result.get("disposition"),
            str(packet.get("disposition_value", "")
                or "(no disposition)")[:200])]
    gaps = disposition.validate_observation(packet["observation"])
    if gaps:
        return [_make_finding(
            "disposition-blocked",
            "observation incomplete (missing %s): bind the exact "
            "head before authorization" % ", ".join(gaps),
            str(packet.get("disposition_value", "")
                or "(no disposition)")[:200])]
    return []


def _check_prompt(packet: Dict[str, Any]) -> List[Dict[str, str]]:
    """IMPLEMENT_AUTHORIZED gate (c): phase-pure prompt contract."""
    prompt_contract = _require("prompt_contract", _prompt_contract)
    repairs = prompt_contract.validate(packet["prompt"])
    if repairs:
        return [_make_finding(
            "prompt-impure",
            "prompt contract impure (%s): one phase per prompt "
            "with fresh hashes" % repairs[0][:140],
            str(packet["prompt"].get("primary_outcome", "")
                or "(no outcome)")[:200])]
    return []


def _check_capsule(packet: Dict[str, Any]) -> List[Dict[str, str]]:
    """IMPLEMENT_AUTHORIZED gate (d): Builder-ready capsule.

    The capsule must build (all canonical fields, no forbidden
    content, within the 24 KiB pilot ceiling) — consumed by
    reference from capsule.build, never reimplemented here. The
    ceiling is the load-bearing check: an oversize capsule fails
    instead of truncating fields away.
    """
    capsule = _require("capsule", _capsule)
    try:
        capsule.build(dict(packet["capsule_fields"]))
    except ValueError as exc:
        return [_make_finding(
            "capsule-unready",
            "Builder capsule unready (%s)" % str(exc)[:140],
            str(packet["capsule_fields"].get("outcome", "")
                or "(no outcome)")[:200])]
    return []


def _check_budget(packet: Dict[str, Any]) -> List[Dict[str, str]]:
    """IMPLEMENT_AUTHORIZED gate (e): context outside recovery.

    The packet carries the live footprint mapping plus the two
    recovery tripwires (``context_polluted``, ``context_missing``)
    the controller sets when history is polluted or a load-bearing
    fact is missing. Any tripwire — or a non-mapping / non-numeric
    footprint — fails the gate; only a govern verdict outside
    RECOVERY_REQUIRED passes. Consumed by reference from
    context_budget.govern.
    """
    context_budget = _require("context_budget", _context_budget)
    footprint = packet["footprint"]
    if not isinstance(footprint, dict) or not footprint:
        return [_make_finding(
            "budget-recovery",
            "no context footprint: record the working set "
            "before authorization",
            "(no footprint)")]
    clean: Dict[str, int] = {}
    for key, value in footprint.items():
        try:
            clean[str(key)] = int(value)
        except (TypeError, ValueError):
            return [_make_finding(
                "budget-recovery",
                "footprint entry %r is not a byte count: fix "
                "the working set" % str(key),
                "(bad footprint)")]
    verdict = context_budget.govern(
        clean,
        polluted=bool(packet.get("context_polluted", False)),
        missing_load_bearing=bool(packet.get("context_missing",
                                             False)))
    if verdict.get("status") == "RECOVERY_REQUIRED":
        return [_make_finding(
            "budget-recovery",
            "context requires recovery (%s): rotate from the "
            "capsule before authorization"
            % "; ".join(verdict.get("reasons", []))[:120],
            "(working set)")]
    return []


def _check_production(packet: Dict[str, Any]) -> List[Dict[str, str]]:
    """IMPLEMENT_AUTHORIZED gate (f): no production/protected write."""
    for path in packet["files_touched"]:
        if _under_any(path, PRODUCTION_PREFIXES):
            return [_make_finding(
                "production-write",
                "production write %r: Arc A authorizes no "
                "production writes" % path,
                path[:200])]
    protected = tuple(packet["protected_paths"])
    for path in packet["files_touched"]:
        if _under_any(path, protected) or path in protected:
            return [_make_finding(
                "production-write",
                "protected path %r: this write must never appear "
                "in Arc A" % path,
                path[:200])]
    return []


@dataclass
class ArcResult:
    """One Arc A phase-gate outcome for one packet."""

    phase: str = "SPEC_READY"
    findings: List[Dict[str, str]] = field(default_factory=list)

    @property
    def authorized(self) -> bool:
        return self.phase == "IMPLEMENT_AUTHORIZED" \
            and not any(f.get("severity") == "blocker"
                        for f in self.findings)


def advance(packet: Any) -> ArcResult:
    """Advance one Arc A packet to its furthest valid phase state.

    Gates run in phase order; the first failing gate pins the
    phase to the last fully-held state and its findings are
    returned. A fully clean packet reaches IMPLEMENT_AUTHORIZED
    with zero findings. Pure function: no I/O, deterministic
    in its input.
    """
    normalized = _normalize_packet(packet)
    findings: List[Dict[str, str]] = []

    spec_findings = _check_spec(normalized)
    if spec_findings:
        return ArcResult(phase="SPEC_READY", findings=spec_findings)

    mold_findings = _check_mold(normalized)
    if mold_findings:
        return ArcResult(phase="SPEC_READY", findings=mold_findings)

    attack_findings = _check_attack(normalized)
    if attack_findings:
        return ArcResult(phase="MOLD_QUALIFIED",
                         findings=attack_findings)

    session_findings = _check_session(normalized)
    portfolio_findings = _check_portfolio(normalized)
    freeze_findings = _check_freeze(normalized)
    checkpoint_findings = (session_findings + portfolio_findings
                           + freeze_findings)
    if checkpoint_findings:
        return ArcResult(phase="ATTACK_CLEAN",
                         findings=checkpoint_findings)

    tail_findings = (_check_ready(normalized)
                     + _check_disposition(normalized)
                     + _check_prompt(normalized)
                     + _check_capsule(normalized)
                     + _check_budget(normalized)
                     + _check_production(normalized))
    if tail_findings:
        return ArcResult(phase="CHECKPOINTED", findings=tail_findings)
    return ArcResult(phase="IMPLEMENT_AUTHORIZED", findings=[])


def _entries_of(corpus: Any) -> List[Dict[str, Any]]:
    if isinstance(corpus, dict):
        entries = corpus.get("entries")
    else:
        entries = corpus
    if not isinstance(entries, list):
        return []
    return entries


def validate_arc_corpus(corpus: Any) -> Tuple[List[str], List[Dict[str, Any]]]:
    """Validate the frozen Arc A fixture oracle.

    Returns (findings, entries); an empty findings list means
    the corpus is a valid frozen oracle: frozen marker set,
    stable provenance, at least 12 entries, unique
    well-formed IDs, every entry computing its expected rules
    and phase, and all 13 arc rules covered.
    """
    if isinstance(corpus, dict):
        if corpus.get("_frozen") is not True:
            return (["arc corpus is not frozen: set "
                     "\"_frozen\": true"], [])
        provenance = str(corpus.get("_provenance", ""))
        if "Stage 34 #125" not in provenance:
            return (["arc corpus provenance must name "
                      "\"Stage 34 #125\""], [])
    elif not isinstance(corpus, list):
        return (["arc corpus must be a JSON object with an "
                 "'entries' array (or a bare array)"], [])
    entries = _entries_of(corpus)
    findings: List[str] = []
    if len(entries) < 12:
        findings.append("arc corpus holds %d entries, want "
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
                            "arc-a.<class>.<nn>" % cid)
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
        for key in ("expected_phase", "expected_authorized"):
            if key not in entry:
                findings.append("entry %s: %s is required" % (cid,
                                                              key))
        result = advance(entry.get("packet", {}))
        computed = sorted({f["rule"] for f in result.findings})
        if sorted(str(r) for r in expected) != computed:
            findings.append("entry %s: expected_rules %r != "
                            "advance %r"
                            % (cid, sorted(str(r)
                                           for r in expected),
                               computed))
        if entry.get("expected_phase") != result.phase:
            findings.append("entry %s: expected_phase %r != "
                            "advance %r" % (cid, entry.get(
                                "expected_phase"),
                                result.phase))
        if bool(entry.get("expected_authorized")) != \
                result.authorized:
            findings.append("entry %s: expected_authorized %r != "
                            "advance %r" % (cid, entry.get(
                                "expected_authorized"),
                                result.authorized))
    for rule in RULES:
        if rule not in covered:
            findings.append("rule %r has no entries (all 13 "
                            "arc rules are required)"
                            % rule)
    return findings, entries


def clean_packet() -> Dict[str, Any]:
    """One clean Arc A packet reaching IMPLEMENT_AUTHORIZED.

    Every gate holds: compact-clean Thin Spec, a qualified Mold
    run with true RED, an independent clean attack report, a
    meta-test-clean session, a funded portfolio, a live freeze,
    a READY receipt, an IMPLEMENT observation, a phase-pure
    prompt, a buildable capsule, a healthy footprint, and zero
    production writes. Callers mutate one dimension per test.
    """
    mold_digest = ("aebc4e7beecafd257a8329577e5234955bae455f5033f"
                   "db525e6e78f66469fc6")
    head = "a" * 40
    red = {
        "alternative_impl_ok": True,
        "asserts_mock_only": False,
        "asserts_observable": True,
        "asserts_setup_state": False,
        "claims": ["claim-total"],
        "coverage_kind": "full",
        "hard_codes_example": False,
        "id": "t-red",
        "is_equivalent_mutant": False,
        "is_structural_failure": False,
        "omits_relevant_state": False,
        "red_reason": "expected total 42, observed 41 on the "
                      "externally visible summary",
        "status": "failed",
        "swallows_errors": False,
    }
    green = {
        "alternative_impl_ok": True,
        "asserts_mock_only": False,
        "asserts_observable": True,
        "asserts_setup_state": False,
        "claims": ["claim-total"],
        "coverage_kind": "full",
        "hard_codes_example": False,
        "id": "t-green",
        "is_equivalent_mutant": False,
        "is_structural_failure": False,
        "omits_relevant_state": False,
        "red_reason": "",
        "status": "passed",
        "swallows_errors": False,
    }
    run = {
        "head": head,
        "mold": "demo-mold",
        "mold_digest": mold_digest,
        "provider": "anthropic/claude",
        "risk": "R2",
        "tests": [red, green],
    }
    return {
        "spec": {
            "title": "Demo Arc A slice completes one outcome",
            "risk": "R1",
            "assured": False,
            "statements": ["The slice completes one outcome"],
            "examples": [],
            "criteria": ["Done within 200 ms"],
            "migration_steps": [],
            "external_calls": [],
        },
        "mold_run": run,
        "attack": {
            "verdict": "clean",
            "attacker_provider": "openai/reviewer",
            "note": "independent review found nothing material",
        },
        "session": {
            "production_writes": ["tools/arc_gate.py"],
            "protected_paths": ["src/protected-impl.py"],
            "controls_run": ["arc-a.control.red",
                             "arc-a.control.receipt"],
            "controls_expected": ["arc-a.control.red",
                                  "arc-a.control.receipt"],
            "hash_pairs": [],
        },
        "project": {
            "stack": "python",
            "claims": [{"id": "c-py-1",
                        "failure_shape": "crud",
                        "risk": "R2",
                        "kind": "generic"}],
            "commands": {"example_based": "pytest -m example_based"},
            "runtime_budget_s": 60,
        },
        "freeze_run": {
            "mold": "demo-mold",
            "mold_digest": "aaaa",
            "frozen_digest": "aaaa",
            "frozen_head": "head-freeze",
            "head": "head-now",
            "intent_digest": "intent-1",
            "frozen_intent_digest": "intent-1",
            "commands": [],
            "frozen_commands": [],
            "protected_paths": [],
            "touched_paths": [],
            "provider": "anthropic/claude",
        },
        "receipt": {
            "outcome": "Demo Arc A slice completes one outcome",
            "scope": "one slice, tools-only writes",
            "proof": "RED log plus qualification receipt",
        },
        "receipt_compact": True,
        "observation": {
            "environment": "test/1.0",
            "command": "standardctl arc-a check",
            "head": head,
            "expected": "advance to IMPLEMENT_AUTHORIZED",
            "observed": "all Arc A gates hold",
            "evidence": "corpus entry arc-a.clean.01",
        },
        "disposition_value": "IMPLEMENT",
        "satisfied": False,
        "code_is_remedy": True,
        "missing": "",
        "ambiguity": "",
        "prompt": {
            "primary_outcome": "Demo Arc A slice completes",
            "repository": "fixture-owner/fixture-app",
            "issue": "125",
            "phase": "spec",
            "role": "builder",
            "risk": "R2",
            "disposition": "IMPLEMENT",
            "allowed_mutations": "tools-only writes",
            "forbidden_mutations": "no production writes",
            "write_paths": "tools/",
            "protected_paths": "src/protected-impl.py",
            "evidence": "RED log",
            "stop_conditions": "stop on drift",
            "first_action": "run the qualification gate",
        },
        "capsule_fields": {
            "schema": "task-capsule",
            "version": "5.0.0",
            "issue": "125",
            "outcome": "Demo slice",
            "remaining_claims": "none",
            "phase": "spec",
            "role": "builder",
            "risk": "R2",
            "focus_envelope": "one slice",
            "allowed_paths": "tools/",
            "protected_paths": "src/protected-impl.py",
            "branch": "issue/125-arc-a-complete",
            "base": head,
            "head": head,
            "pr": "0",
            "lease": "lease-1",
            "extensions": "none",
            "rule_ids": "arc-a",
            "last_verification": "verify OK",
            "blocker": "none",
            "next_action": "advance toward Builder authorization",
            "stop_conditions": "stop on drift",
            "source_hashes": "mold %s" % mold_digest[:12],
            "redacted": "no secrets",
            "expires": "2026-10-01",
            "producer": "arc-a tests",
        },
        "footprint": {
            "capsule": 1000,
            "rules": 1000,
            "files": 1000,
            "skills": 500,
            "mcp": 100,
            "tool_output": 500,
        },
        "files_touched": ["tools/arc_gate.py"],
        "protected_paths": ["src/protected-impl.py"],
        "provider": "anthropic/claude",
        "receipt_compact": True,
    }
