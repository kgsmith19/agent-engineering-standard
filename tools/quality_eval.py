"""Stage 41 Standard half: the implementation-quality evaluation corpus.

Measure whether Builders produce minimum, clear, correct code
without rewarding superficial shortness. ``score`` grades one
solution against one task's adjudication (correctness first,
then charter/quality/plane/dependency conformance, then owned
complexity); ``validate_quality_eval_corpus`` checks the frozen
oracle. Tasks and solutions are plain data; missing keys fall
back to total defaults, never a crash.

Frozen scoring rules (correctness gates everything)::

  correctness  — an incorrect solution always loses, however
                 small (no shortness reward, ever).
  charter      — clean-charter violations cost.
  quality      — quality-gate misses cost.
  plane        — plane violations cost.
  dependency   — rejected dependencies cost.
  parsimony    — among fully correct, fully conforming
                 solutions, less owned complexity wins;
                 a necessary larger safety implementation
                 still beats any incorrect shortcut.

``score`` returns a (points, ranking-note) outcome per
solution; the corpus freezes tasks, adjudications, and
baseline provider results. Reviewer agreement is recorded per
task (two independent reviewers, rule-grounded). Findings use
the standard five keys via ``FINDING_FIELDS``; ``SEVERITIES``
names the allowed severities; ``validate_finding`` returns
repair strings (empty means valid). Pure functions: no I/O, no
subprocess, no network — tasks and solutions in, scores out.
Baseline measurement only: no blocking threshold until data
exists.
"""

from typing import Any, Dict, List, Optional, Tuple

import re as _re

# Frozen score dimensions, in tiebreak order after correctness.
DIMENSIONS = (
    "correctness",
    "charter",
    "quality",
    "plane",
    "dependency",
    "parsimony",
)

SEVERITIES = ("blocker", "major", "minor")

FINDING_FIELDS = ("id", "rule", "finding", "severity", "excerpt")

# Entry-ID shape for the frozen oracle.
_ENTRY_ID_RE = _re.compile(r"^quality-eval\.[a-z-]+\.\d{2}$")


def _make_finding(rule: str, message: str, excerpt: str,
                  severity: str = "major") -> Dict[str, str]:
    """Build one structured evaluation finding dict."""
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
    if "rule" in finding and rule not in DIMENSIONS:
        repairs.append("finding rule %r is not a frozen Stage 41 "
                       "evaluation dimension" % (rule,))
    if "severity" in finding and finding.get("severity") not in SEVERITIES:
        repairs.append("finding severity %r must be "
                       "blocker|major|minor" % (finding.get("severity"),))
    return repairs


def _normalize_solution(solution: Any) -> Dict[str, Any]:
    """Fill total defaults so partial input never crashes."""
    solution = solution if isinstance(solution, dict) else {}
    return {
        "id": str(solution.get("id", "")),
        "correct": bool(solution.get("correct", False)),
        "charter_clean": bool(solution.get(
            "charter_clean", False)),
        "quality_ok": bool(solution.get("quality_ok", False)),
        "plane_clean": bool(solution.get("plane_clean", False)),
        "dependency_ok": bool(solution.get(
            "dependency_ok", False)),
        "simplifier_touched": bool(solution.get(
            "simplifier_touched", False)),
        "owned_loc": int(solution.get("owned_loc") or 0),
        "reviewers_agree": bool(solution.get(
            "reviewers_agree", False)),
    }


class EvalScore:
    """One evaluation score for one solution."""

    points: int = 0
    wins: bool = False
    findings: List[Dict[str, str]] = []  # type: ignore[assignment]

    def __init__(self, points: int = 0, wins: bool = False,
                 findings: Optional[List[Dict[str, str]]] = None):
        self.points = points
        self.wins = wins
        self.findings = list(findings or [])


