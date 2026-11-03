"""Independent LLM review contract (AES #324).

The contract lives in ``Canonical/review-contract.json``. It defines what
the reviewer judges, which mechanical categories it leaves to
deterministic CI, the shape of one finding, and how a review result maps
to an outcome. This module holds pure functions only: no I/O except
``load_contract``, no subprocess, no network.

- ``render_instructions`` turns the contract into the reviewer prompt.
- ``validate_finding`` returns repair strings; an empty list means valid.
- ``classify`` maps one review result to ``clean``, ``findings`` or
  ``infrastructure_failure``. Invalid findings are dropped, never counted,
  so a confused model cannot block work. Only a provider, transport or
  contract failure fails the job.
"""

from typing import Any, Dict, List, NamedTuple, Optional

import json
from pathlib import Path

CONTRACT_PATH = (
    Path(__file__).resolve().parent.parent / "Canonical" / "review-contract.json")

OUTCOMES = ("clean", "findings", "infrastructure_failure")

_CONTRACT_KEYS = (
    "contract_version", "focus", "excluded_mechanical", "finding", "outcomes")


class Outcome(NamedTuple):
    outcome: str
    exit_code: int
    finding_count: int
    findings: List[Dict[str, Any]]
    rejected: List[Dict[str, Any]]
    reason: str


def load_contract(path: Optional[str] = None) -> Dict[str, Any]:
    data = json.loads(
        Path(path or CONTRACT_PATH).read_text(encoding="utf-8"))
    errors = validate_contract(data)
    if errors:
        raise ValueError("review contract invalid: " + "; ".join(errors))
    return data


def validate_contract(contract: Any) -> List[str]:
    if not isinstance(contract, dict):
        return ["contract must be a JSON object"]
    errors = ["missing key: %s" % k for k in _CONTRACT_KEYS
              if k not in contract]
    if errors:
        return errors
    outcomes = contract["outcomes"]
    if sorted(outcomes) != sorted(OUTCOMES):
        errors.append("outcomes must be exactly %s" % ", ".join(OUTCOMES))
    elif outcomes["infrastructure_failure"].get("exit_code") == 0:
        errors.append("infrastructure_failure must exit non-zero")
    elif any(outcomes[k].get("exit_code") != 0
             for k in ("clean", "findings")):
        errors.append("clean and findings must exit 0")
    focus_ids = {f.get("id") for f in contract["focus"]}
    excluded_ids = {e.get("id") for e in contract["excluded_mechanical"]}
    if focus_ids & excluded_ids:
        errors.append("a category cannot be both focus and excluded")
    if not contract["finding"].get("required"):
        errors.append("finding.required must list fields")
    return errors


def render_instructions(contract: Dict[str, Any]) -> str:
    finding = contract["finding"]
    lines = [
        "# Independent review instructions (contract %s)"
        % contract["contract_version"],
        "",
        contract.get("purpose", ""),
        "",
        "## Trust boundary",
        contract.get("untrusted_content", ""),
        "",
        "## Judge these areas",
    ]
    lines += ["- %s: %s" % (f["id"], f["ask"]) for f in contract["focus"]]
    lines += ["", "## Do not review these (deterministic CI owns them)"]
    lines += ["- %s (owner: %s)" % (e["id"], e.get("owner", "CI"))
              for e in contract["excluded_mechanical"]]
    lines += [
        contract.get("excluded_exception", ""),
        "",
        "## Each finding",
        "Required fields: %s." % ", ".join(finding["required"]),
        "Optional fields: %s." % ", ".join(finding.get("optional", [])),
        "Severity is one of: %s." % ", ".join(finding["severities"]),
        "category is one focus id above, or an excluded id with risk set.",
        finding.get("rationale_rule", ""),
        finding.get("smallest_fix_rule", ""),
        "",
        "Report no finding rather than a speculative one. Never approve,",
        "merge or modify the pull request.",
    ]
    return "\n".join(lines).rstrip() + "\n"


def validate_finding(finding: Any, contract: Dict[str, Any]) -> List[str]:
    if not isinstance(finding, dict):
        return ["finding must be an object"]
    spec = contract["finding"]
    repairs = []
    for key in spec["required"]:
        value = finding.get(key)
        if not isinstance(value, str) or not value.strip():
            repairs.append("missing required field: %s" % key)
    severity = finding.get("severity")
    if isinstance(severity, str) and severity not in spec["severities"]:
        repairs.append("unknown severity: %s" % severity)
    line = finding.get("line")
    if line is not None and (not isinstance(line, int) or line < 1):
        repairs.append("line must be a positive integer")
    category = finding.get("category")
    focus_ids = {f["id"] for f in contract["focus"]}
    excluded_ids = {e["id"] for e in contract["excluded_mechanical"]}
    if isinstance(category, str) and category:
        if category in excluded_ids:
            if finding.get("risk") not in spec.get("risks", []):
                repairs.append(
                    "excluded mechanical category %s needs risk set to "
                    "one of %s" % (category, ", ".join(spec["risks"])))
        elif category not in focus_ids:
            repairs.append("unknown category: %s" % category)
    return repairs


def classify(result: Any, contract: Dict[str, Any]) -> Outcome:
    """Map one review result to an outcome.

    A result is ``{"status": "completed", "findings": [...]}`` or
    ``{"status": "error", "error": "..."}``. Anything other than a
    completed result with a findings list is an infrastructure failure.
    """
    infra = contract["outcomes"]["infrastructure_failure"]["exit_code"]
    if not isinstance(result, dict):
        return Outcome("infrastructure_failure", infra, 0, [], [],
                       "result is not an object")
    if result.get("status") != "completed":
        return Outcome("infrastructure_failure", infra, 0, [], [],
                       str(result.get("error") or "review did not complete"))
    raw = result.get("findings")
    if not isinstance(raw, list):
        return Outcome("infrastructure_failure", infra, 0, [], [],
                       "completed result has no findings list")
    valid, rejected = [], []
    for item in raw:
        repairs = validate_finding(item, contract)
        if repairs:
            rejected.append({"finding": item, "repairs": repairs})
        else:
            valid.append(item)
    name = "findings" if valid else "clean"
    return Outcome(name, contract["outcomes"][name]["exit_code"], len(valid),
                   valid, rejected,
                   "%d valid, %d rejected" % (len(valid), len(rejected)))
