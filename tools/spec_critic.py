"""Stage 28 Standard half: fresh specification critic and ready gate.

Independently challenge important Specs before verification design
begins. The critic raises structured findings only — it has NO write
authority over Specs; findings update the Spec through owner
precedence. Compact/simple work is never burdened: only assured R2/R3
work is critiqued, everything else returns ``skipped`` with no
findings.

Spec shape (plain data; missing keys fall back to a total defaults
dict, never a crash)::

    {"title": str,
     "risk": "R0"|"R1"|"R2"|"R3",
     "assured": bool,                    # owner marks the work assured
     "statements": [str, ...],           # behavioral statements
     "examples": [{"given": str, "when": str, "then": str}, ...],
     "criteria": [str, ...],             # acceptance criteria
     "migration_steps": [str, ...],      # optional; migration specs
     "external_calls": [str, ...]}       # optional; external deps

Scope first: compact work (``assured`` false OR risk R0/R1) returns
``status="skipped"`` with empty findings regardless of content.
Only assured R2/R3 work runs the rules (``status="critiqued"``).

Deterministic rules (frozen precedence, first listed first checked;
findings appended in this order, so output order is stable):

1. ``ambiguous_owner`` — any statement naming tenant/multi-tenant/
   workspace/account without an explicit ownership phrase
   ("owned by", "per-tenant"/"per tenant", or a named owning actor
   such as owner/admin/member/accountant/viewer) -> blocker.
2. ``contradictory_examples`` — two examples sharing the same
   ``given``+``when`` but different ``then`` (exact string
   comparison) -> blocker.
3. ``untestable_adjective`` — a statement/criterion sentence holding
   a vague adjective from the FROZEN list (fast, scalable, robust,
   user-friendly, simple, clean, efficient, flexible, intuitive,
   maintainable) with no digit or measurement unit in the same
   sentence -> major. A sentence carrying a digit/unit bound
   (e.g. "within 200 ms") does NOT trip.
4. ``missing_timeout`` — ``external_calls`` non-empty and no
   statement/criterion mentions a timeout/deadline bound (detect:
   "timeout"/"deadline"/"ms"/"seconds") -> blocker.
5. ``hidden_migration_order`` — ``migration_steps`` length > 1 and
   no statement/criterion mentions ordering ("before", "after",
   "order", "phase") -> blocker.
6. ``overconstrained_implementation`` — a criterion naming an
   implementation artifact from the FROZEN marker list (library,
   table, column, SQL, Redis, Postgres, ORM, framework, .py, .ts,
   .json) -> major.
7. ``giant_spec`` — len(statements) + len(criteria) > 20 -> blocker
   telling the owner to split the Spec.

Findings are repair guidance (what to fix, with an excerpt), never
an error: ``FINDING_FIELDS`` names the five required keys,
``SEVERITIES`` names the allowed severities, and
``validate_finding`` returns repair strings (empty means valid).
``gates_ready`` is the ready gate: assured R2/R3 requires zero
blocker findings; compact work is always ready.

This module consumes Specs as plain data and performs no filesystem
access itself.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

RISKS = ("R0", "R1", "R2", "R3")

FINDING_FIELDS = ("id", "rule", "finding", "severity", "excerpt")

SEVERITIES = ("blocker", "major", "minor")

RULES = (
    "ambiguous_owner",
    "contradictory_examples",
    "untestable_adjective",
    "missing_timeout",
    "hidden_migration_order",
    "overconstrained_implementation",
    "giant_spec",
)

CLASSES = (
    "tenant-ambiguity",
    "contradictory-examples",
    "untestable-adjective",
    "missing-timeout",
    "migration-order",
    "overconstraint",
    "giant-spec",
    "compact-control",
)

VAGUE_ADJECTIVES = (
    "fast", "scalable", "robust", "user-friendly", "simple", "clean",
    "efficient", "flexible", "intuitive", "maintainable",
)

IMPLEMENTATION_MARKERS = (
    "library", "table", "column", "sql", "redis", "postgres", "orm",
    "framework", ".py", ".ts", ".json",
)

OWNERSHIP_KEYWORDS = ("tenant", "multi-tenant", "workspace", "account")

OWNERSHIP_PHRASES = ("owned by", "per-tenant", "per tenant")

NAMED_OWNERS = ("owner", "admin", "member", "accountant", "viewer")

ORDER_WORDS = ("before", "after", "order", "phase")

TIMEOUT_WORDS = ("timeout", "deadline", "seconds", "second")

MEASURE_UNITS = (
    "ms", "millisecond", "milliseconds", "second", "seconds",
    "minute", "minutes", "hour", "hours", "percent", "%",
)

DEFAULTS: Dict[str, Any] = {
    "title": "",
    "risk": "R1",
    "assured": False,
    "statements": [],
    "examples": [],
    "criteria": [],
    "migration_steps": [],
    "external_calls": [],
}

_ADJECTIVE_RES = [
    re.compile(r"\b%s\b" % re.escape(word)) for word in VAGUE_ADJECTIVES
]

_MARKER_RES = [
    re.compile(r"\b%s\b" % re.escape(word))
    for word in IMPLEMENTATION_MARKERS if not word.startswith(".")
]

_MS_RE = re.compile(r"\bmilliseconds?\b|\bms\b|%")

_DIGIT_RE = re.compile(r"\d")

_SENTENCE_SPLIT_RE = re.compile(r"[^.!?;]+[.!?;]?")

_CORPUS_ID_RE = re.compile(r"^spec-critic\.[a-z-]+\.\d{2}$")


@dataclass
class CritiqueResult:
    """One critic outcome for one Spec."""

    status: str = "skipped"  # "skipped" | "critiqued"
    findings: List[Dict[str, str]] = field(default_factory=list)
    scope: str = "compact"  # "compact" | "assured"

    @property
    def ok(self) -> bool:
        return not self.findings


def _normalize(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Fill a total defaults dict so partial input never crashes."""
    spec = spec if isinstance(spec, dict) else {}
    out: Dict[str, Any] = {}
    out["title"] = str(spec.get("title", DEFAULTS["title"]))
    risk = str(spec.get("risk", DEFAULTS["risk"]) or "").upper()
    out["risk"] = risk if risk in RISKS else DEFAULTS["risk"]
    out["assured"] = bool(spec.get("assured", False))

    def str_list(value: Any) -> List[str]:
        if not isinstance(value, list):
            return []
        return [str(v) for v in value if isinstance(v, (str, int, float))]

    out["statements"] = str_list(spec.get("statements"))
    out["criteria"] = str_list(spec.get("criteria"))
    out["migration_steps"] = str_list(spec.get("migration_steps"))
    out["external_calls"] = str_list(spec.get("external_calls"))
    examples = spec.get("examples")
    normalized_examples: List[Dict[str, str]] = []
    if isinstance(examples, list):
        for entry in examples:
            if not isinstance(entry, dict):
                continue
            normalized_examples.append({
                "given": str(entry.get("given", "")),
                "when": str(entry.get("when", "")),
                "then": str(entry.get("then", "")),
            })
    out["examples"] = normalized_examples
    return out


