"""Stage 21b Standard half: MCP/connector profile schema fields and the
activation contract the Stage 21a sibling mechanism enforces.

The Standard governs the schema: zero standing servers is the default
posture, servers activate only as bounded task-specific entries, and the
profile carries active/candidate counts, permissions, egress, secrets,
and expiry. Enforcement (server startup, transport handling, live
fail-closed gating) is the disjoint Stage 21a half in
``agent_extensions.sync.mcp_governance`` — referenced read-only, never
imported here.

Contract (plain data, additive-only per the sibling contract v1.0.0):

- A server declaration carries exactly ``SERVER_FIELDS``, matching the
  Stage 21a ``McpServer`` model field-for-field.
- Hard failures (findings, never advisory): secret exposure, egress
  outside the pinned allowlist, write connectors during the research
  phase, non-idempotent writes, stale/expired sessions, duplicate
  capabilities where a native tool exists (native wins over MCP), and
  http servers targeting a provider with no declared transport key.
- Numeric footprint limits (active/candidate counts, pilot cap, giant
  schemas, unused capabilities) are advisory warnings only during the
  pilot — callers log them, never enforce them.
- ``apply_activation`` stamps the server and feeds the Task Capsule
  active list and Context Budget count that Stage 21a consumes live.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

SIBLING_CONTRACT_VERSION = "1.0.0"

SERVER_FIELDS = (
    "name",
    "transport",
    "endpoint",
    "capabilities",
    "kind",
    "schema_bytes",
    "idempotent",
    "activated_at",
    "ttl_seconds",
)

TRANSPORTS = ("stdio", "http")
KINDS = ("read", "write")
PHASES = ("research", "task")
RESEARCH_PHASE = "research"

# Pinned from Stage 21a agent_extensions.sync.adapters.MCP_TRANSPORT_KEY:
# the config key under which an http MCP server endpoint is declared.
TRANSPORT_KEYS = {
    "claude": "url",
    "codex": "serverUrl",
    "antigravity": "serverUrl",
    "local": "url",
}

# Pinned egress allowlist (Stage 21a contract): fail closed for anything
# else on http endpoints.
EGRESS_ALLOWLIST = ("localhost", "127.0.0.1", "github.com",
                    "api.anthropic.com")

# Pinned secret shapes (Stage 21a contract); truncated matches in
# findings, never the full value.
SECRET_MARKERS = (
    ("sk-ant-", "anthropic"),
    ("sk-", "api key"),
    ("xoxb-", "slack token"),
    ("xoxp-", "slack token"),
    ("ghp_", "github token"),
    ("AKIA", "aws access key"),
    ("AIza", "google api key"),
)

# Advisory pilot limits — documented, logged, never enforced here.
ADVISORY_LIMITS = {
    "active_max": 2,
    "candidate_max": 5,
    "pilot_cap": 12,
    "schema_bytes_max": 64 * 1024,
}


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_server(server: Dict[str, Any]) -> List[str]:
    """Return repairs; empty means the declaration matches the Stage 21a
    McpServer schema."""
    repairs: List[str] = []
    for field in SERVER_FIELDS:
        if field not in server:
            repairs.append(
                "server %r missing required field %r" % (
                    server.get("name", "<unnamed>"), field))
    transport = server.get("transport")
    if transport is not None and transport not in TRANSPORTS:
        repairs.append(
            "server %r: transport must be one of %s, got %r" % (
                server.get("name", "<unnamed>"), list(TRANSPORTS),
                transport))
    kind = server.get("kind")
    if kind is not None and kind not in KINDS:
        repairs.append(
            "server %r: kind must be one of %s, got %r" % (
                server.get("name", "<unnamed>"), list(KINDS), kind))
    if "schema_bytes" in server and not _is_int(server.get("schema_bytes")):
        repairs.append(
            "server %r: schema_bytes must be a non-negative int" %
            server.get("name", "<unnamed>"))
    return repairs


def _scan_secrets(text: str) -> List[str]:
    """Secret-shaped substrings (truncated); empty means clean."""
    hits: List[str] = []
    for marker, label in SECRET_MARKERS:
        index = text.find(marker)
        if index >= 0:
            hits.append("%s%s…" % (marker, " " + label))
            break
    return hits


def check_egress(endpoint: str) -> str:
    """Return "" when allowed, else the egress-violation finding text."""
    if not endpoint or endpoint.startswith(("stdio:", "cmd:")):
        return ""
    host = str(endpoint).replace("https://", "").replace("http://", "")
    host = host.split("/")[0].split(":")[0]
    if host in EGRESS_ALLOWLIST:
        return ""
    return "egress violation: %r not in allowlist %s" % (
        host, list(EGRESS_ALLOWLIST))


def _stale_session_finding(server: Dict[str, Any]) -> str:
    activated_at = server.get("activated_at")
    ttl_seconds = server.get("ttl_seconds")
    if not activated_at or not ttl_seconds:
        return ""
    try:
        activated = datetime.fromisoformat(
            str(activated_at).replace("Z", "+00:00"))
        if activated.tzinfo is None:
            activated = activated.replace(tzinfo=timezone.utc)
    except ValueError:
        return "server %r: unparseable activated_at" % server.get("name")
    expires = activated.timestamp() + int(ttl_seconds)
    if expires <= datetime.now(timezone.utc).timestamp():
        return "stale session: server %r activation expired" % (
            server.get("name"),)
    return ""


def validate_activation(server: Dict[str, Any],
                        profile: Dict[str, Any]) -> Dict[str, List[str]]:
    """Fail-closed gate over one server declaration.

    Returns {"findings": [...], "warnings": [...]}: findings refuse
    activation (fail closed); warnings are advisory pilot guidance only.
    """
    findings: List[str] = []
    warnings: List[str] = []
    name = str(server.get("name", "<unnamed>"))

    for repair in validate_server(server):
        findings.append(repair)

    scanned = str(server.get("endpoint", "")) + " " + " ".join(
        str(c) for c in server.get("capabilities", []) or [])
    for hit in _scan_secrets(scanned):
        findings.append("secret exposure in %s: %s" % (name, hit))

    egress = check_egress(str(server.get("endpoint", "")))
    if egress:
        findings.append("%s: %s" % (name, egress))

    phase = str(profile.get("phase", "task"))
    if phase == RESEARCH_PHASE and server.get("kind") == "write":
        findings.append(
            "write connector %s activated during research phase" % name)
    if server.get("kind") == "write" and not server.get("idempotent"):
        findings.append(
            "write connector %s must declare idempotency" % name)

    stale = _stale_session_finding(server)
    if stale:
        findings.append(stale)

    native = profile.get("native_capabilities") or []
    for cap in server.get("capabilities", []) or []:
        if cap in native:
            findings.append(
                "duplicate capability %s: native tool wins over MCP %s" % (
                    cap, name))

    provider = str(profile.get("provider", "local"))
    if server.get("transport") == "http" and provider not in TRANSPORT_KEYS:
        findings.append(
            "server %s: no MCP transport key for provider %r" % (
                name, provider))

    warnings.extend(
        advisory_warnings(
            list(profile.get("active_servers", []) or []),
            list(profile.get("candidate_servers", []) or [])))
    return {"findings": findings, "warnings": warnings}


def advisory_warnings(active: List[Dict[str, Any]],
                      candidates: List[Dict[str, Any]]) -> List[str]:
    """Advisory pilot guidance only — callers log these, never enforce."""
    warnings: List[str] = []
    if len(active) > ADVISORY_LIMITS["active_max"]:
        warnings.append(
            "advisory: %d active servers over pilot suggestion %d" % (
                len(active), ADVISORY_LIMITS["active_max"]))
    if len(candidates) > ADVISORY_LIMITS["candidate_max"]:
        warnings.append(
            "advisory: %d candidate servers over pilot suggestion %d" % (
                len(candidates), ADVISORY_LIMITS["candidate_max"]))
    if len(active) + len(candidates) > ADVISORY_LIMITS["pilot_cap"]:
        warnings.append("advisory: pilot cap exceeded (informational only)")
    for server in active + candidates:
        if int(server.get("schema_bytes", 0)) > \
                ADVISORY_LIMITS["schema_bytes_max"]:
            warnings.append(
                "advisory: server %r has a giant schema; consider pruning" %
                server.get("name"))
    unused = [str(s.get("name")) for s in candidates
              if not s.get("capabilities")]
    if unused:
        warnings.append("advisory: unused capabilities: %s" % unused)
    return warnings


def validate_profile(profile: Dict[str, Any]) -> Dict[str, List[str]]:
    """Profile-level validation: zero standing servers is binding, every
    declared server must be well-formed, and all numeric footprint signals
    stay advisory."""
    findings: List[str] = []
    warnings: List[str] = []

    standing = list(profile.get("standing_servers", []) or [])
    if standing:
        findings.append(
            "standing_servers must be empty: zero standing MCPs is the "
            "default posture (%d declared)" % len(standing))

    active = list(profile.get("active_servers", []) or [])
    candidates = list(profile.get("candidate_servers", []) or [])
    for server in active + candidates:
        findings.extend(validate_server(server))
    warnings.extend(advisory_warnings(active, candidates))
    return {"findings": findings, "warnings": warnings}


def apply_activation(server: Dict[str, Any], capsule: Dict[str, Any],
                     budget: Dict[str, Any]) -> Dict[str, Any]:
    """Stamp the server and feed the live Task Capsule / Context Budget
    update path consumed by Stage 21a (mirrors sibling record_activation)."""
    stamped = dict(server)
    stamped["activated_at"] = datetime.now(timezone.utc).isoformat().replace(
        "+00:00", "Z")
    capsule.setdefault("active_servers", []).append(stamped["name"])
    budget["mcp_active"] = len(capsule["active_servers"])
    return stamped
