"""Provider-neutral task capsules: bounded recovery packets that cold-boot
any supported provider without transcript history.

Canonical state only: identities, exact source hashes, outcome/remaining
claims, phase/role/risk, Focus Envelope, allowed/protected paths,
branch/worktree/base/head/PR, lease, extensions, rule IDs, last
verification, blocker, next action, stop conditions, redaction note,
expiry, producer. Forbidden: vendor session IDs, local absolute paths,
hidden reasoning, fabricated defaults, secrets.

Budget: 4-6k tokens (~16-24 KiB UTF-8) pilot. Oversize fails/splits
instead of truncating load-bearing fields. Deterministic JSON: sorted
keys, LF, UTF-8.
"""

import json
import re
from typing import Any, Dict, List, Optional

VERSION = "5.0.0"
BUDGET_BYTES_MIN = 16 * 1024
BUDGET_BYTES_MAX = 24 * 1024

CAPSULE_FIELDS = (
    "schema", "version", "issue", "outcome", "remaining_claims",
    "phase", "role", "risk", "focus_envelope", "allowed_paths",
    "protected_paths", "branch", "base", "head", "pr", "lease",
    "extensions", "rule_ids", "last_verification", "blocker",
    "next_action", "stop_conditions", "source_hashes", "redacted",
    "expires", "producer",
)

_SECRET_RE = re.compile(
    r"(api[_-]?key\s*[:=]\s*\S+|secret\s*[:=]\s*\S+|password\s*[:=]\s*\S+|"
    r"private[_-]?key\s*[:=]\s*\S+|bearer\s+\S+|gh[pousr]_[A-Za-z0-9]+|"
    r"xox[bpas]-[A-Za-z0-9-]+)",
    re.IGNORECASE)
_ABSPATH_RE = re.compile(r"(?<![\w.-])([A-Za-z]:\\|/)[\w./\\-]*")
_SESSION_RE = re.compile(r"(session[_-]?id|conversation[_-]?id)",
                         re.IGNORECASE)


def scan_forbidden(capsule: Dict[str, Any]) -> List[str]:
    """Return repair strings for forbidden content; empty means clean."""
    repairs = []
    blob = json.dumps(capsule, sort_keys=True)
    if _SECRET_RE.search(blob):
        repairs.append("capsule carries secret-like material: redact it; "
                       "capsules never hold credentials")
    if _ABSPATH_RE.search(json.dumps(
            {k: capsule.get(k, "") for k in
             ("next_action", "blocker", "allowed_paths",
              "protected_paths")})):
        repairs.append("capsule carries local absolute paths: use repo-"
                       "relative paths; canonical state is portable")
    if _SESSION_RE.search(blob):
        repairs.append("capsule requires vendor session IDs: canonical "
                       "state cannot depend on them")
    for key in ("reasoning", "chain_of_thought", "hidden"):
        if key in capsule:
            repairs.append("capsule carries hidden reasoning field %r: "
                           "remove it" % key)
    return repairs


def build(fields: Dict[str, Any]) -> Dict[str, Any]:
    """Build a deterministic capsule. Raises ValueError on missing fields,
    forbidden content, or budget breach (caller splits instead)."""
    missing = [f for f in CAPSULE_FIELDS if f not in fields]
    if missing:
        raise ValueError("capsule missing fields: %s" % ", ".join(missing))
    capsule = {key: fields[key] for key in CAPSULE_FIELDS}
    repairs = scan_forbidden(capsule)
    if repairs:
        raise ValueError("; ".join(repairs))
    blob = json.dumps(capsule, indent=2, sort_keys=True,
                      ensure_ascii=False) + "\n"
    size = len(blob.encode("utf-8"))
    if size > BUDGET_BYTES_MAX:
        raise ValueError(
            "capsule is %d bytes, over the %d-byte pilot budget: split "
            "the task instead of truncating load-bearing fields"
            % (size, BUDGET_BYTES_MAX))
    capsule["_bytes"] = size
    return capsule


def render(capsule: Dict[str, Any]) -> str:
    """Deterministic JSON rendering (sorted keys, LF, UTF-8)."""
    clean = {k: v for k, v in capsule.items() if not k.startswith("_")}
    return json.dumps(clean, indent=2, sort_keys=True,
                      ensure_ascii=False) + "\n"
