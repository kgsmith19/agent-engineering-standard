"""Stage 37 Standard half: stack-native quality and architecture gates.

Portable declaration plus fixtures for repository-selected
linters, analyzers, dead-code, duplication, dependency, and
architecture tests. The consuming repository declares its real
tool commands per stack in ``project.yaml`` under
``verification``; this module checks the declaration shape
(mutual exclusion within a stack, real commands, generated-file
exclusion) and classifies fixture outcomes per check class.

Fixture ``kind`` values (frozen, first listed first checked)::

  mutually-exclusive pair  (Biome vs ESLint: exactly one selected)
  ruff / pyright           (Python lint + type correctness)
  roslyn / netarchtest     (dotnet correctness + direction)
  no-op rejected           (a no-op command is never a gate)
  bad import               (seeded bad import detected)
  dead export              (dead export detected)
  duplication              (duplicated block detected)
  dependency direction     (invalid direction rejected)
  synthetic issue          (scanner-synthetic issue recorded)
  generated excluded       (generated files excluded from scans)

``declare`` validates one verification profile (plain data;
missing keys fall back to total defaults, never a crash) and
``classify`` maps one fixture outcome to its finding. Findings
are repair guidance (what to fix, with an excerpt), never an
error: ``FINDING_FIELDS`` names the five required keys,
``SEVERITIES`` names the allowed severities, and
``validate_finding`` returns repair strings (empty means
valid). ``validate_quality_corpus`` checks the frozen oracle.
Pure functions: no I/O, no subprocess, no network —
declarations and outcomes in, violations out. Exhaustive
matrices run in CI; local runs stay fast and affected-only.
"""

from typing import Any, Dict, List, Optional, Tuple

import re as _re

# Frozen stack slots: one selected command each at most.
STACKS = ("ts", "python", "dotnet")

# Frozen check classes, in check order.
CLASSES = (
    "lint",
    "types",
    "dead-code",
    "duplication",
    "dependency",
    "architecture",
)

SEVERITIES = ("blocker", "major", "minor")

FINDING_FIELDS = ("id", "rule", "finding", "severity", "excerpt")

NO_OP_COMMANDS = ("true", "echo", ":", "exit 0", "echo ok", "echo done")

_ENTRY_ID_RE = _re.compile(r"^quality-gates\.[a-z-]+\.\d{2}$")


def _make_finding(rule: str, message: str, excerpt: str,
                  severity: str = "major") -> Dict[str, str]:
    """Build one structured quality finding dict."""
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
    for key in FINDING_FIELDS:
        if key not in finding:
            repairs.append("finding is missing required key %r" % key)
    rule = finding.get("rule")
    if "rule" in finding and rule not in CLASSES:
        repairs.append("finding rule %r is not a frozen Stage 37 "
                       "quality class" % (rule,))
    if "severity" in finding and finding.get("severity") not in SEVERITIES:
        repairs.append("finding severity %r must be "
                       "blocker|major|minor" % (finding.get("severity"),))
    return repairs


def _excerpt(profile: Any) -> str:
    """Short evidence excerpt naming the stack or fixture."""
    if isinstance(profile, dict):
        for key in ("stack", "fixture", "command", "name"):
            value = profile.get(key)
            if isinstance(value, (str, int, float)) and str(value).strip():
                return str(value)[:200]
    return "(profile)"


def _normalize_profile(profile: Any) -> Dict[str, Any]:
    """Fill total defaults so partial input never crashes."""
    profile = profile if isinstance(profile, dict) else {}
    stacks = profile.get("stacks")
    norm_stacks: Dict[str, Any] = {}
    if isinstance(stacks, dict):
        for stack in STACKS:
            entry = stacks.get(stack)
            norm_stacks[stack] = dict(entry) if isinstance(entry, dict) else {}
    else:
        for stack in STACKS:
            norm_stacks[stack] = {}
    return {
        "stacks": norm_stacks,
        "generated_excluded": bool(profile.get(
            "generated_excluded", False)),
    }


def _check_mutual_exclusion(profile: Dict[str, Any]) -> List[Dict[str, str]]:
    """TS stack: Biome and ESLint are mutually exclusive."""
    ts = profile["stacks"]["ts"]
    tools = ts.get("tools")
    selected = [str(t) for t in tools
                if isinstance(t, (str, int, float))] \
        if isinstance(tools, list) else []
    lowered = [t.lower() for t in selected]
    if "biome" in lowered and "eslint" in lowered:
        return [_make_finding(
            "lint",
            "Biome and ESLint both selected: pick exactly one "
            "per stack (mutual exclusion)",
            ",".join(sorted(selected))[:200] or "(ts)")]
    return []


