"""Versioned Standard-to-agent-extensions sibling contract (Standard half).

Policy and extension supply stay separate, provider-neutral, synchronized.
The contract pins: contract version; required sibling repo + minimum
commit; schema compatibility statement; capability-ID namespace rules;
failure behavior (fail-closed skew handling); offline bootstrap support.
Stage 15b (agent-extensions half) binds to the merged contract version,
never a draft.
"""

from typing import Any, Dict, List, Optional

CONTRACT_VERSION = "1.0.0"
SIBLING_REPO = "kgsmith19/agent-extensions"
COMPATIBILITY = ("additive-only: new optional fields allowed; renaming, "
                 "removal, or type change requires a major version bump")

CONTRACT_FIELDS = (
    "contract_version",
    "sibling_repo",
    "sibling_min_commit",
    "compatibility",
    "capability_namespace",
    "failure_behavior",
    "offline_bootstrap",
)


def validate_contract(contract: Dict[str, Any]) -> List[str]:
    """Return repair strings; empty means the contract is bindable."""
    repairs = []
    for field in CONTRACT_FIELDS:
        if not str(contract.get(field, "") or "").strip():
            repairs.append(
                "contract missing %r: versioned contracts need it" % field)
    version = str(contract.get("contract_version", ""))
    parts = version.split(".")
    if version and (len(parts) != 3 or not all(p.isdigit() for p in parts)):
        repairs.append("contract_version %r is not semver" % version)
    return repairs


def check_binding(contract: Dict[str, Any],
                  catalog_ids: List[str],
                  registry_ids: List[str],
                  rendered_hash: str = "",
                  expected_hash: str = "",
                  contract_ref: str = "",
                  offline: bool = False) -> List[str]:
    """Fail-closed skew handling between the two repos."""
    repairs = []
    repairs.extend(validate_contract(contract))
    if contract_ref and contract_ref != CONTRACT_VERSION:
        repairs.append(
            "stale contract reference %r: current is %s" % (
                contract_ref, CONTRACT_VERSION))
    missing = sorted(set(registry_ids) - set(catalog_ids))
    if missing:
        repairs.append(
            "%d Standard capability ID(s) absent from the catalog "
            "(e.g. %s): catalog must cover policy" % (
                len(missing), ", ".join(missing[:3])))
    if rendered_hash and expected_hash and rendered_hash != expected_hash:
        repairs.append("rendered-profile hash mismatch: re-render from "
                       "canonical artifacts")
    if offline and not contract.get("offline_bootstrap"):
        repairs.append("offline bootstrap unsupported by this contract")
    return repairs
