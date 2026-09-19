"""Stage 29 Standard half: verification mold contract for thin slices.

One Mold binds ONE implementation slice's behavior claims to
evidence: each claim names one observable outcome with its failure
shape and risk, and each test names the claims it evidences, the
technique used, how the expected result is determined (oracle), the
externally observable result asserted, what is mocked, and whether
it reaches into internals. The contract is load-bearing for Stages
30-35: it rejects missing, duplicated, coupled, mocked, over-
constrained, or unobservable evidence before verification design.

Mold shape (plain data; missing keys fall back to a total defaults
dict, never a crash)::

    {"mold": str,                     # mold name (artifact key)
     "slice": str,                    # slice/implementation unit
     "spec_ref": str,                 # stable Spec ID
     "claims": [{"id": str, "behavior": str,
                 "failure_shape": "crud"|"state"|"auth"|"parse"|
                                  "migration"|"workflow"|"ui"|
                                  "control_plane",
                 "risk": "R0"|"R1"|"R2"|"R3"}, ...],
     "tests": [{"id": str, "claims": [str, ...],
                "technique": str, "oracle": str,
                "observable": str, "mocks": [str, ...],
                "covers_internals": bool}, ...],
     "evidence": [{"claim": str, "kind": str,
                   "source": str}, ...]}

Deterministic rejection rules (frozen precedence, first listed
first checked; findings appended in this order, so output order is
stable):

1. ``missing-claim`` — a test whose ``claims`` list is empty, a
   declared claim with no evidencing test, or a test referencing
   an undeclared claim id -> blocker.
2. ``duplicate-weak-evidence`` — two or more tests asserting the
   SAME claim id with the SAME technique and identical
   ``observable`` text (exact string match) count as duplicate
   weak evidence, not corroboration -> major.
3. ``implementation-coupled-oracle`` — a test whose ``oracle``
   names implementation artifacts from the FROZEN marker list
   (library, table, column, SQL, Redis, Postgres, ORM, framework,
   .py, .ts, .json, internal) -> major.
4. ``mocked-behavior-under-test`` — a test whose ``mocks`` list
   holds the very claim it evidences (mock entry equal to the
   claim id, or containing "subject"/"system_under_test") ->
   blocker.
5. ``overconstrained-internals`` — ``covers_internals`` true on a
   test for a claim with risk R0/R1, or more than one
   ``covers_internals`` test for the same claim -> major.
6. ``unobservable-assertion`` — a test with an empty
   ``observable``, or one naming a private internal (a
   ``_``-prefixed word, or the phrase "internal state") rather
   than an external result -> blocker.

Findings are repair guidance (what to fix, with an excerpt),
never an error: ``FINDING_FIELDS`` names the five required keys,
``SEVERITIES`` names the allowed severities, and
``validate_finding`` returns repair strings (empty means valid).
``validate_mold`` returns structural repair strings (empty means
valid); ``select_technique`` is the frozen failure-shape to
default-technique mapping (technique selection is by failure
shape and risk, never by quota); ``validate_corpus`` checks the
frozen positive/rejection fixture oracle.

This module consumes Molds as plain data and performs no
filesystem access itself.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

RISKS = ("R0", "R1", "R2", "R3")

FINDING_FIELDS = ("id", "rule", "finding", "severity", "excerpt")

SEVERITIES = ("blocker", "major", "minor")

RULES = (
    "missing-claim",
    "duplicate-weak-evidence",
    "implementation-coupled-oracle",
    "mocked-behavior-under-test",
    "overconstrained-internals",
    "unobservable-assertion",
)

POSITIVE_CLASSES = (
    "crud", "retry", "auth", "parser", "migration", "workflow",
    "ui", "control-plane",
)

NEGATIVE_CLASSES = (
    "missing-claim", "duplicate-weak-evidence",
    "implementation-coupled-oracle", "mocked-behavior-under-test",
    "overconstrained-internals", "unobservable-assertion",
)

FAILURE_SHAPES = (
    "crud", "state", "auth", "parse", "migration", "workflow",
    "ui", "control_plane",
)

TECHNIQUES = (
    "example_based", "property_based", "mutation_check",
    "contract_test", "scenario_test",
)

TECHNIQUE_MAP = {
    "crud": "example_based",
    "state": "scenario_test",
    "auth": "example_based",
    "parse": "property_based",
    "migration": "scenario_test",
    "workflow": "scenario_test",
    "ui": "example_based",
    "control_plane": "contract_test",
}

IMPLEMENTATION_MARKERS = (
    "library", "table", "column", "sql", "redis", "postgres",
    "orm", "framework", ".py", ".ts", ".json", "internal",
)

DEFAULTS: Dict[str, Any] = {
    "mold": "",
    "slice": "",
    "spec_ref": "",
    "claims": [],
    "tests": [],
    "evidence": [],
}

_CORPUS_POS_RE = re.compile(r"^mold-positive\.[a-z-]+\.\d{2}$")
_CORPUS_NEG_RE = re.compile(r"^mold-negative\.[a-z-]+\.\d{2}$")

_MARKER_RES = [
    re.compile(r"\b%s\b" % re.escape(word))
    for word in IMPLEMENTATION_MARKERS if not word.startswith(".")
]

_PRIVATE_RE = re.compile(r"\b_[A-Za-z_][A-Za-z0-9_]*")


@dataclass
class MoldResult:
    """One mold validation outcome for one implementation slice."""

    findings: List[Dict[str, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.findings


def _normalize(mold: Dict[str, Any]) -> Dict[str, Any]:
    """Fill a total defaults dict so partial input never crashes."""
    mold = mold if isinstance(mold, dict) else {}
    out: Dict[str, Any] = {}
    out["mold"] = str(mold.get("mold", DEFAULTS["mold"]))
    out["slice"] = str(mold.get("slice", DEFAULTS["slice"]))
    out["spec_ref"] = str(mold.get("spec_ref", DEFAULTS["spec_ref"]))

    def str_list(value: Any) -> List[str]:
        if not isinstance(value, list):
            return []
        return [str(v) for v in value if isinstance(v, (str, int, float))]

    claims_raw = mold.get("claims")
    claims: List[Dict[str, Any]] = []
    if isinstance(claims_raw, list):
        for entry in claims_raw:
            if not isinstance(entry, dict):
                continue
            risk = str(entry.get("risk", "") or "").upper()
            claims.append({
                "id": str(entry.get("id", "")),
                "behavior": str(entry.get("behavior", "")),
                "failure_shape": str(entry.get("failure_shape", "")),
                "risk": risk if risk in RISKS else "R1",
            })
    out["claims"] = claims
    tests_raw = mold.get("tests")
    tests: List[Dict[str, Any]] = []
    if isinstance(tests_raw, list):
        for entry in tests_raw:
            if not isinstance(entry, dict):
                continue
            mocks = entry.get("mocks")
            if isinstance(mocks, list):
                mock_list = [str(v) for v in mocks
                             if isinstance(v, (str, int, float))]
            else:
                mock_list = []
            tests.append({
                "id": str(entry.get("id", "")),
                "claims": str_list(entry.get("claims")),
                "technique": str(entry.get("technique", "")),
                "oracle": str(entry.get("oracle", "")),
                "observable": str(entry.get("observable", "")),
                "mocks": mock_list,
                "covers_internals": bool(entry.get("covers_internals",
                                                  False)),
            })
    out["tests"] = tests
    evidence_raw = mold.get("evidence")
    evidence: List[Dict[str, str]] = []
    if isinstance(evidence_raw, list):
        for entry in evidence_raw:
            if not isinstance(entry, dict):
                continue
            evidence.append({
                "claim": str(entry.get("claim", "")),
                "kind": str(entry.get("kind", "")),
                "source": str(entry.get("source", "")),
            })
    out["evidence"] = evidence
    return out


def _check_missing_claim(mold: Dict[str, Any]) -> List[Dict[str, str]]:
    findings: List[Dict[str, str]] = []
    declared = [c["id"] for c in mold["claims"]]
    declared_set = set(declared)
    evidenced: set = set()
    for test in mold["tests"]:
        for cid in test["claims"]:
            evidenced.add(cid)
    for test in mold["tests"]:
        if not test["claims"]:
            findings.append({
                "id": "missing-claim-%d" % (len(findings) + 1),
                "rule": "missing-claim",
                "finding": (
                    "test %r evidences no claim: name at least one "
                    "declared claim id so the binding cannot point "
                    "nowhere" % test["id"][:80]),
                "severity": "blocker",
                "excerpt": test["id"][:200] or "(unnamed test)",
            })
    for claim in mold["claims"]:
        if claim["id"] not in evidenced:
            findings.append({
                "id": "missing-claim-%d" % (len(findings) + 1),
                "rule": "missing-claim",
                "finding": (
                    "claim %r has no evidencing test: add a test "
                    "that names this claim id" % claim["id"][:80]),
                "severity": "blocker",
                "excerpt": claim["id"][:200] or "(unnamed claim)",
            })
    for test in mold["tests"]:
        for cid in test["claims"]:
            if cid not in declared_set:
                findings.append({
                    "id": "missing-claim-%d" % (len(findings) + 1),
                    "rule": "missing-claim",
                    "finding": (
                        "test %r references unknown claim %r: point "
                        "at a declared claim id" % (test["id"][:60],
                                                    cid[:60])),
                    "severity": "blocker",
                    "excerpt": ("%s -> %s" % (test["id"],
                                             cid))[:200],
                })
    return findings


def _check_duplicate_weak_evidence(
        mold: Dict[str, Any]) -> List[Dict[str, str]]:
    findings: List[Dict[str, str]] = []
    for claim in mold["claims"]:
        cid = claim["id"]
        group: Dict[Tuple[str, str], List[str]] = {}
        for test in mold["tests"]:
            if cid not in test["claims"]:
                continue
            key = (test["technique"], test["observable"])
            group.setdefault(key, []).append(test["id"])
        for (technique, observable), test_ids in group.items():
            if len(test_ids) < 2:
                continue
            findings.append({
                "id": "duplicate-weak-evidence-%d" % (len(findings) + 1),
                "rule": "duplicate-weak-evidence",
                "finding": (
                    "claim %r is asserted %d times with technique "
                    "%r and identical observable text: vary the "
                    "technique or the observable so the second "
                    "test corroborates instead of repeating"
                    % (cid[:60], len(test_ids), technique[:40])),
                "severity": "major",
                "excerpt": ("%s: %s" % (cid, observable))[:200],
            })
    return findings


def _check_implementation_coupled_oracle(
        mold: Dict[str, Any]) -> List[Dict[str, str]]:
    findings: List[Dict[str, str]] = []
    for test in mold["tests"]:
        lower = test["oracle"].lower()
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
            "id": "implementation-coupled-oracle-%d" % (len(findings) + 1),
            "rule": "implementation-coupled-oracle",
            "finding": (
                "test %r oracle names implementation artifact %r: "
                "state the observable behavior instead so the "
                "mold stays implementation-free" % (test["id"][:60],
                                                    hit)),
            "severity": "major",
            "excerpt": ("%s: %s" % (test["id"],
                                   test["oracle"]))[:200],
        })
    return findings


def _check_mocked_behavior(
        mold: Dict[str, Any]) -> List[Dict[str, str]]:
    findings: List[Dict[str, str]] = []
    for test in mold["tests"]:
        mocked = None
        for cid in test["claims"]:
            for mock in test["mocks"]:
                low = mock.lower()
                if mock == cid or "subject" in low \
                        or "system_under_test" in low:
                    mocked = mock
                    break
            if mocked is not None:
                break
        if mocked is None:
            continue
        findings.append({
            "id": "mocked-behavior-under-test-%d" % (len(findings) + 1),
            "rule": "mocked-behavior-under-test",
            "finding": (
                "test %r mocks the behavior it evidences (%r): "
                "exercise the real subject so the test can fail "
                "for the right reason" % (test["id"][:60],
                                           mocked[:60])),
            "severity": "blocker",
            "excerpt": ("%s mocks %s" % (test["id"], mocked))[:200],
        })
    return findings


def _check_overconstrained(
        mold: Dict[str, Any]) -> List[Dict[str, str]]:
    findings: List[Dict[str, str]] = []
    risk_of = {c["id"]: c["risk"] for c in mold["claims"]}
    for test in mold["tests"]:
        if not test["covers_internals"]:
            continue
        low_risk = [cid for cid in test["claims"]
                    if risk_of.get(cid) in ("R0", "R1")]
        if not low_risk:
            continue
        findings.append({
            "id": "overconstrained-internals-%d" % (len(findings) + 1),
            "rule": "overconstrained-internals",
            "finding": (
                "test %r reaches into internals for low-risk "
                "claim %r: assert the external result instead"
                % (test["id"][:60], low_risk[0][:60])),
            "severity": "major",
            "excerpt": ("%s -> %s" % (test["id"],
                                     low_risk[0]))[:200],
        })
    counts: Dict[str, int] = {}
    for test in mold["tests"]:
        if not test["covers_internals"]:
            continue
        for cid in test["claims"]:
            counts[cid] = counts.get(cid, 0) + 1
    for cid, total in counts.items():
        if total <= 1:
            continue
        findings.append({
            "id": "overconstrained-internals-%d" % (len(findings) + 1),
            "rule": "overconstrained-internals",
            "finding": (
                "claim %r is asserted through internals by %d "
                "tests: keep at most one internals view per "
                "claim" % (cid[:60], total)),
            "severity": "major",
            "excerpt": cid[:200],
        })
    return findings


def _check_unobservable(
        mold: Dict[str, Any]) -> List[Dict[str, str]]:
    findings: List[Dict[str, str]] = []
    for test in mold["tests"]:
        observable = test["observable"]
        if not observable.strip():
            findings.append({
                "id": "unobservable-assertion-%d" % (len(findings) + 1),
                "rule": "unobservable-assertion",
                "finding": (
                    "test %r asserts no observable result: name "
                    "the externally visible outcome" % test["id"][:80]),
                "severity": "blocker",
                "excerpt": test["id"][:200] or "(unnamed test)",
            })
        elif _PRIVATE_RE.search(observable) \
                or "internal state" in observable.lower():
            findings.append({
                "id": "unobservable-assertion-%d" % (len(findings) + 1),
                "rule": "unobservable-assertion",
                "finding": (
                    "test %r asserts a private internal, not an "
                    "external result: restate the observable so "
                    "the world can see it" % test["id"][:60]),
                "severity": "blocker",
                "excerpt": ("%s: %s" % (test["id"],
                                       observable))[:200],
            })
    return findings


def critique(mold: Dict[str, Any]) -> MoldResult:
    """Validate one Mold as plain data in, plain data out; no I/O.

    Runs the six frozen rejection rules in precedence order.
    """
    normalized = _normalize(mold)
    findings: List[Dict[str, str]] = []
    findings.extend(_check_missing_claim(normalized))
    findings.extend(_check_duplicate_weak_evidence(normalized))
    findings.extend(_check_implementation_coupled_oracle(normalized))
    findings.extend(_check_mocked_behavior(normalized))
    findings.extend(_check_overconstrained(normalized))
    findings.extend(_check_unobservable(normalized))
    return MoldResult(findings=findings)


def validate_mold(mold: Any) -> List[str]:
    """Return repair strings for one Mold; empty means valid."""
    if not isinstance(mold, dict):
        return ["mold must be a mapping of plain data, not %s"
                % type(mold).__name__]
    repairs: List[str] = []
    for key in ("mold", "slice", "spec_ref"):
        value = mold.get(key)
        if key not in mold:
            repairs.append("missing key %r: add it to the mold" % key)
        elif not str(value).strip():
            repairs.append("key %r must be a non-empty string" % key)
    claims = mold.get("claims")
    if not isinstance(claims, list) or not claims:
        repairs.append("key 'claims' must be a non-empty list of "
                       "behavior claims")
        claim_ids: List[str] = []
    else:
        claim_ids = [str(c.get("id", "")) for c in claims
                     if isinstance(c, dict)]
        seen: Dict[str, int] = {}
        for index, cid in enumerate(claim_ids):
            if not cid.strip():
                repairs.append("claims[%d] has no id: give every "
                               "claim a stable id" % index)
            elif cid in seen:
                repairs.append("duplicate claim id %r (claims %d "
                               "and %d): ids must be unique"
                               % (cid, seen[cid], index))
            else:
                seen[cid] = index
    tests = mold.get("tests")
    if not isinstance(tests, list) or not tests:
        repairs.append("key 'tests' must be a non-empty list of "
                       "evidence tests")
    else:
        declared = set(claim_ids)
        evidenced: set = set()
        for test in tests:
            if not isinstance(test, dict):
                repairs.append("a test entry is not a mapping: use "
                               "plain data for every test")
                continue
            tids = test.get("claims")
            if not isinstance(tids, list) or not tids:
                repairs.append("test %r evidences no claim: name at "
                               "least one declared claim id"
                               % str(test.get("id", ""))[:60])
                continue
            for cid in tids:
                cid_str = str(cid)
                evidenced.add(cid_str)
                if cid_str not in declared:
                    repairs.append("test %r references unknown claim "
                                   "%r: point at a declared claim id"
                                   % (str(test.get("id", ""))[:60],
                                      cid_str[:60]))
        for cid in claim_ids:
            if cid and cid not in evidenced:
                repairs.append("missing claim evidence for %r: add a "
                               "test that names this claim id" % cid)
    for item in critique(mold).findings:
        repairs.append("%s: %s" % (item["rule"], item["finding"]))
    return repairs


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


def select_technique(claim: Dict[str, Any]) -> str:
    """Frozen failure-shape to default-technique mapping.

    Technique selection is by failure shape and risk, never by
    quota: crud/auth/ui default to example_based, state/migration/
    workflow to scenario_test, parse to property_based, and
    control_plane to contract_test.
    """
    shape = ""
    if isinstance(claim, dict):
        shape = str(claim.get("failure_shape", ""))
    return TECHNIQUE_MAP.get(shape, "example_based")


def _entries_of(corpus: Any) -> List[Dict[str, Any]]:
    if isinstance(corpus, dict):
        entries = corpus.get("entries")
    else:
        entries = corpus
    if not isinstance(entries, list):
        return []
    return entries


def validate_corpus(positive_corpus: Any,
                    negative_corpus: Any) -> Tuple[List[str],
                                                  List[Dict[str, Any]]]:
    """Validate the frozen positive/rejection fixture oracle.

    Returns (findings, entries); an empty findings list means the
    corpus is a valid frozen oracle: both documents frozen, IDs
    unique and well-formed, all 8 positive and 6 negative classes
    present, every positive clean, and every negative producing
    exactly its expected_rules.
    """
    findings: List[str] = []
    for label, corpus in (("positive", positive_corpus),
                          ("negative", negative_corpus)):
        if isinstance(corpus, dict):
            if corpus.get("_frozen") is not True:
                findings.append("%s corpus is not frozen: set "
                                "\"_frozen\": true" % label)
            provenance = str(corpus.get("_provenance", ""))
            if "Stage 29 #120" not in provenance:
                findings.append("%s corpus provenance must name "
                                "\"Stage 29 #120\"" % label)
    positives = _entries_of(positive_corpus)
    negatives = _entries_of(negative_corpus)
    if not isinstance(positives, list) or len(positives) != 8:
        findings.append("positive corpus holds %d entries, want "
                        "exactly 8" % len(positives
                                          if isinstance(positives,
                                                        list) else -1))
        positives = positives if isinstance(positives, list) else []
    if not isinstance(negatives, list) or len(negatives) != 6:
        findings.append("negative corpus holds %d entries, want "
                        "exactly 6" % len(negatives
                                          if isinstance(negatives,
                                                        list) else -1))
        negatives = negatives if isinstance(negatives, list) else []
    seen: Dict[str, str] = {}
    pos_classes = set()
    neg_classes = set()
    for mold in positives:
        if not isinstance(mold, dict):
            findings.append("a positive entry is not a mapping")
            continue
        mid = str(mold.get("mold", ""))
        if not _CORPUS_POS_RE.match(mid):
            findings.append("entry %r: id is not "
                            "mold-positive.<class>.<nn>" % mid)
        else:
            pos_classes.add(mid.split(".")[1])
        if mid in seen:
            findings.append("duplicate mold id %s (%s and positive)"
                            % (mid, seen[mid]))
        else:
            seen[mid] = "positive"
        computed = sorted({f["rule"]
                           for f in critique(mold).findings})
        if computed:
            findings.append("positive %s has findings %r, want none"
                            % (mid, computed))
    for mold in negatives:
        if not isinstance(mold, dict):
            findings.append("a negative entry is not a mapping")
            continue
        mid = str(mold.get("mold", ""))
        if not _CORPUS_NEG_RE.match(mid):
            findings.append("entry %r: id is not "
                            "mold-negative.<class>.<nn>" % mid)
        else:
            neg_classes.add(mid.split(".")[1])
        if mid in seen:
            findings.append("duplicate mold id %s (%s and negative)"
                            % (mid, seen[mid]))
        else:
            seen[mid] = "negative"
        expected = mold.get("expected_rules")
        if not isinstance(expected, list):
            findings.append("entry %s: expected_rules must be a list"
                            % mid)
            continue
        computed = sorted({f["rule"]
                           for f in critique(mold).findings})
        if sorted(str(r) for r in expected) != computed:
            findings.append("entry %s: expected_rules %r != critique "
                            "%r" % (mid, sorted(str(r)
                                                for r in expected),
                                    computed))
        if not str(mold.get("note", "")).strip():
            findings.append("entry %s: a one-line adjudication note "
                            "is required" % mid)
    for cls in POSITIVE_CLASSES:
        if cls not in pos_classes:
            findings.append("positive class %r has no entries (all 8 "
                            "positive classes are required)" % cls)
    for cls in NEGATIVE_CLASSES:
        if cls not in neg_classes:
            findings.append("negative class %r has no entries (all 6 "
                            "negative classes are required)" % cls)
    return findings, positives + negatives
