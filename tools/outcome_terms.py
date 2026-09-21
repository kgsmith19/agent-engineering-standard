"""Outcome-first titles and fixed defined terms (T11, #207).

One observable-outcome rule for amendment-scope issue titles plus the
six fixed term definitions (lease, fencing generation, idempotent,
Mold, capability sense, MERGED vs CLEANED). Pure stdlib-only contract:
no I/O, no network. consumed by the `outcome-terms` verify check and by
unit fixtures (ambiguous/empty outcome, contradictory term use,
dropped template field, inline stage ID).

Template fields are never renamed here: REQUIRED_TEMPLATE_FIELDS
mirrors the `TEMPLATES/ISSUE.md` section list verbatim, and the check
fails a body that drops any of them.
"""

from typing import Dict, List, Tuple
import re

DEFINED_TERMS: Dict[str, str] = {
    "lease": "temporary exclusive write authority",
    "fencing generation": "increasing identifier rejecting stale writers",
    "idempotent": "retries do not repeat effect",
    "Mold": "frozen verification contract",
    "capability": "named behavior OR granted permission (state which)",
    "MERGED vs CLEANED": "completion states: merge may precede cleanup; "
    "MERGED is not CLEANED",
}

REQUIRED_TEMPLATE_FIELDS: Tuple[str, ...] = (
    "Outcome",
    "Release",
    "Context",
    "Behavior claims",
    "Must remain true",
    "Must never happen",
    "Examples and boundaries",
    "Risk",
    "Test strategy",
    "Artifact requirements",
    "Lean design",
    "Dependencies",
    "Security and recovery",
    "Scope",
    "Owner overrides",
    "Handoff",
)

AMBIGUOUS_OUTCOME_PATTERNS = (
    "improve things",
    "improve the workflow",
    "make things better",
    "misc updates",
    "various fixes",
    "general improvements",
)

_STAGE_SUFFIX_RE = re.compile(r"\[T\d+\]\s*$|Stage \d+[a-z]?\s*\]\s*$")
_STAGE_INLINE_RE = re.compile(r"^Stage \d+", re.IGNORECASE)
_FIELD_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def check_outcome_title(title: str) -> List[str]:
    """Return violation strings for an issue title; empty means pass.

    Rejects empty outcomes and ambiguous outcomes with no observable
    behavior. Accepts outcome-first titles and `Stage X` suffix/
    metadata mappings.
    """
    text = (title or "").strip()
    if not text:
        return ["empty outcome: title states no observable result"]
    lowered = text.lower()
    for pattern in AMBIGUOUS_OUTCOME_PATTERNS:
        if pattern in lowered:
            return [
                "ambiguous outcome %r: title states no verb + "
                "observable behavior + scope" % pattern
            ]
    return []


def check_term_use(body: str) -> List[str]:
    """Return violation strings for contradictory defined-term use."""
    text = body or ""
    violations = []
    if re.search(r"MERGED\s*=\s*CLEANED|MERGED\s+is\s+CLEANED",
                 text, re.IGNORECASE):
        violations.append(
            "contradictory term use: MERGED treated as CLEANED "
            "(merge may precede cleanup; MERGED is not CLEANED)")
    if re.search(r"lease.{0,40}permanent", text, re.IGNORECASE):
        violations.append(
            "contradictory term use: lease treated as permanent "
            "authority (a lease is temporary exclusive write "
            "authority)")
    return violations


def check_template_fields(body: str) -> List[str]:
    """Return a violation per required template field absent from body."""
    present = set(_FIELD_HEADING_RE.findall(body or ""))
    return [
        "template field dropped: ## %s is missing" % field
        for field in REQUIRED_TEMPLATE_FIELDS
        if field not in present
    ]


def check_stage_id_placement(title: str) -> List[str]:
    """Stage IDs map to metadata: allowed only as a title suffix."""
    text = (title or "").strip()
    if _STAGE_INLINE_RE.match(text) and not _STAGE_SUFFIX_RE.search(text):
        return [
            "stage ID placement: stage IDs appear only as a `Stage X` "
            "title suffix/metadata mapping, never as the outcome itself"
        ]
    return []


def validate_issue(title: str, body: str) -> List[str]:
    """Validate one issue title + body against the T11 convention."""
    return (check_outcome_title(title) + check_term_use(body)
            + check_template_fields(body)
            + check_stage_id_placement(title))
