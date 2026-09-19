"""Stage 32 Standard half: verification portfolio router.

Select the cheapest evidence portfolio capable of disproving
each important claim. One selection-and-rationale router across
technique categories; wide downstream reuse by Stages 33-41.
Reversible tooling.

Project plain-data shape (the declarative project schema)::

    project = {
      "stack": "js"|"python"|"dotnet"|"mixed",
      "claims": [ {"id": str,
                   "failure_shape": "state"|"auth"|"parse"|
                                    "migration"|"workflow"|"ui"|
                                    "control_plane"|"crud"|
                                    "adapter"|"docs",
                   "risk": "R0".."R3",
                   "kind": "parser"|"adapter"|"ui"|"auth"|
                           "state"|"docs"|"generic"} , ... ],
      "commands": {"technique": "shell command string", ...},
      "runtime_budget_s": int,
    }

Selection rules (frozen, explicit precedence in this order):

1. R0 ``docs`` claims -> NO techniques (empty portfolio,
   rationale "trivial R0 docs: no evidence portfolio needed").
   Proving docs need no portfolio is a proof point.
2. ``kind: parser`` -> property_based + fuzz
   (property/fuzz-heavy for grammar failures).
3. ``kind: adapter`` -> contract_test + example_based
   (contract-heavy for interface promises).
4. ``kind: ui`` -> e2e_focused (focused E2E) - at most ONE e2e
   technique (focused, never a full suite).
5. ``kind: auth`` or ``kind: state`` -> state_matrix +
   example_based (auth/state matrix).
6. Default: per-claim Mold default via
   ``verification_mold.select_technique`` mapped into this
   tool's 8-technique set, cost-capped: if the running total
   would exceed ``runtime_budget_s``, prefer the cheaper of
   (default, example_based) - but NEVER drop to zero
   techniques for a non-docs claim with risk >= R1 and NEVER
   silently skip: if even the cheapest portfolio for the
   remaining claims exceeds the budget, emit finding
   ``budget_exceeded`` naming the claim and the cheapest cost
   (fail loud, not silent).

Rejection rules (frozen precedence, findings appended in this
order, so output order is stable):

1. ``budget_exceeded`` - even the cheapest portfolio for a
   remaining claim exceeds the running budget -> major.
2. ``missing_command`` - a selected technique with no entry
   in ``project["commands"]`` -> blocker. A no-op command
   string (frozen markers ``"true"``, ``"echo ok"``,
   ``":"``, ``"exit 0"``, empty string) counts as missing:
   "no-op command does not satisfy <technique>".
3. ``excessive_portfolio`` - a claim assigned MORE than 3
   techniques, or the whole portfolio containing every one
   of the 8 techniques (the "force every claim through
   everything" anti-pattern) -> major.

Runtime estimates: ``total_estimated_s`` is the sum of
``TECHNIQUE_COST_S`` over the deduplicated technique set;
per-claim rationale strings name the selected techniques +
the failure-shape reason + cost.

``stack_ok`` repairs: unknown stack; mixed-stack projects
must have commands covering >=2 stack families (else repair
"mixed stack needs commands from at least two families").

Findings are repair guidance (what to fix, with an excerpt),
never an error: ``FINDING_FIELDS`` names the five required
keys, ``SEVERITIES`` names the allowed severities, and
``validate_finding`` returns repair strings (empty means
valid). ``select_portfolio`` is a pure function of its input
(no I/O anywhere): the same project always yields the same
portfolio. ``validate_portfolio_corpus`` checks the frozen
selection/rejection fixture oracle.

This module consumes projects as plain data and performs no
filesystem access itself. It never executes commands: the
per-stack command strings are declarative markers only.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

try:
    from verification_mold import select_technique as _mold_select
except Exception:
    _mold_select = None

RISKS = ("R0", "R1", "R2", "R3")

FINDING_FIELDS = ("id", "rule", "finding", "severity", "excerpt")

SEVERITIES = ("blocker", "major", "minor")

RULES = (
    "budget_exceeded",
    "missing_command",
    "excessive_portfolio",
)

TECHNIQUES = (
    "example_based",
    "property_based",
    "mutation_check",
    "contract_test",
    "scenario_test",
    "fuzz",
    "e2e_focused",
    "state_matrix",
)

# What each technique covers (frozen documentation):
# - example_based: one concrete seeded example with an oracle.
# - property_based: generative properties over input families.
# - mutation_check: oracle sensitivity to behavior edits.
# - contract_test: interface promises between two sides.
# - scenario_test: multi-step state/workflow sequences.
# - fuzz: exploratory malformed-input robustness.
# - e2e_focused: one focused user-visible slice, never a suite.
# - state_matrix: auth/state cross-products (roles x states).

TECHNIQUE_COST_S: Dict[str, float] = {
    "example_based": 5,
    "property_based": 30,
    "mutation_check": 120,
    "contract_test": 15,
    "scenario_test": 20,
    "fuzz": 180,
    "e2e_focused": 90,
    "state_matrix": 45,
}
# Provenance: Stage 32 estimates; Stages 40-41 may recalibrate.

STACKS = ("js", "python", "dotnet", "mixed")

STACK_TECHNIQUE_COMMANDS: Dict[str, Dict[str, str]] = {
    "python": {
        "example_based": "pytest -m example_based",
        "property_based": "pytest -m property_based",
        "mutation_check": "mutmut run",
        "contract_test": "pytest -m contract_test",
        "scenario_test": "pytest -m scenario_test",
        "fuzz": "hypothesis fuzz corpus/",
        "e2e_focused": "pytest -m e2e_focused",
        "state_matrix": "pytest -m state_matrix",
    },
    "js": {
        "example_based": "npm test -- --grep example_based",
        "property_based": "npm test -- --grep property_based",
        "mutation_check": "npx stryker run",
        "contract_test": "npm test -- --grep contract_test",
        "scenario_test": "npm test -- --grep scenario_test",
        "fuzz": "npx jsfuzz fuzz/ corpus/",
        "e2e_focused": "npx playwright test --focused",
        "state_matrix": "npm test -- --grep state_matrix",
    },
    "dotnet": {
        "example_based": "dotnet test --filter ExampleBased",
        "property_based": "dotnet test --filter PropertyBased",
        "mutation_check": "dotnet stryker",
        "contract_test": "dotnet test --filter ContractTest",
        "scenario_test": "dotnet test --filter ScenarioTest",
        "fuzz": "dotnet fuzz run corpus/",
        "e2e_focused": "dotnet test --filter E2EFocused",
        "state_matrix": "dotnet test --filter StateMatrix",
    },
    "mixed": {
        "example_based":
            "pytest -m example_based + npm test -- --grep example_based",
        "property_based":
            "pytest -m property_based + npm test -- --grep property_based",
        "mutation_check":
            "mutmut run + npx stryker run",
        "contract_test":
            "pytest -m contract_test + npm test -- --grep contract_test",
        "scenario_test":
            "pytest -m scenario_test + npm test -- --grep scenario_test",
        "fuzz":
            "hypothesis fuzz corpus/ + npx jsfuzz fuzz/ corpus/",
        "e2e_focused":
            "npx playwright test --focused",
        "state_matrix":
            "pytest -m state_matrix + npm test -- --grep state_matrix",
    },
}

CHEAPEST_FIRST = (
    "example_based",
    "contract_test",
    "scenario_test",
    "property_based",
    "state_matrix",
    "e2e_focused",
    "mutation_check",
    "fuzz",
)

NO_OP_COMMANDS = ("true", "echo ok", ":", "exit 0", "")

FAILURE_SHAPES = (
    "state", "auth", "parse", "migration", "workflow", "ui",
    "control_plane", "crud", "adapter", "docs",
)

KINDS = (
    "parser", "adapter", "ui", "auth", "state", "docs",
    "generic",
)

SELECTION_CLASSES = (
    "js", "python", "dotnet", "mixed", "parser", "adapter",
    "ui", "auth-state-matrix", "r0-docs",
)

REJECTION_CLASSES = (
    "missing-command",
    "excessive-portfolio",
)

_FALLBACK_TECHNIQUE_MAP = {
    "crud": "example_based",
    "state": "scenario_test",
    "auth": "example_based",
    "parse": "property_based",
    "migration": "scenario_test",
    "workflow": "scenario_test",
    "ui": "example_based",
    "control_plane": "contract_test",
}

_PYTHON_MARKERS = ("pytest", "python", "pip", "poetry",
                   "hypothesis", "mutmut")
_JS_MARKERS = ("npm", "npx", "node", "jest", "yarn", "pnpm",
               "playwright", "vitest", "jsfuzz", "stryker")
_DOTNET_MARKERS = ("dotnet",)

DEFAULT_PROJECT: Dict[str, Any] = {
    "stack": "",
    "claims": [],
    "commands": {},
    "runtime_budget_s": 10 ** 9,
}


@dataclass
class PortfolioResult:
    """One portfolio selection outcome for one project."""

    portfolio: Dict[str, List[str]] = field(default_factory=dict)
    commands: Dict[str, str] = field(default_factory=dict)
    total_estimated_s: float = 0
    rationales: Dict[str, str] = field(default_factory=dict)
    findings: List[Dict[str, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.findings


def _make_finding(rule: str, message: str, excerpt: str,
                  severity: str = "blocker") -> Dict[str, str]:
    """Build one structured finding dict for a portfolio."""
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


def _numbered(rule: str, message: str, excerpt: str,
              index: int, severity: str = "blocker") -> Dict[str, str]:
    """Build one finding with a stable per-rule sequence id."""
    item = _make_finding(rule, message, excerpt, severity)
    item["id"] = "%s-%d" % (rule, index + 1)
    return item


def _normalize_claim(entry: Any) -> Dict[str, str]:
    """Fill claim defaults so partial input never crashes."""
    entry = entry if isinstance(entry, dict) else {}
    risk = str(entry.get("risk", "") or "").upper()
    if risk not in RISKS:
        risk = "R1"
    kind = str(entry.get("kind", "") or "generic").strip().lower()
    if kind not in KINDS:
        kind = "generic"
    return {
        "id": str(entry.get("id", "")),
        "failure_shape": str(entry.get("failure_shape", "")),
        "risk": risk,
        "kind": kind,
    }


def _normalize_project(project: Any) -> Dict[str, Any]:
    """Fill total project defaults so partial input never crashes."""
    project = project if isinstance(project, dict) else {}
    stack = str(project.get("stack", "") or "").strip().lower()
    claims_raw = project.get("claims")
    if isinstance(claims_raw, list):
        claims = [_normalize_claim(e) for e in claims_raw]
    else:
        claims = []
    commands_raw = project.get("commands")
    commands: Dict[str, str] = {}
    if isinstance(commands_raw, dict):
        for key, value in commands_raw.items():
            commands[str(key)] = str(value)
    budget_raw = project.get("runtime_budget_s")
    try:
        budget = int(budget_raw)
    except (TypeError, ValueError):
        budget = DEFAULT_PROJECT["runtime_budget_s"]
    return {
        "stack": stack,
        "claims": claims,
        "commands": commands,
        "runtime_budget_s": budget,
    }


def _default_technique(claim: Dict[str, str]) -> str:
    """Per-claim Mold default mapped into the 8-technique set."""
    if _mold_select is not None:
        try:
            mapped = _mold_select(claim)
        except Exception:
            mapped = _FALLBACK_TECHNIQUE_MAP.get(
                claim.get("failure_shape", ""), "example_based")
    else:
        mapped = _FALLBACK_TECHNIQUE_MAP.get(
            claim.get("failure_shape", ""), "example_based")
    if mapped not in TECHNIQUES:
        return "example_based"
    return mapped


def _is_noop(command: str) -> bool:
    """True when a command string is a frozen no-op marker."""
    return command.strip().lower() in NO_OP_COMMANDS


def _cost_of(techniques: List[str]) -> float:
    """Sum TECHNIQUE_COST_S over one technique list."""
    return sum(TECHNIQUE_COST_S.get(t, 0) for t in techniques)


def _deduped_cost(selected: List[List[str]]) -> float:
    """Sum TECHNIQUE_COST_S over the deduplicated technique set."""
    union: set = set()
    for techs in selected:
        union.update(techs)
    return sum(TECHNIQUE_COST_S.get(t, 0) for t in union)


def _command_families(commands: Dict[str, str]) -> set:
    """Stack families covered by command strings (python/js/dotnet)."""
    families: set = set()
    for value in commands.values():
        low = str(value).lower()
        if any(m in low for m in _PYTHON_MARKERS):
            families.add("python")
        if any(m in low for m in _JS_MARKERS):
            families.add("js")
        if any(m in low for m in _DOTNET_MARKERS):
            families.add("dotnet")
    return families


def stack_ok(project: Any) -> List[str]:
    """Return repair strings for one project stack; empty means ok."""
    normalized = _normalize_project(project)
    stack = normalized["stack"]
    if stack not in STACKS:
        return ["unknown stack %r: stack is one of %s"
                % (stack, ", ".join(STACKS))]
    if stack == "mixed":
        families = _command_families(normalized["commands"])
        if len(families) < 2:
            return ["mixed stack needs commands from at least two "
                    "families: found %s; add commands from a second "
                    "stack family (pytest/python, npm/node, dotnet)"
                    % (sorted(families) or "none")]
    return []


def check_excessive(portfolio: Any) -> List[Dict[str, str]]:
    """Return excessive_portfolio findings for one claim map."""
    mapping = portfolio if isinstance(portfolio, dict) else {}
    findings: List[Dict[str, str]] = []
    for cid, techs in mapping.items():
        items = list(techs) if isinstance(techs, list) else []
        if len(items) > 3:
            findings.append(_numbered(
                "excessive_portfolio",
                "claim %r is assigned %d techniques (%s): keep at "
                "most 3 per claim so no claim is forced through "
                "everything" % (str(cid)[:60], len(items),
                                ", ".join(str(t) for t in items)[:80]),
                str(cid) or "(unnamed claim)", len(findings),
                "major"))
    union: set = set()
    for techs in mapping.values():
        if isinstance(techs, list):
            union.update(str(t) for t in techs)
    if union == set(TECHNIQUES):
        findings.append(_numbered(
            "excessive_portfolio",
            "portfolio contains every one of the 8 techniques: "
            "select the cheapest capable slice per claim instead "
            "of forcing every claim through everything",
            "all-8 portfolio", len(findings), "major"))
    return findings


def select_portfolio(project: Any) -> PortfolioResult:
    """Select the cheapest capable portfolio as plain data out.

    Pure function: no I/O, deterministic in its input. Runs
    the six frozen selection rules in precedence order, then
    the three frozen rejection checks (budget_exceeded,
    missing_command, excessive_portfolio).
    """
    normalized = _normalize_project(project)
    claims = normalized["claims"]
    commands = normalized["commands"]
    budget = normalized["runtime_budget_s"]
    portfolio: Dict[str, List[str]] = {}
    rationales: Dict[str, str] = {}
    budget_findings: List[Dict[str, str]] = []
    existing: set = set()
    for claim in claims:
        cid = claim["id"]
        kind = claim["kind"]
        shape = claim["failure_shape"]
        risk = claim["risk"]
        if risk == "R0" and (kind == "docs" or shape == "docs"):
            portfolio[cid] = []
            rationales[cid] = (
                "trivial R0 docs: no evidence portfolio needed "
                "(claim %s, kind docs, cost 0s)" % (cid or "unnamed"))
            continue
        if kind == "parser":
            techs = ["property_based", "fuzz"]
            rationales[cid] = (
                "parser kind (failure_shape %s): property_based + "
                "fuzz (property/fuzz-heavy for grammar failures; "
                "cost %ss)" % (shape or "parse", _cost_of(techs)))
            portfolio[cid] = techs
            existing.update(techs)
            continue
        if kind == "adapter":
            techs = ["contract_test", "example_based"]
            rationales[cid] = (
                "adapter kind (failure_shape %s): contract_test + "
                "example_based (contract-heavy for interface "
                "promises; cost %ss)" % (shape or "adapter",
                                         _cost_of(techs)))
            portfolio[cid] = techs
            existing.update(techs)
            continue
        if kind == "ui":
            techs = ["e2e_focused"]
            rationales[cid] = (
                "ui kind (failure_shape %s): e2e_focused (focused "
                "E2E slice, never a full suite; cost %ss)"
                % (shape or "ui", _cost_of(techs)))
            portfolio[cid] = techs
            existing.update(techs)
            continue
        if kind in ("auth", "state"):
            techs = ["state_matrix", "example_based"]
            rationales[cid] = (
                "%s kind (failure_shape %s): state_matrix + "
                "example_based (auth/state matrix for role and "
                "state cross-products; cost %ss)"
                % (kind, shape or kind, _cost_of(techs)))
            portfolio[cid] = techs
            existing.update(techs)
            continue
        default = _default_technique(claim)
        candidate = [default]
        candidate_total = sum(
            TECHNIQUE_COST_S.get(t, 0) for t in (existing | set(candidate)))
        if candidate_total <= budget:
            portfolio[cid] = candidate
            rationales[cid] = (
                "default Mold technique for failure_shape %s: %s "
                "(cheapest capable by shape, never by quota; cost "
                "%ss within %ss budget)"
                % (shape or "crud", default, _cost_of(candidate),
                   budget))
            existing.update(candidate)
            continue
        cheap = "example_based"
        if TECHNIQUE_COST_S.get(cheap, 5) <= TECHNIQUE_COST_S.get(
                default, 5):
            chosen = cheap
        else:
            chosen = default
        cheapest_total = sum(
            TECHNIQUE_COST_S.get(t, 0) for t in (existing | {chosen}))
        portfolio[cid] = [chosen]
        cheapest_cost = TECHNIQUE_COST_S.get(chosen, 0)
        if cheapest_total <= budget:
            rationales[cid] = (
                "default Mold technique for failure_shape %s: %s "
                "(cost-capped to cheaper %s within %ss budget; "
                "cost %ss)"
                % (shape or "crud", default, chosen, budget,
                   cheapest_cost))
            existing.add(chosen)
            continue
        budget_findings.append(_numbered(
            "budget_exceeded",
            "claim %r needs cheapest technique %r at %ss, which "
            "exceeds the remaining runtime budget %ss: raise the "
            "budget or accept the over-budget portfolio (never a "
            "silent skip)" % (cid[:60] if cid else "(unnamed)",
                              chosen, cheapest_cost, budget),
            cid or "(unnamed claim)", len(budget_findings),
            "major"))
        rationales[cid] = (
            "default Mold technique for failure_shape %s: %s "
            "(cost-capped to cheaper %s over %ss budget; cheapest "
            "cost %ss still assigned, fail loud)"
            % (shape or "crud", default, chosen, budget,
               cheapest_cost))
        existing.add(chosen)
    union: set = set()
    for techs in portfolio.values():
        union.update(techs)
    total = sum(TECHNIQUE_COST_S.get(t, 0) for t in union)
    selected_commands: Dict[str, str] = {}
    for tech in union:
        if tech in commands:
            selected_commands[tech] = commands[tech]
    missing: List[Dict[str, str]] = []
    for claim in claims:
        cid = claim["id"]
        for tech in portfolio.get(cid, []):
            if tech not in commands:
                missing.append(_numbered(
                    "missing_command",
                    "technique %r selected for claim %r has no "
                    "command: add project[\"commands\"][%r] so the "
                    "technique can actually run"
                    % (tech, cid[:60] if cid else "(unnamed)", tech),
                    "%s -> %s" % (cid, tech), len(missing),
                    "blocker"))
            elif _is_noop(commands[tech]):
                missing.append(_numbered(
                    "missing_command",
                    "no-op command does not satisfy %s for claim "
                    "%r: replace %r with a real %s command"
                    % (tech, cid[:60] if cid else "(unnamed)",
                       commands[tech][:40], tech),
                    "%s -> %s" % (cid, tech), len(missing),
                    "blocker"))
    excessive = check_excessive(portfolio)
    findings = budget_findings + missing + excessive
    return PortfolioResult(
        portfolio=portfolio,
        commands=selected_commands,
        total_estimated_s=total,
        rationales=rationales,
        findings=findings,
    )


def _entries_of(corpus: Any) -> List[Dict[str, Any]]:
    if isinstance(corpus, dict):
        entries = corpus.get("entries")
    else:
        entries = corpus
    if not isinstance(entries, list):
        return []
    return entries


def validate_portfolio_corpus(
        corpus: Any) -> Tuple[List[str], List[Dict[str, Any]]]:
    """Validate the frozen selection/rejection fixture oracle.

    Returns (findings, entries); an empty findings list means
    the corpus is a valid frozen oracle: frozen marker set,
    stable provenance, at least 11 entries, unique
    well-formed IDs, every selection entry reproducing its
    expected map and runtime total, every rejection entry
    producing its rule, and all 9 selection plus 2 rejection
    classes present.
    """
    import re as _re
    entry_re = _re.compile(r"^verify-portfolio\.[a-z0-9-]+\.\d{2}$")
    if isinstance(corpus, dict):
        if corpus.get("_frozen") is not True:
            return (["portfolio corpus is not frozen: set "
                     "\"_frozen\": true"], [])
        provenance = str(corpus.get("_provenance", ""))
        if "Stage 32 #123" not in provenance:
            return (["portfolio corpus provenance must name "
                      "\"Stage 32 #123\""], [])
    elif not isinstance(corpus, list):
        return (["portfolio corpus must be a JSON object with an "
                 "'entries' array (or a bare array)"], [])
    entries = _entries_of(corpus)
    findings: List[str] = []
    if len(entries) < 11:
        findings.append("portfolio corpus holds %d entries, want "
                        "at least 11" % len(entries))
    seen: Dict[str, int] = {}
    covered = set()
    by_class: Dict[str, int] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            findings.append("entries[%d] is not a mapping" % index)
            continue
        cid = str(entry.get("id", ""))
        if not entry_re.match(cid):
            findings.append("entry %r: id is not "
                            "verify-portfolio.<class>.<nn>" % cid)
        if cid in seen:
            findings.append("duplicate entry id %s (entries %d "
                            "and %d)" % (cid, seen[cid], index))
        else:
            seen[cid] = index
        if not str(entry.get("note", "")).strip():
            findings.append("entry %s: a one-line adjudication note "
                            "is required" % cid)
        cls = str(entry.get("class", ""))
        if cls not in SELECTION_CLASSES + REJECTION_CLASSES:
            findings.append("entry %s: unknown class %r" % (cid, cls))
            continue
        covered.add(cls)
        by_class[cls] = by_class.get(cls, 0) + 1
        if cls in SELECTION_CLASSES:
            project = entry.get("project")
            expected = entry.get("expected")
            if not isinstance(project, dict):
                findings.append("entry %s: project must be a mapping"
                                % cid)
                continue
            if not isinstance(expected, dict):
                findings.append("entry %s: expected must be a "
                                "claim-to-techniques map" % cid)
                continue
            if "expected_total_s" not in entry:
                findings.append("entry %s: expected_total_s is "
                                "required" % cid)
                continue
            if "budget" not in entry:
                findings.append("entry %s: budget is required" % cid)
                continue
            result = select_portfolio(project)
            computed = {k: set(v) for k, v in
                        result.portfolio.items()}
            wanted = {}
            try:
                wanted = {str(k): set(v) for k, v in
                          expected.items()}
            except (AttributeError, TypeError):
                findings.append("entry %s: expected map is malformed"
                                % cid)
                continue
            if computed != wanted:
                findings.append("entry %s: expected %r != select %r"
                                % (cid, {k: sorted(v) for k, v in
                                         wanted.items()},
                                   {k: sorted(v) for k, v in
                                    computed.items()}))
            try:
                wanted_total = float(entry.get("expected_total_s"))
            except (TypeError, ValueError):
                findings.append("entry %s: expected_total_s must be "
                                "a number" % cid)
                continue
            if float(result.total_estimated_s) != wanted_total:
                findings.append("entry %s: expected_total_s %r != "
                                "select %r" % (cid, wanted_total,
                                              result.total_estimated_s))
            if result.findings:
                findings.append("entry %s: selection entry must be "
                                "clean, got %r" % (
                                    cid, sorted({f["rule"] for f in
                                                 result.findings})))
        elif cls == "missing-command":
            project = entry.get("project")
            if not isinstance(project, dict):
                findings.append("entry %s: project must be a mapping"
                                % cid)
                continue
            result = select_portfolio(project)
            rules = sorted({f["rule"] for f in result.findings})
            if "missing_command" not in rules:
                findings.append("entry %s: missing_command not "
                                "produced, got %r" % (cid, rules))
        elif cls == "excessive-portfolio":
            expected = entry.get("expected")
            if not isinstance(expected, dict):
                findings.append("entry %s: expected must be a "
                                "claim-to-techniques map" % cid)
                continue
            rules = sorted({f["rule"] for f in
                            check_excessive(expected)})
            if "excessive_portfolio" not in rules:
                findings.append("entry %s: excessive_portfolio not "
                                "produced, got %r" % (cid, rules))
    for cls in SELECTION_CLASSES:
        if cls not in covered:
            findings.append("selection class %r has no entries (all 9 "
                            "selection classes are required)" % cls)
    for cls in REJECTION_CLASSES:
        if cls not in covered:
            findings.append("rejection class %r has no entries (both "
                            "rejection classes are required)" % cls)
    return findings, entries