def _check_no_op(profile: Dict[str, Any]) -> List[Dict[str, str]]:
    """Every selected command must be real; no-op gates rejected."""
    for stack in STACKS:
        command = str(profile["stacks"][stack].get("command", "") or "")
        if command.strip().lower() in NO_OP_COMMANDS:
            return [_make_finding(
                "lint",
                "stack %r declares no-op command %r: gates must "
                "run a real linter/analyzer" % (stack, command),
                command[:200])]
    return []


def _check_generated(profile: Dict[str, Any]) -> List[Dict[str, str]]:
    """Generated files stay excluded from scans."""
    if not profile["generated_excluded"]:
        return [_make_finding(
            "lint",
            "generated files not excluded: scans must skip "
            "generated output or every regeneration fails",
            "(generated)")]
    return []


def _check_classes(profile: Dict[str, Any]) -> List[Dict[str, str]]:
    """Every stack command maps to a frozen check class."""
    findings: List[Dict[str, str]] = []
    for stack in STACKS:
        entry = profile["stacks"][stack]
        command = str(entry.get("command", "") or "").strip()
        if not command:
            continue
        check_class = str(entry.get("class", "") or "")
        if check_class not in CLASSES:
            findings.append(_make_finding(
                "lint",
                "stack %r command %r names unknown class %r: "
                "use one of %s" % (stack, command, check_class,
                                   ", ".join(CLASSES)),
                command[:200]))
    return findings


_CHECKS = (
    _check_mutual_exclusion,
    _check_no_op,
    _check_generated,
    _check_classes,
)


class QualityResult:
    """One quality declaration outcome for one profile."""

    ok: bool = False
    findings: List[Dict[str, str]] = []  # type: ignore[assignment]

    def __init__(self, ok: bool = False,
                 findings: Optional[List[Dict[str, str]]] = None):
        self.ok = ok
        self.findings = list(findings or [])


def declare(profile: Any) -> QualityResult:
    """Validate one verification profile declaration.

    All frozen declaration checks run in order; any finding
    means the profile is not acceptable. A fully clean profile
    returns ``ok=True`` with zero findings. Pure function: no
    I/O, no subprocess, deterministic in its input. This
    validates the declaration; it never executes the tools.
    """
    normalized = _normalize_profile(profile)
    findings: List[Dict[str, str]] = []
    for check in _CHECKS:
        findings.extend(check(normalized))
    if findings:
        return QualityResult(ok=False, findings=findings)
    return QualityResult(ok=True, findings=[])


def _normalize_fixture(fixture: Any) -> Dict[str, Any]:
    """Fill total defaults so partial input never crashes."""
    fixture = fixture if isinstance(fixture, dict) else {}
    return {
        "kind": str(fixture.get("kind", "")),
        "stack": str(fixture.get("stack", "")),
        "detected": bool(fixture.get("detected", False)),
        "excluded": bool(fixture.get("excluded", False)),
        "command": str(fixture.get("command", "")),
    }


def classify(fixture: Any) -> QualityResult:
    """Map one fixture outcome to its finding.

    A fixture passes when its defect was detected (or its
    generated file excluded, or its command proven real); a
    missed defect, an executed no-op, or an unexcluded
    generated file is exactly one finding in its class. Pure
    function: no I/O, deterministic in its input.
    """
    item = _normalize_fixture(fixture)
    kind = item["kind"]
    if kind in ("bad-import", "dead-export", "duplication",
                "dependency-direction", "synthetic",
                "ruff", "pyright", "roslyn", "netarchtest"):
        check_class = {
            "bad-import": "lint", "dead-export": "dead-code",
            "duplication": "duplication",
            "dependency-direction": "dependency",
            "synthetic": "lint", "ruff": "lint",
            "pyright": "types", "roslyn": "lint",
            "netarchtest": "architecture",
        }[kind]
        if item["detected"]:
            return QualityResult(ok=True, findings=[])
        return QualityResult(ok=False, findings=[_make_finding(
            check_class,
            "fixture %r on stack %r missed its seeded defect: "
            "the gate must detect it" % (kind, item["stack"]),
            item["command"][:200] or "(%s)" % kind)])
    if kind == "no-op":
        if item["command"].strip().lower() in NO_OP_COMMANDS:
            return QualityResult(ok=False, findings=[_make_finding(
                "lint",
                "no-op command %r rejected: gates must run a "
                "real linter/analyzer" % item["command"],
                item["command"][:200])])
        return QualityResult(ok=True, findings=[])
    if kind == "mutual-exclusion":
        tools = [t.strip().lower()
                 for t in item["command"].split(",")]
        if "biome" in tools and "eslint" in tools:
            return QualityResult(ok=False, findings=[_make_finding(
                "lint",
                "Biome and ESLint both selected: pick exactly "
                "one per stack (mutual exclusion)",
                item["command"][:200])])
        return QualityResult(ok=True, findings=[])
    if kind == "generated-excluded":
        if item["excluded"]:
            return QualityResult(ok=True, findings=[])
        return QualityResult(ok=False, findings=[_make_finding(
            "lint",
            "generated file scanned: generated output must be "
            "excluded from scans",
            item["command"][:200] or "(generated)")])
    return QualityResult(ok=False, findings=[_make_finding(
        "lint",
        "unknown fixture kind %r: use a frozen Stage 37 kind"
        % kind,
        kind[:200] or "(kind)")])