def score(solution: Any) -> EvalScore:
    """Grade one solution: correctness first, then conformance,
    then parsimony. An incorrect solution scores 0 and never
    wins; a correct fully-conforming solution scores 100 minus
    1 per 50 owned LOC (floor 60); each non-correctness miss
    costs 10. The simplifier is never favored: simplifier
    touch without conformance still loses every point it
    misses. Pure function: no I/O, deterministic in its input.
    """
    item = _normalize_solution(solution)
    if not item["correct"]:
        return EvalScore(points=0, wins=False, findings=[_make_finding(
            "correctness",
            "incorrect solution loses however small: no "
            "shortness reward, ever",
            item["id"][:200] or "(solution)",
            severity="blocker")])
    points = 100
    findings: List[Dict[str, str]] = []
    for dimension, flag in (("charter", item["charter_clean"]),
                            ("quality", item["quality_ok"]),
                            ("plane", item["plane_clean"]),
                            ("dependency", item["dependency_ok"])):
        if not flag:
            points -= 10
            findings.append(_make_finding(
                dimension,
                "%s non-conformance costs 10 points" % dimension,
                item["id"][:200] or "(solution)"))
    points -= min(40, item["owned_loc"] // 50)
    if not item["reviewers_agree"]:
        points -= 5
        findings.append(_make_finding(
            "parsimony",
            "reviewers disagree: agreement costs 5 points until "
            "rule-grounded consensus",
            item["id"][:200] or "(solution)"))
    points = max(0, points)
    return EvalScore(points=points, wins=True, findings=findings)


def rank(solutions: List[Any]) -> List[Dict[str, Any]]:
    """Rank solutions: winners first by points desc, then less
    owned LOC, then id. Incorrect solutions always sort last."""
    scored = [(score(s), _normalize_solution(s)) for s in solutions]
    scored.sort(key=lambda pair: (
        0 if pair[0].wins else 1,
        -pair[0].points,
        pair[1]["owned_loc"],
        pair[1]["id"]))
    return [{"id": item["id"], "points": result.points,
             "wins": result.wins} for result, item in scored]


def _entries_of(corpus: Any) -> List[Dict[str, Any]]:
    if isinstance(corpus, dict):
        entries = corpus.get("entries")
    else:
        entries = corpus
    if not isinstance(entries, list):
        return []
    return entries


def validate_quality_eval_corpus(corpus: Any) -> Tuple[List[str],
                                                       List[Dict[str, Any]]]:
    """Validate the frozen evaluation fixture oracle.

    Returns (findings, entries); an empty findings list means
    the corpus is a valid frozen oracle: frozen marker set,
    stable provenance, at least 8 entries, unique well-formed
    IDs, every entry's ranked winner matching expected_winner
    with rule-grounded reviewer agreement, and all 6
    dimensions exercised.
    """
    if isinstance(corpus, dict):
        if corpus.get("_frozen") is not True:
            return (["quality-eval corpus is not frozen: set "
                     "\"_frozen\": true"], [])
        provenance = str(corpus.get("_provenance", ""))
        if "Stage 41 #132" not in provenance:
            return (["quality-eval corpus provenance must name "
                      "\"Stage 41 #132\""], [])
    elif not isinstance(corpus, list):
        return (["quality-eval corpus must be a JSON object with an "
                 "'entries' array (or a bare array)"], [])
    entries = _entries_of(corpus)
    findings: List[str] = []
    if len(entries) < 8:
        findings.append("quality-eval corpus holds %d entries, want "
                        "at least 8" % len(entries))
    seen: Dict[str, int] = {}
    exercised: set = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            findings.append("entries[%d] is not a mapping" % index)
            continue
        cid = str(entry.get("id", ""))
        if not _ENTRY_ID_RE.match(cid):
            findings.append("entry %r: id is not "
                            "quality-eval.<class>.<nn>" % cid)
        if cid in seen:
            findings.append("duplicate entry id %s (entries %d "
                            "and %d)" % (cid, seen[cid], index))
        else:
            seen[cid] = index
        if not str(entry.get("note", "")).strip():
            findings.append("entry %s: a one-line adjudication note "
                            "is required" % cid)
        solutions = entry.get("solutions")
        if not isinstance(solutions, list) or not solutions:
            findings.append("entry %s: solutions must be a "
                            "non-empty list" % cid)
            continue
        expected = entry.get("expected_winner")
        ranked = rank(solutions)
        if not ranked or ranked[0]["id"] != expected:
            findings.append("entry %s: expected_winner %r != "
                            "ranked %r" % (cid, expected,
                                           ranked[0]["id"] if ranked
                                           else None))
        for solution in solutions:
            item = _normalize_solution(solution)
            result = score(solution)
            if result.wins:
                exercised.add("correctness")
                if not item["charter_clean"]:
                    exercised.add("charter")
                if not item["quality_ok"]:
                    exercised.add("quality")
                if not item["plane_clean"]:
                    exercised.add("plane")
                if not item["dependency_ok"]:
                    exercised.add("dependency")
                exercised.add("parsimony")
            else:
                exercised.add("correctness")
            if not item["reviewers_agree"]:
                findings.append("entry %s solution %r: reviewers "
                                "must agree on rule-grounded "
                                "results" % (cid, item["id"]))
    for dimension in DIMENSIONS:
        if dimension not in exercised:
            findings.append("dimension %r never exercised (all 6 "
                            "dimensions are required)" % dimension)
    return findings, entries
