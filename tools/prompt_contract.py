"""One-outcome prompt contract: short phase-pure prompts generated from
canonical artifacts, never copied methodology.

A prompt carries: primary outcome; repository/Issue/Slice IDs; content
hashes; phase/role; risk; current disposition; allowed/forbidden
mutations; write/protected paths; selected extensions; required evidence;
stop conditions; first safe action. The common bootstrap carries
cross-stage invariants only.

Rejects: transcript dumps; whole-repo preload; multiple shippable
outcomes; stale hashes; phase-unsupported authority; multiple write
phases. No provider-specific forks of canonical semantics: one renderer,
adapter-supplied tokens only.
"""

from typing import Any, Dict, List, Optional

REQUIRED_FIELDS = (
    "primary_outcome",
    "repository",
    "issue",
    "phase",
    "role",
    "risk",
    "disposition",
    "allowed_mutations",
    "forbidden_mutations",
    "write_paths",
    "protected_paths",
    "evidence",
    "stop_conditions",
    "first_action",
)

WRITE_PHASES = ("implement", "migrate", "release", "fix")


def validate(contract: Dict[str, Any],
             known_heads: Optional[Dict[str, str]] = None) -> List[str]:
    """Return repair strings; empty means the contract is phase-pure.
    known_heads maps artifact path -> current sha; a mismatch is stale."""
    repairs = []
    for field in REQUIRED_FIELDS:
        if not str(contract.get(field, "") or "").strip():
            repairs.append(
                "prompt missing %r: fill it from canonical artifacts"
                % field)
    outcomes = contract.get("outcomes", ["one"])
    if len(outcomes) != 1:
        repairs.append(
            "prompt authorizes %d shippable outcomes, want exactly one"
            % len(outcomes))
    phases = [p.strip() for p in str(
        contract.get("phases", "") or "").split(",") if p.strip()]
    writes = [p for p in phases if p.strip() in WRITE_PHASES]
    if len(phases) > 1:
        repairs.append(
            "prompt spans phases %s: one phase per prompt" % phases)
    if contract.get("transcript_dump"):
        repairs.append("prompt carries a transcript dump: cite hashes, "
                       "never paste history")
    if contract.get("whole_repo_preload"):
        repairs.append("prompt preloads the whole repo: name direct files "
                       "plus the route map instead")
    for path, want in (known_heads or {}).items():
        got = (contract.get("hashes", {}) or {}).get(path, "")
        if got != want:
            repairs.append(
                "stale hash for %s: regenerate from canonical artifacts"
                % path)
    authority = str(contract.get("authority", "") or "")
    phase = str(contract.get("phase", "") or "")
    if authority and authority not in phase and phase not in authority:
        repairs.append(
            "authority %r not supported by phase %r" % (authority, phase))
    return repairs


def render(contract: Dict[str, Any]) -> str:
    """Render the short phase-pure prompt text (adapter tokens only)."""
    lines = [
        "# Task: %s" % contract.get("primary_outcome", ""),
        "",
        "Phase: %s | Role: %s | Risk: %s | Disposition: %s" % (
            contract.get("phase", ""), contract.get("role", ""),
            contract.get("risk", ""), contract.get("disposition", "")),
        "Scope: %s (issue %s)" % (contract.get("repository", ""),
                                   contract.get("issue", "")),
        "Allowed: %s" % contract.get("allowed_mutations", ""),
        "Forbidden: %s" % contract.get("forbidden_mutations", ""),
        "Write: %s | Protected: %s" % (contract.get("write_paths", ""),
                                        contract.get("protected_paths", "")),
        "Extensions: %s" % contract.get("extensions", "none"),
        "Evidence: %s" % contract.get("evidence", ""),
        "Stop when: %s" % contract.get("stop_conditions", ""),
        "First safe action: %s" % contract.get("first_action", ""),
    ]
    return "\n".join(lines) + "\n"
