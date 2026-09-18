"""Bounded repository map: locate code/tests/contracts/commands without
loading the repository.

Map entries carry a reason for every path. The map never enumerates the
entire file tree and is never authoritative (source of truth stays in
the files). Planes: source / generated / artifact / cache / evidence /
protected. Direct generated edits, missing contracts, invalid commands,
cycles, oversize maps, and wrong-plane entries fail with repair guidance.
"""

from typing import Any, Dict, List, Optional

PLANES = ("source", "generated", "artifact", "cache", "evidence",
          "protected")

MAP_BUDGET_ENTRIES = 60

GENERATED_PATTERNS = ("Canonical/generated/",)
ARTIFACT_PATTERNS = ("Canonical/schemas/", "Canonical/capabilities.json",
                     "Canonical/v4.2-preservation.csv")
CACHE_PATTERNS = (".worktrees/", "__pycache__/", ".evidence/cache")
EVIDENCE_PATTERNS = (".evidence/",)
PROTECTED_PATTERNS = (".github/workflows/pr-gate.yml",
                      ".github/workflows/merge-policy.yml", "main")


def plane_for(path: str) -> str:
    for pattern in PROTECTED_PATTERNS:
        if path == pattern or path.startswith(pattern):
            return "protected"
    for pattern in EVIDENCE_PATTERNS:
        if path.startswith(pattern):
            return "evidence"
    for pattern in CACHE_PATTERNS:
        if pattern in path:
            return "cache"
    for pattern in ARTIFACT_PATTERNS:
        if path.startswith(pattern):
            return "artifact"
    for pattern in GENERATED_PATTERNS:
        if path.startswith(pattern):
            return "generated"
    return "source"


def build(entries: List[Dict[str, str]]) -> Dict[str, Any]:
    """Build a bounded map. Each entry needs path+reason. Raises
    ValueError on missing reasons, cycles (dup paths), oversize, or
    wrong-plane declarations."""
    if len(entries) > MAP_BUDGET_ENTRIES:
        raise ValueError(
            "map holds %d entries, over the %d-entry budget: narrow the "
            "focus envelope instead" % (len(entries), MAP_BUDGET_ENTRIES))
    seen = set()
    for entry in entries:
        path = entry.get("path", "")
        if not path:
            raise ValueError("map entry without a path")
        if not str(entry.get("reason", "") or "").strip():
            raise ValueError(
                "map entry %r has no reason: every path needs one" % path)
        if path in seen:
            raise ValueError(
                "cyclic map: %r listed twice" % path)
        seen.add(path)
        declared = entry.get("plane", "")
        actual = plane_for(path)
        if declared and declared != actual:
            raise ValueError(
                "wrong plane for %r: declared %r, actual %r"
                % (path, declared, actual))
        entry["plane"] = actual
    return {"version": "5.0.0",
            "entries": sorted(entries, key=lambda e: e["path"])}


def validate_edit(path: str, plane: str) -> Optional[str]:
    """Refuse direct generated edits; None means the edit may proceed."""
    if plane == "generated":
        return ("direct generated edit of %r refused: regenerate via the "
                "owning tool instead" % path)
    return None
