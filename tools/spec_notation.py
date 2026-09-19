"""Stage 27 Standard half: spec-notation selection for Thin Specs.

Thin Specs get precise behavioral language selected by ambiguity and
risk — never a mandatory syntax. Five notations plus plain criteria are
available (``NOTATIONS``); ``plain`` is always available and wins
wherever plain acceptance criteria are already clearer. This module
consumes the task as plain data and performs no filesystem access
itself.

Task shape (plain data; missing keys fall back to a total defaults
dict, never a crash)::

    {"ambiguity": 0-3,              # how unclear the requirement is
     "risk": "R0"|"R1"|"R2"|"R3",   # Standard risk tier
     "stateful": bool,              # persisted state / session workflow
     "concurrency_or_retry": bool,  # retries, idempotency, races
     "external_effects": bool,      # deployment, recovery, side effects
     "ui_or_text": bool,            # cosmetic copy/layout work
     "authorization": bool}         # actor/resource/action decisions

Selection semantics (deterministic, frozen):

- Precedence, first match wins (frozen tie-break order; evaluated after
  the pre-step below):
  1. ``authorization``        -> specification_by_example
     (decision table of actor/resource/action outcomes)
  2. ``concurrency_or_retry`` -> atdd
     (the failure is only provable by replay, so the contract is the
     failing test written first; the behavioral-across-actors variant is
     frozen OUT — bdd is reserved for external effects, keeping exactly
     one rule per dimension)
  3. ``external_effects``     -> bdd
     (given/when/then with the observable side effect named)
  4. ``stateful``             -> ears
     ("when/then" requirement sentences pin condition-trigger pairs)
  5. otherwise                -> plain
     (``ui_or_text`` + ambiguity 0 + R0/R1 is the frozen cosmetic plain
     case — do not over-specify cosmetic work; ambiguity 0 with no
     behavioral dimension is the generic plain case; ambiguity 1
     tolerates plain)
- ``ambiguity >= 2`` at any risk steps back to example mapping FIRST
  (map concrete examples, rules, and questions) and then re-selects
  from the mapped rules. Mapped rules are concrete, so re-selection
  treats ambiguity as resolved; the step is recorded in ``pre_steps``.
- Guards run after selection and can invalidate it (findings, so
  ``ok`` is False — the selection is not valid, not an error):
  under-specification — ``plain`` selected while ``stateful`` /
  ``concurrency_or_retry`` / ``external_effects`` is set or risk is
  R2/R3 ("plain criteria cannot carry this behavior");
  over-specification — a heavyweight notation for cosmetic work
  (``ui_or_text`` + ambiguity 0 + R0) with no behavioral dimension
  ("plain criteria are clearer here").
- ``force`` pins a notation for what-if adjudication (the guards still
  apply); it never changes the precedence rules.
- ``measure(entry)`` is the MEASUREMENTS helper: one frozen-corpus
  entry's over-/under-specification, divergent-interpretation, and
  token-cost fields; pass a list of entries for the corpus aggregate.
  A non-plain entry without an adjudication note counts one divergent
  interpretation (an unrecorded judgment call invites divergent
  implementation readings).
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

NOTATIONS = ("ears", "example_mapping", "specification_by_example", "bdd",
             "atdd", "plain")

HEAVYWEIGHT = ("ears", "example_mapping", "specification_by_example", "bdd",
               "atdd")

RISKS = ("R0", "R1", "R2", "R3")

CATEGORIES = (
    "cosmetic", "local-bug", "stateful-workflow", "authorization",
    "migration", "retry-idempotency", "deployment", "recovery",
)

DEFAULTS: Dict[str, Any] = {
    "ambiguity": 0,
    "risk": "R1",
    "stateful": False,
    "concurrency_or_retry": False,
    "external_effects": False,
    "ui_or_text": False,
    "authorization": False,
}

PRE_STEP_EXAMPLE_MAPPING = (
    "example mapping first: map concrete examples, rules, and questions, "
    "then re-select the notation from the mapped rules")

UNDER_SPECIFIED_FINDING = (
    "under-specified: plain criteria cannot carry this behavior "
    "(stateful, concurrency/retry, external effects, or R2+ need a "
    "structured notation)")

OVER_SPECIFIED_FINDING = (
    "over-specified: plain criteria are clearer here (ui/text cosmetics "
    "at ambiguity 0 and R0 need no notation machinery)")

CORPUS_ID_RE = re.compile(r"^spec-notation\.[a-z-]+\.\d{2}$")


@dataclass
class SelectionResult:
    """One notation-selection outcome for one Thin Spec task."""

    notation: str = "plain"
    pre_steps: List[str] = field(default_factory=list)
    findings: List[str] = field(default_factory=list)
    rationale: str = ""

    @property
    def ok(self) -> bool:
        return not self.findings


def _normalize(task: Dict[str, Any]) -> Dict[str, Any]:
    """Fill a total defaults dict; clamp ambiguity to 0-3 and risk to a
    known tier so partial or out-of-range input never crashes."""
    out: Dict[str, Any] = {}
    for key, default in DEFAULTS.items():
        value = task.get(key, default)
        if key == "ambiguity":
            try:
                value = int(value)
            except (TypeError, ValueError):
                value = default
            value = max(0, min(3, value))
        elif key == "risk":
            value = str(value or "").upper()
            if value not in RISKS:
                value = default
        else:
            value = bool(value)
        out[key] = value
    return out


def _guards(task: Dict[str, Any], notation: str) -> List[str]:
    """Over-/under-specification guards for one (task, notation) pair."""
    findings: List[str] = []
    behavioral = (task["stateful"] or task["concurrency_or_retry"]
                  or task["external_effects"])
    if notation == "plain" and (behavioral or task["risk"] in ("R2", "R3")):
        findings.append(UNDER_SPECIFIED_FINDING)
    if (notation in HEAVYWEIGHT and task["ui_or_text"]
            and task["ambiguity"] == 0 and task["risk"] == "R0"
            and not behavioral and not task["authorization"]):
        findings.append(OVER_SPECIFIED_FINDING)
    return findings


def _select(task: Dict[str, Any]) -> Tuple[str, str]:
    """Frozen precedence: first match wins (see module docstring)."""
    if task["authorization"]:
        return "specification_by_example", (
            "authorization decision: a Specification-by-Example decision "
            "table pins actor/resource/action outcomes so permissions "
            "cannot drift")
    if task["concurrency_or_retry"]:
        return "atdd", (
            "retry/idempotency or concurrency: the property is only "
            "provable by replay, so ATDD's test-first loop is the contract")
    if task["external_effects"]:
        return "bdd", (
            "external effects: BDD given/when/then stages the observable "
            "side effect (deployment, recovery) so it can be verified in "
            "the world")
    if task["stateful"]:
        return "ears", (
            "stateful workflow: EARS 'when/then' requirement sentences pin "
            "condition-trigger pairs over persisted state")
    if task["ui_or_text"] and task["risk"] in ("R0", "R1"):
        return "plain", (
            "cosmetic ui/text work at ambiguity 0 and R0/R1: plain "
            "criteria win; do not over-specify")
    return "plain", (
        "single unconditioned behavior at ambiguity 0 with no state, "
        "retry, or external-effect dimension: plain criteria are exact")


def select_notation(task: Dict[str, Any],
                    force: Optional[str] = None) -> SelectionResult:
    """Select the notation for one Thin Spec task (plain data in, plain
    data out; no I/O).

    Raises:
        ValueError: When ``force`` is not a known notation.
    """
    normalized = _normalize(task or {})
    pre_steps: List[str] = []
    if normalized["ambiguity"] >= 2:
        pre_steps.append(PRE_STEP_EXAMPLE_MAPPING)
        normalized = dict(normalized, ambiguity=0)
    if force is not None:
        if force not in NOTATIONS:
            raise ValueError(
                "unknown notation %r (valid: %s)" % (force, ", ".join(NOTATIONS)))
        notation = force
        rationale = ("forced selection for what-if adjudication; guards "
                     "still apply")
    else:
        notation, rationale = _select(normalized)
    findings = _guards(normalized, notation)
    return SelectionResult(notation, pre_steps, findings, rationale)


def measure(entry: Union[Dict[str, Any], List[Dict[str, Any]]]) -> Dict[str, Any]:
    """MEASUREMENTS helper for the frozen corpus.

    One entry in, one dict out: over-/under-specification guards on
    (task, expected_notation), the divergent-interpretation count (a
    non-plain entry with no adjudication note), and the token-cost
    fields from the entry's ``cost``. A list of entries returns the
    corpus aggregate with summed token cost.
    """
    if isinstance(entry, list):
        aggregate: Dict[str, Any] = {
            "entries": len(entry),
            "over_specification": 0,
            "under_specification": 0,
            "divergent_interpretations": 0,
            "notation_tokens_est": 0,
            "plain_tokens_est": 0,
        }
        for item in entry:
            single = measure(item)
            for field_name in ("over_specification", "under_specification",
                               "divergent_interpretations",
                               "notation_tokens_est", "plain_tokens_est"):
                aggregate[field_name] += single[field_name]
        aggregate["token_cost"] = (
            aggregate["notation_tokens_est"]
            - aggregate["plain_tokens_est"])
        return aggregate

    record = entry if isinstance(entry, dict) else {}
    normalized = _normalize(record.get("task") or {})
    notation = str(record.get("expected_notation", ""))
    findings = _guards(normalized, notation)
    cost = record.get("cost") or {}

    def positive_int(value: Any) -> int:
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
        return 0

    notation_tokens = positive_int(cost.get("notation_tokens_est"))
    plain_tokens = positive_int(cost.get("plain_tokens_est"))
    return {
        "id": str(record.get("id", "")),
        "notation": notation,
        "over_specification": int(OVER_SPECIFIED_FINDING in findings),
        "under_specification": int(UNDER_SPECIFIED_FINDING in findings),
        "divergent_interpretations": int(
            notation in HEAVYWEIGHT
            and not str(record.get("adjudication", "")).strip()),
        "notation_tokens_est": notation_tokens,
        "plain_tokens_est": plain_tokens,
        "token_cost": notation_tokens - plain_tokens,
    }


def validate_corpus(corpus: Any) -> Tuple[List[str], Dict[str, Any]]:
    """Validate a frozen corpus document (or a bare entries list):
    unique well-formed IDs, complete categories, honest measurements,
    and every expected_notation equal to select_notation(task).

    Returns (findings, aggregate_measurements); an empty findings list
    means the corpus is a valid adjudicated oracle.
    """
    entries = corpus.get("entries") if isinstance(corpus, dict) else corpus
    if not isinstance(entries, list):
        return ["corpus must be a JSON object with an 'entries' array "
                "(or a bare array)"], measure([])
    if isinstance(corpus, dict) and corpus.get("_frozen") is not True:
        return ["corpus is not frozen: set \"_frozen\": true"], measure([])
    findings: List[str] = []
    seen: Dict[str, int] = {}
    categories_found = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            findings.append("entries[%d] is not a mapping" % index)
            continue
        cid = str(entry.get("id", ""))
        category = str(entry.get("category", ""))
        notation = str(entry.get("expected_notation", ""))
        if not CORPUS_ID_RE.match(cid):
            findings.append(
                "entry %r: id is not spec-notation.<category>.<nn>" % cid)
        elif cid.split(".")[1] != category:
            findings.append(
                "entry %s: id category segment does not match category %r"
                % (cid, category))
        if cid in seen:
            findings.append(
                "duplicate corpus id %s (entries %d and %d)"
                % (cid, seen[cid], index))
        else:
            seen[cid] = index
        if category not in CATEGORIES:
            findings.append(
                "entry %s: unknown category %r" % (cid, category))
        else:
            categories_found.add(category)
        if notation not in NOTATIONS:
            findings.append(
                "entry %s: unknown expected_notation %r" % (cid, notation))
        else:
            result = select_notation(entry.get("task") or {})
            if result.notation != notation:
                findings.append(
                    "entry %s: expected_notation %r does not match "
                    "select_notation %r" % (cid, notation, result.notation))
        cost = entry.get("cost") or {}
        for cost_field in ("notation_tokens_est", "plain_tokens_est"):
            value = cost.get(cost_field)
            if (not isinstance(value, int) or isinstance(value, bool)
                    or value <= 0):
                findings.append(
                    "entry %s: cost.%s must be a positive int"
                    % (cid, cost_field))
        if notation in HEAVYWEIGHT and not str(
                entry.get("adjudication", "")).strip():
            findings.append(
                "entry %s: non-plain entry needs an adjudication note"
                % cid)
    for category in CATEGORIES:
        if category not in categories_found:
            findings.append(
                "category %r has no entries (all %d categories are "
                "required)" % (category, len(CATEGORIES)))
    return findings, measure(entries)