def _is_compact(spec: Dict[str, Any]) -> bool:
    """Compact work is never burdened: not assured, or risk R0/R1."""
    return (not spec["assured"]) or (spec["risk"] in ("R0", "R1"))


def _has_ownership_phrase(text: str) -> bool:
    lower = text.lower()
    for phrase in OWNERSHIP_PHRASES:
        if phrase in lower:
            return True
    for actor in NAMED_OWNERS:
        if re.search(r"\b%s\b" % re.escape(actor), lower):
            return True
    return False


def _sentences(text: str) -> List[str]:
    parts = _SENTENCE_SPLIT_RE.findall(text)
    return [p.strip() for p in parts if p.strip()]


def _sentence_has_measure(sentence: str) -> bool:
    if _DIGIT_RE.search(sentence):
        return True
    lower = sentence.lower()
    if _MS_RE.search(lower):
        return True
    for unit in MEASURE_UNITS:
        if unit in ("ms", "%"):
            continue
        if re.search(r"\b%s\b" % re.escape(unit), lower):
            return True
    return False


def _check_ambiguous_owner(spec: Dict[str, Any]) -> List[Dict[str, str]]:
    findings: List[Dict[str, str]] = []
    for statement in spec["statements"]:
        lower = statement.lower()
        if not any(k in lower for k in OWNERSHIP_KEYWORDS):
            continue
        if _has_ownership_phrase(statement):
            continue
        findings.append({
            "id": "ambiguous_owner-%d" % (len(findings) + 1),
            "rule": "ambiguous_owner",
            "finding": (
                "ambiguous tenant ownership: name the owning actor "
                "(owned by / per-tenant) so isolation cannot drift"),
            "severity": "blocker",
            "excerpt": statement[:200],
        })
    return findings


