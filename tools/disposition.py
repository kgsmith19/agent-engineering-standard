"""Exact-head disposition: observation before implementation.

Four outcomes: IMPLEMENT, NO_CHANGE, INSUFFICIENT_EVIDENCE, OWNER_DECISION.
An observation binds environment, command, exact head, expected/current
result, and evidence. NO_CHANGE succeeds only when current behavior
already satisfies the ask or code is not the remedy. INSUFFICIENT_EVIDENCE
names the exact missing observation. OWNER_DECISION requires a concrete
owner-dependent ambiguity (never a work avoidance). Any disposition change
invalidates readiness/Molds/capsules (consumers must re-derive).
"""

from typing import Any, Dict, List, Optional

DISPOSITIONS = (
    "IMPLEMENT",
    "NO_CHANGE",
    "INSUFFICIENT_EVIDENCE",
    "OWNER_DECISION",
)

OBSERVATION_FIELDS = (
    "environment",
    "command",
    "head",
    "expected",
    "observed",
    "evidence",
)


def validate_observation(obs: Dict[str, Any]) -> List[str]:
    """Return a list of missing/empty observation field names."""
    missing = []
    for field in OBSERVATION_FIELDS:
        if not str(obs.get(field, "") or "").strip():
            missing.append(field)
    return missing


def decide(outcome: str,
           observation: Optional[Dict[str, Any]] = None,
           satisfied: bool = False,
           code_is_remedy: bool = True,
           missing: str = "",
           ambiguity: str = "") -> Dict[str, Any]:
    """Decide one disposition. Raises ValueError on contract violation:
    unknown outcome; NO_CHANGE without satisfied-or-not-remedy proof;
    INSUFFICIENT_EVIDENCE without the exact missing observation;
    OWNER_DECISION without a concrete ambiguity."""
    if outcome not in DISPOSITIONS:
        raise ValueError(
            "unknown disposition %r (want one of %s)"
            % (outcome, ", ".join(DISPOSITIONS)))
    obs = dict(observation or {})
    gaps = validate_observation(obs)
    if outcome == "IMPLEMENT":
        if gaps:
            raise ValueError(
                "IMPLEMENT requires a complete observation; missing: %s"
                % ", ".join(gaps))
        return {"disposition": outcome, "observation": obs,
                "invalidates": ["readiness", "molds", "capsules"]}
    if outcome == "NO_CHANGE":
        if gaps:
            raise ValueError(
                "NO_CHANGE requires a complete observation; missing: %s"
                % ", ".join(gaps))
        if not (satisfied or not code_is_remedy):
            raise ValueError(
                "NO_CHANGE requires proof: behavior already satisfies the "
                "ask (satisfied) or code is not the remedy")
        return {"disposition": outcome, "observation": obs,
                "reason": "satisfied" if satisfied else "not-code-remedy",
                "invalidates": ["readiness", "molds", "capsules"]}
    if outcome == "INSUFFICIENT_EVIDENCE":
        if not missing.strip():
            raise ValueError(
                "INSUFFICIENT_EVIDENCE must name the exact missing "
                "observation")
        return {"disposition": outcome, "observation": obs,
                "missing": missing.strip(),
                "invalidates": ["readiness", "molds", "capsules"]}
    if not ambiguity.strip():
        raise ValueError(
            "OWNER_DECISION requires a concrete owner-dependent ambiguity; "
            "it may not be chosen to avoid work")
    return {"disposition": outcome, "observation": obs,
            "ambiguity": ambiguity.strip(),
            "invalidates": ["readiness", "molds", "capsules"]}
