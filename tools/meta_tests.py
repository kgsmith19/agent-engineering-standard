"""Stage 31 Standard half: process meta-tests for Arc A sessions.

While ``tools/mold_qualification.py`` proves a Mold deserves
trust, this module proves the *process* that produced it stayed
honest: every file written in Arc A (Stages 25a-31) must sit
outside production implementation paths, no protected path may
have been touched, every expected control canary must have run,
and every recorded hash must match. The qualification gate
authorizes production implementation to begin, so a process
lapse (a quiet production write, a skipped control, a doctored
artifact) would corrupt every downstream evidence claim.

Claims shape (plain data; missing keys fall back to total
defaults, never a crash)::

    {"production_writes": [str, ...],  # every file written in Arc A
     "protected_paths": [str, ...],    # writes that must never appear
     "controls_run": [str, ...],       # control canary ids executed
     "controls_expected": [str, ...],  # control canaries that must run
     "hash_pairs": [{"path": str, "expected": str, "actual": str},
                    ...]}

Frozen rules (first listed first checked; repair strings
appended in this order, so output order is stable):

1. ``production-write`` — any entry in ``production_writes``
   under a frozen production prefix (``src/``, ``packages/``,
   ``apps/``, ``services/``, matched on whole path segments
   so ``src-evil/`` never matches ``src/``) ==> repair naming
   the path. Arc A authorizes no production writes.
2. ``protected-path`` — any ``production_writes`` entry equal
   to or under a ``protected_paths`` entry ==> repair naming
   the path.
3. ``missing-control`` — every ``controls_expected`` id must
   appear in ``controls_run`` ==> one repair per missing id.
4. ``hash-mismatch`` — every hash pair's ``actual`` must equal
   its ``expected`` ==> one repair per mismatching path.

``check_meta`` returns repair strings; empty means the process
is clean. This module performs no I/O and never reads git
itself: the caller assembles the file list by hand from merge
commit stats, keeping the tool pure data in, plain data out.
"""

from typing import Any, Dict, List

PRODUCTION_PREFIXES = ("src/", "packages/", "apps/", "services/")


def _matches_prefix(normalized: str, prefix: str) -> bool:
    """True when a normalized path sits at or under a prefix.

    Prefixes end with ``/``; the bare directory itself (without
    the trailing slash) also matches. Matching is on whole
    segments, never substrings (``src/`` never matches
    ``src-evil/``).
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


def _normalize_claims(claims: Any) -> Dict[str, Any]:
    """Fill total defaults so partial input never crashes."""
    claims = claims if isinstance(claims, dict) else {}
    writes = claims.get("production_writes")
    protected = claims.get("protected_paths")
    run = claims.get("controls_run")
    expected = claims.get("controls_expected")
    pairs = claims.get("hash_pairs")
    return {
        "production_writes": [str(v) for v in writes
                              if isinstance(v, (str, int, float))]
        if isinstance(writes, list) else [],
        "protected_paths": [str(v) for v in protected
                            if isinstance(v, (str, int, float))]
        if isinstance(protected, list) else [],
        "controls_run": [str(v) for v in run
                         if isinstance(v, (str, int, float))]
        if isinstance(run, list) else [],
        "controls_expected": [str(v) for v in expected
                              if isinstance(v, (str, int, float))]
        if isinstance(expected, list) else [],
        "hash_pairs": [entry for entry in pairs
                       if isinstance(entry, dict)]
        if isinstance(pairs, list) else [],
    }


def check_meta(claims: Any) -> List[str]:
    """Return repair strings for one session's process evidence.

    Empty means the process is clean: zero production writes,
    zero protected-path touches, every expected control ran,
    and every hash matches.
    """
    session = _normalize_claims(claims)
    repairs: List[str] = []
    for path in session["production_writes"]:
        if _under_any(path, PRODUCTION_PREFIXES):
            repairs.append(
                "production write %r: Arc A authorizes no "
                "production writes (forbidden prefixes: %s)"
                % (path, ", ".join(PRODUCTION_PREFIXES)))
    for path in session["production_writes"]:
        if _under_any(path, tuple(session["protected_paths"])) \
                or path in session["protected_paths"]:
            repairs.append(
                "protected path %r: this write must never appear; "
                "remove it from the session" % path)
    ran = set(session["controls_run"])
    for control in session["controls_expected"]:
        if control not in ran:
            repairs.append(
                "missing control %r: the expected control canary "
                "did not run; execute it and record it" % control)
    for pair in session["hash_pairs"]:
        expected = str(pair.get("expected", ""))
        actual = str(pair.get("actual", ""))
        path = str(pair.get("path", ""))
        if expected != actual:
            repairs.append(
                "hash mismatch for %r: expected %r != actual %r; "
                "the artifact changed after recording"
                % (path or "(unnamed path)",
                   expected[:32], actual[:32]))
    return repairs


def validate_meta_corpus(corpus: Any) -> List[str]:
    """Validate the frozen meta-test oracle (repairs-or-clean).

    Every entry must carry a stable ``mold-qual.<class>.<nn>``
    id, a one-line note, a ``claims`` mapping, and
    ``expected_repairs`` equal to ``check_meta(claims)``.
    Returns repair strings; empty means the oracle is frozen.
    """
    import re
    id_re = re.compile(r"^mold-qual\.[a-z-]+\.\d{2}$")
    if isinstance(corpus, dict):
        if corpus.get("_frozen") is not True:
            return ["meta corpus is not frozen: set "
                    "\"_frozen\": true"]
        provenance = str(corpus.get("_provenance", ""))
        if "Stage 31 #122" not in provenance:
            return ["meta corpus provenance must name "
                    "\"Stage 31 #122\""]
        entries = corpus.get("entries")
    else:
        entries = corpus
    if not isinstance(entries, list):
        return ["meta corpus must be a JSON object with an "
                "'entries' array (or a bare array)"]
    findings: List[str] = []
    seen: Dict[str, int] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            findings.append("entries[%d] is not a mapping" % index)
            continue
        cid = str(entry.get("id", ""))
        if not id_re.match(cid):
            findings.append("entry %r: id is not "
                            "mold-qual.<class>.<nn>" % cid)
        if cid in seen:
            findings.append("duplicate meta id %s (entries %d and "
                            "%d)" % (cid, seen[cid], index))
        else:
            seen[cid] = index
        if not str(entry.get("note", "")).strip():
            findings.append("entry %s: a one-line adjudication note "
                            "is required" % cid)
        if not isinstance(entry.get("claims"), dict):
            findings.append("entry %s: claims must be a mapping"
                            % cid)
            continue
        expected = entry.get("expected_repairs")
        if not isinstance(expected, list):
            findings.append("entry %s: expected_repairs must be a "
                            "list" % cid)
            continue
        computed = check_meta(entry["claims"])
        if sorted(str(r) for r in expected) != \
                sorted(str(r) for r in computed):
            findings.append("entry %s: expected_repairs %r != "
                            "check_meta %r"
                            % (cid,
                               sorted(str(r) for r in expected),
                               sorted(str(r) for r in computed)))
    if len(entries) < 4:
        findings.append("meta corpus holds %d entries, want at "
                        "least 4" % len(entries))
    return findings