def _check_contradictory_examples(
        spec: Dict[str, Any]) -> List[Dict[str, str]]:
    findings: List[Dict[str, str]] = []
    examples = spec["examples"]
    for i in range(len(examples)):
        for j in range(i + 1, len(examples)):
            first = examples[i]
            second = examples[j]
            if (first["given"] == second["given"]
                    and first["when"] == second["when"]
                    and first["then"] != second["then"]):
                findings.append({
                    "id": "contradictory_examples-%d"
                          % (len(findings) + 1),
                    "rule": "contradictory_examples",
                    "finding": (
                        "contradictory examples: the same given+when "
                        "promises two different thens; pin one outcome"),
                    "severity": "blocker",
                    "excerpt": ("given %r when %r then %r vs %r"
                                % (first["given"][:80],
                                   first["when"][:80],
                                   first["then"][:80],
                                   second["then"][:80])),
                })
                break
        if findings:
            break
    return findings


def _check_untestable_adjective(
        spec: Dict[str, Any]) -> List[Dict[str, str]]:
    findings: List[Dict[str, str]] = []
    texts = list(spec["statements"]) + list(spec["criteria"])
    for text in texts:
        for sentence in _sentences(text):
            lower = sentence.lower()
            for adj, adj_re in zip(VAGUE_ADJECTIVES, _ADJECTIVE_RES):
                if not adj_re.search(lower):
                    continue
                if _sentence_has_measure(sentence):
                    break
                findings.append({
                    "id": "untestable_adjective-%d" % (len(findings) + 1),
                    "rule": "untestable_adjective",
                    "finding": (
                        "untestable adjective %r: replace with a "
                        "measured bound (digits + unit) so a test "
                        "can pass or fail" % adj),
                    "severity": "major",
                    "excerpt": sentence[:200],
                })
                break
    return findings


def _check_missing_timeout(spec: Dict[str, Any]) -> List[Dict[str, str]]:
    if not spec["external_calls"]:
        return []
    texts = list(spec["statements"]) + list(spec["criteria"])
    for text in texts:
        lower = text.lower()
        if "timeout" in lower or "deadline" in lower:
            return []
        if re.search(r"\bseconds?\b", lower):
            return []
        if _MS_RE.search(lower):
            return []
    return [{
        "id": "missing_timeout-1",
        "rule": "missing_timeout",
        "finding": (
            "missing timeout: external call %r has no timeout/deadline "
            "bound; name the bound so verification can observe it"
            % spec["external_calls"][0][:80]),
        "severity": "blocker",
        "excerpt": spec["external_calls"][0][:200],
    }]


def _check_hidden_migration_order(
        spec: Dict[str, Any]) -> List[Dict[str, str]]:
    if len(spec["migration_steps"]) <= 1:
        return []
    texts = list(spec["statements"]) + list(spec["criteria"])
    for text in texts:
        lower = text.lower()
        if any(word in lower for word in ORDER_WORDS):
            return []
    return [{
        "id": "hidden_migration_order-1",
        "rule": "hidden_migration_order",
        "finding": (
            "hidden migration order: %d steps with no before/after/"
            "order/phase wording; state the ordering so steps "
            "cannot run out of sequence" % len(spec["migration_steps"])),
        "severity": "blocker",
        "excerpt": "; ".join(spec["migration_steps"])[:200],
    }]


def _check_overconstrained(spec: Dict[str, Any]) -> List[Dict[str, str]]:
    findings: List[Dict[str, str]] = []
    for criterion in spec["criteria"]:
        lower = criterion.lower()
        hit = None
        for marker in IMPLEMENTATION_MARKERS:
            if marker.startswith("."):
                if marker in lower:
                    hit = marker
                    break
            else:
                if re.search(r"\b%s\b" % re.escape(marker), lower):
                    hit = marker
                    break
        if hit is None:
            continue
        findings.append({
            "id": "overconstrained_implementation-%d" % (len(findings) + 1),
            "rule": "overconstrained_implementation",
            "finding": (
                "overconstrained implementation %r: state the "
                "observable behavior, not the storage or library, "
                "so the Spec stays implementation-free" % hit),
            "severity": "major",
            "excerpt": criterion[:200],
        })
    return findings


