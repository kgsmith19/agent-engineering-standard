"""Quantified semantic thinness: six-axis Thinness Signal plus hard
semantic conditions and pilot warning bands.

Pure stdlib scoring used by `standardctl thinness` (advisory only; never
gates verify). Doctrine source: cookbook sections 5.2 (ten hard
conditions), 5.3 (six 0-2 axes, classes 0-3/4-6/7-8/9-12), 5.4 (pilot
ranges per artifact). Semantic gates always outrank counts.
"""

from typing import Any, Dict, List, Optional

AXES = (
    "independent_behaviors",
    "unknowns",
    "state_irreversibility",
    "external_boundary",
    "verification_burden",
    "write_overlap",
)

HARD_CONDITIONS = (
    "one_sentence_outcome",
    "one_observable_boundary",
    "independent_merge_or_recovery",
    "one_writer",
    "one_reviewer_understands",
    "one_evidence_strategy",
    "one_to_five_claims",
    "non_goals_explicit",
    "no_write_overlap",
    "capsule_sufficient",
)


def classify(total: int) -> str:
    if total <= 3:
        return "micro"
    if total <= 6:
        return "preferred"
    if total <= 8:
        return "medium"
    return "large"


def default_action(classification: str) -> str:
    return {
        "micro": "excellent tiny slice; avoid extra ceremony",
        "preferred": "normal autonomous Builder assignment",
        "medium": "split, investigate, or finish Arc A before Builder",
        "large": "never assign to one Builder prompt; create more work items",
    }[classification]


def score(axes: Dict[str, int],
          failed_conditions: Optional[List[str]] = None,
          warning_band_hit: bool = False,
          kind: str = "issue") -> Dict[str, Any]:
    """Score one work item. axes maps each of the six AXES to 0-2.
    failed_conditions lists failed HARD_CONDITIONS (empty means all pass).
    warning_band_hit flags a pilot-range breach (counts only, advisory).
    Raises ValueError on unknown axes or out-of-range values."""
    unknown = sorted(set(axes) - set(AXES))
    if unknown:
        raise ValueError("unknown thinness axes: %s" % ", ".join(unknown))
    missing = sorted(set(AXES) - set(axes))
    if missing:
        raise ValueError("missing thinness axes: %s" % ", ".join(missing))
    for axis, value in axes.items():
        if value not in (0, 1, 2):
            raise ValueError(
                "axis %r must be 0-2, got %r" % (axis, value))
    failed = list(failed_conditions or [])
    unknown_conditions = sorted(set(failed) - set(HARD_CONDITIONS))
    if unknown_conditions:
        raise ValueError(
            "unknown hard conditions: %s" % ", ".join(unknown_conditions))
    total = sum(axes[axis] for axis in AXES)
    classification = classify(total)
    semantic_veto = bool(failed)
    # Semantic gates outrank counts: any failed hard condition escalates
    # at least one class (micro->preferred->medium->large).
    if semantic_veto and classification != "large":
        order = ("micro", "preferred", "medium", "large")
        classification = order[order.index(classification) + 1]
    explanations = [
        "%s=%d" % (axis, axes[axis]) for axis in AXES
    ]
    if failed:
        explanations.append(
            "failed hard conditions: %s" % ", ".join(sorted(failed)))
    if warning_band_hit:
        explanations.append(
            "pilot warning band breached (advisory; semantic gates govern)")
    split = (
        classification in ("medium", "large")
        or bool(failed)
        or (classification == "preferred" and warning_band_hit
            and kind in ("pr", "issue")))
    return {
        "total": total,
        "classification": classification,
        "action": default_action(classification),
        "axes": dict(axes),
        "failed_conditions": sorted(failed),
        "warning_band_hit": warning_band_hit,
        "semantic_veto": semantic_veto,
        "split_recommended": split,
        "explanations": explanations,
    }