def _entries_of(corpus: Any) -> List[Dict[str, Any]]:
    if isinstance(corpus, dict):
        entries = corpus.get("entries")
    else:
        entries = corpus
    if not isinstance(entries, list):
        return []
    return entries


def validate_quality_corpus(corpus: Any) -> Tuple[List[str],
                                                  List[Dict[str, Any]]]:
    """Validate the frozen quality fixture oracle.

    Returns (findings, entries); an empty findings list means
    the corpus is a valid frozen oracle: frozen marker set,
    stable provenance, at least 11 entries, unique well-formed
    IDs, every entry classifying to its expected class and ok
    flag, and all 6 quality classes covered.
    """
    if isinstance(corpus, dict):
        if corpus.get("_frozen") is not True:
            return (["quality corpus is not frozen: set "
                     "\"_frozen\": true"], [])
        provenance = str(corpus.get("_provenance", ""))
        if "Stage 37 #128" not in provenance:
            return (["quality corpus provenance must name "
                      "\"Stage 37 #128\""], [])
    elif not isinstance(corpus, list):
        return (["quality corpus must be a JSON object with an "
                 "'entries' array (or a bare array)"], [])
    entries = _entries_of(corpus)
    findings: List[str] = []
    if len(entries) < 11:
        findings.append("quality corpus holds %d entries, want "
                        "at least 11" % len(entries))
    seen: Dict[str, int] = {}
    covered = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            findings.append("entries[%d] is not a mapping" % index)
            continue
        cid = str(entry.get("id", ""))
        if not _ENTRY_ID_RE.match(cid):
            findings.append("entry %r: id is not "
                            "quality-gates.<class>.<nn>" % cid)
        if cid in seen:
            findings.append("duplicate entry id %s (entries %d "
                            "and %d)" % (cid, seen[cid], index))
        else:
            seen[cid] = index
        if not str(entry.get("note", "")).strip():
            findings.append("entry %s: a one-line adjudication note "
                            "is required" % cid)
        expected = entry.get("expected_class")
        if expected not in CLASSES:
            findings.append("entry %s: expected_class %r is not a "
                            "frozen Stage 37 quality class"
                            % (cid, expected))
            continue
        covered.add(str(expected))
        if "expected_ok" not in entry:
            findings.append("entry %s: expected_ok is required"
                            % cid)
        result = classify(entry.get("fixture", {}))
        computed = sorted({f["rule"] for f in result.findings})
        want = [] if entry.get("expected_ok") else [str(expected)]
        if want != computed:
            findings.append("entry %s: expected class %r != "
                            "classify %r"
                            % (cid, want, computed))
        if bool(entry.get("expected_ok")) != result.ok:
            findings.append("entry %s: expected_ok %r != "
                            "classify %r" % (cid, entry.get(
                                "expected_ok"),
                                result.ok))
    for rule in CLASSES:
        if rule not in covered:
            findings.append("class %r has no entries (all 6 "
                            "quality classes are required)"
                            % rule)
    return findings, entries


def clean_profile() -> Dict[str, Any]:
    """One clean verification profile (acceptable).

    TS selects Ruff-equivalent lint alone, Python declares Ruff
    plus Pyright classes, dotnet declares Roslyn plus
    NetArchTest classes; every command is real and generated
    files are excluded. Callers mutate one dimension per test.
    """
    return {
        "stacks": {
            "ts": {"tools": ["biome"],
                   "command": "biome check",
                   "class": "lint"},
            "python": {"tools": ["ruff"],
                       "command": "ruff check",
                       "class": "lint"},
            "dotnet": {"tools": ["roslyn"],
                       "command": "dotnet build",
                       "class": "lint"},
        },
        "generated_excluded": True,
    }
