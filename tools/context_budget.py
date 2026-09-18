"""Zero-compaction context budget governor: planned fresh-session rotation
happens before provider auto-compaction or context pollution.

Tracks capsule/rules/files/skills/MCP/tool-output footprint, expansions,
unresolved questions, provider-safe headroom, and rotations. Emits
HEALTHY, EXPANSION_REQUIRES_REASON, ROTATE_AT_BOUNDARY, ROTATE_NOW_READ_ONLY,
or RECOVERY_REQUIRED. Target automatic compactions per Issue = 0.
Mandatory rotations at role/phase boundaries; emergency pre-compaction
tripwire fires before provider hooks do.

Thresholds are PROPOSED per-provider/repo experiments: 4-6k capsule
(16-24 KiB), 8-12k working set (32-48 KiB). No silent summary ever
replaces state: rotation carries the capsule forward, never a digest.
"""

from typing import Any, Dict, List

STATUSES = (
    "HEALTHY",
    "EXPANSION_REQUIRES_REASON",
    "ROTATE_AT_BOUNDARY",
    "ROTATE_NOW_READ_ONLY",
    "RECOVERY_REQUIRED",
)

CAPSULE_BYTES_MAX = 24 * 1024
WORKING_BYTES_WARN = 32 * 1024
WORKING_BYTES_MAX = 48 * 1024


def govern(footprint: Dict[str, int],
           expansions: int = 0,
           unresolved: int = 0,
           polluted: bool = False,
           missing_load_bearing: bool = False,
           phase_change: bool = False) -> Dict[str, Any]:
    """Evaluate one footprint snapshot. footprint maps section name to
    bytes (capsule, rules, files, skills, mcp, tool_output). Returns
    status + reasons + rotation directive."""
    total = sum(footprint.values())
    reasons = []
    if missing_load_bearing or polluted:
        return {"status": "RECOVERY_REQUIRED",
                "total_bytes": total,
                "reasons": ["missing load-bearing fact" if
                            missing_load_bearing else "polluted history: "
                            "recover from capsule, never summarize"],
                "action": "recover from last capsule; new session"}
    if total >= WORKING_BYTES_MAX:
        return {"status": "ROTATE_NOW_READ_ONLY",
                "total_bytes": total,
                "reasons": ["working set %d bytes at hard max: read-only "
                            "until rotation" % total],
                "action": "read-only; rotate with capsule now"}
    if phase_change:
        return {"status": "ROTATE_AT_BOUNDARY",
                "total_bytes": total,
                "reasons": ["mandatory rotation at role/phase boundary"],
                "action": "rotate with capsule at boundary"}
    if total >= WORKING_BYTES_WARN:
        reasons.append("working set %d bytes in warn band: expand only "
                       "for a named unresolved question" % total)
    if expansions > 0 and unresolved <= 0:
        return {"status": "EXPANSION_REQUIRES_REASON",
                "total_bytes": total,
                "reasons": ["%d expansion(s) with no unresolved question: "
                            "name one or roll back" % expansions],
                "action": "name the question or roll back the expansion"}
    if reasons or total >= WORKING_BYTES_WARN:
        return {"status": "ROTATE_AT_BOUNDARY"
                if total >= WORKING_BYTES_WARN else "HEALTHY",
                "total_bytes": total,
                "reasons": reasons or ["approaching limit: plan rotation"],
                "action": "plan rotation at next boundary"}
    return {"status": "HEALTHY", "total_bytes": total,
            "reasons": [], "action": "continue"}
