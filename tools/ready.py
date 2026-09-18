"""Machine-gated Definition of Ready: Arc A starts only with validated
intent, bounded scope, right-sized task, and named proof.

A receipt validates: one outcome; claims/invariants/forbidden outcomes;
non-goals; risk + Autonomy Envelope; Focus Envelope; allowed/protected
paths; dependencies; thinness class below large (score 9-12 refuses);
disposition IMPLEMENT (observation complete); recovery path; owner
decisions recorded; independent evidence strategy; context budget and
extension profile within pilot ranges. R0/R1 uses the compact form
(outcome + scope + proof only). Any semantic Issue/Spec/Product Truth
change invalidates the receipt (caller re-derives).
"""

from typing import Any, Dict, List, Optional

FULL_FIELDS = (
    "outcome",
    "claims",
    "forbidden_outcomes",
    "non_goals",
    "risk",
    "autonomy_envelope",
    "focus_envelope",
    "allowed_paths",
    "protected_paths",
    "dependencies",
    "thinness_total",
    "disposition",
    "recovery",
    "owner_decisions",
    "evidence_strategy",
    "context_budget_ok",
    "extension_profile_ok",
)

COMPACT_FIELDS = ("outcome", "scope", "proof")


def check_receipt(receipt: Dict[str, Any],
                  compact: bool = False) -> List[str]:
    """Return repair guidance strings; empty means READY. Compact form
    (R0/R1) requires outcome+scope+proof only. Full form requires every
    FULL_FIELDS entry plus: thinness_total below 9, disposition exactly
    IMPLEMENT, context/extension flags true."""
    repairs = []
    if compact:
        for field in COMPACT_FIELDS:
            if not str(receipt.get(field, "") or "").strip():
                repairs.append(
                    "compact DoR missing %r: state it in one line" % field)
        return repairs
    for field in FULL_FIELDS:
        value = receipt.get(field, "")
        if isinstance(value, bool):
            if not value and field in ("context_budget_ok",
                                       "extension_profile_ok"):
                repairs.append(
                    "%s is false: shrink scope or record an approved "
                    "exception" % field)
            continue
        if not str(value or "").strip():
            repairs.append(
                "DoR missing %r: fill it before Arc A starts" % field)
    if "DoR missing 'forbidden_outcomes'" in " ".join(repairs):
        repairs.append(
            "hint: forbidden outcomes name what must NOT happen")
    total = receipt.get("thinness_total", None)
    if isinstance(total, int) and total >= 9:
        repairs.append(
            "thinness %d is large (9-12): split or finish Arc A first; "
            "score 9-12 cannot authorize one Builder" % total)
    if (receipt.get("disposition", "") and
            receipt.get("disposition") != "IMPLEMENT"):
        repairs.append(
            "disposition is %s, want IMPLEMENT with a complete "
            "observation; stale dispositions fail" % receipt["disposition"])
    return repairs


def ready_blocked(reason: str) -> Dict[str, Any]:
    return {"ready": False, "reason": reason,
            "invalidated_by": ["issue", "spec", "product-truth change"]}