def _check_giant_spec(spec: Dict[str, Any]) -> List[Dict[str, str]]:
    total = len(spec["statements"]) + len(spec["criteria"])
    if total <= 20:
        return []
    return [{
        "id": "giant_spec-1",
        "rule": "giant_spec",
        "finding": (
            "giant Spec: %d statements + criteria exceed the 20-item "
            "ceiling; split the Spec into thin slices" % total),
        "severity": "blocker",
        "excerpt": spec.get("title", "")[:200] or "%d items" % total,
    }]


def critique(spec: Dict[str, Any]) -> CritiqueResult:
    """Critique one Spec as plain data in, plain data out; no I/O.

    Compact scope (not assured, or risk R0/R1) returns skipped with
    no findings. Assured R2/R3 runs the seven frozen rules in
    precedence order.
    """
    normalized = _normalize(spec)
    if _is_compact(normalized):
        return CritiqueResult(status="skipped", findings=[], scope="compact")
    findings: List[Dict[str, str]] = []
    findings.extend(_check_ambiguous_owner(normalized))
    findings.extend(_check_contradictory_examples(normalized))
    findings.extend(_check_untestable_adjective(normalized))
    findings.extend(_check_missing_timeout(normalized))
    findings.extend(_check_hidden_migration_order(normalized))
    findings.extend(_check_overconstrained(normalized))
    findings.extend(_check_giant_spec(normalized))
    return CritiqueResult(
        status="critiqued", findings=findings, scope="assured")


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


def validate_eval(corpus: Any) -> Tuple[List[str], List[Dict[str, Any]]]:
    """Validate a frozen spec-critic eval document.

    Returns (findings, entries); an empty findings list means the
    eval is a valid frozen oracle: IDs unique and well-formed, all 8
    classes present, and every expected_rules equals the computed
    critique rules with matching scope.
    """
    entries = corpus.get("entries") if isinstance(corpus, dict) else corpus
    if not isinstance(entries, list):
        return (["eval must be a JSON object with an 'entries' array "
                 "(or a bare array)"], [])
    findings: List[str] = []
    seen: Dict[str, int] = {}
    classes_found = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            findings.append("entries[%d] is not a mapping" % index)
            continue
        cid = str(entry.get("id", ""))
        if not _CORPUS_ID_RE.match(cid):
            findings.append(
                "entry %r: id is not spec-critic.<class>.<nn>" % cid)
        else:
            classes_found.add(cid.split(".")[1])
        if cid in seen:
            findings.append(
                "duplicate eval id %s (entries %d and %d)"
                % (cid, seen[cid], index))
        else:
            seen[cid] = index
        spec = entry.get("spec")
        if not isinstance(spec, dict):
            findings.append("entry %s: spec must be a mapping" % cid)
            continue
        expected_rules = entry.get("expected_rules")
        if not isinstance(expected_rules, list):
            findings.append(
                "entry %s: expected_rules must be a list" % cid)
            continue
        expected_scope = entry.get("expected_scope")
        if expected_scope not in ("assured", "compact"):
            findings.append(
                "entry %s: expected_scope must be assured|compact" % cid)
        result = critique(spec)
        computed = sorted({f["rule"] for f in result.findings})
        if sorted(str(r) for r in expected_rules) != computed:
            findings.append(
                "entry %s: expected_rules %r != critique %r"
                % (cid, sorted(str(r) for r in expected_rules), computed))
        if expected_scope in ("assured", "compact"):
            if result.scope != expected_scope:
                findings.append(
                    "entry %s: expected_scope %r != critique scope %r"
                    % (cid, expected_scope, result.scope))
        if not str(entry.get("note", "")).strip():
            findings.append(
                "entry %s: a one-line adjudication note is required"
                % cid)
    for cls in CLASSES:
        if cls not in classes_found:
            findings.append(
                "class %r has no entries (all %d classes are required)"
                % (cls, len(CLASSES)))
    return findings, entries


def gates_ready(spec: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Ready gate: assured R2/R3 needs zero blocker findings.

    Compact work is always ready. Returns (ready, reasons); reasons
    is empty when ready.
    """
    normalized = _normalize(spec)
    if _is_compact(normalized):
        return True, []
    result = critique(normalized)
    blockers = [f for f in result.findings if f.get("severity") == "blocker"]
    if blockers:
        return False, [
            "%s: %s" % (f["rule"], f["finding"]) for f in blockers]
    return True, []
