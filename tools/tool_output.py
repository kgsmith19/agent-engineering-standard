"""Bounded tool output envelope: logs/search/schemas never flood context
while exact evidence survives.

Default 4-16 KiB envelope: head window + digest (sha256 of full bytes) +
truncation marker + critical summary (load-bearing lines: errors,
failures, security hits, hashes, test results) + continuation handle for
targeted range retrieval. Every expansion names an unresolved question
and selected paths. Unmarked truncation fails validation. Wrappers and
adapters share these semantics via wrap()/retrieve()/validate().
"""

import hashlib
import re
from typing import Any, Dict, List, Optional

ENVELOPE_BYTES_MIN = 4 * 1024
ENVELOPE_BYTES_MAX = 16 * 1024

_CRITICAL_RE = re.compile(
    r"(error|fail|exception|traceback|denied|vulnerab|secret|expired|"
    r"mismatch|refused|panic|fatal|\b[A-Fa-f0-9]{7,64}\b|"
    r"FAILED|PASSED|OK\b)",
    re.IGNORECASE)


def _sanitize(text: str) -> str:
    return "".join(
        ch if (ch == "\n" or ch == "\t" or 32 <= ord(ch) < 127) else "�"
        for ch in text)


def wrap(output: str,
         question: str = "",
         paths: Optional[List[str]] = None,
         budget: int = ENVELOPE_BYTES_MAX,
         handle: str = "out-0") -> Dict[str, Any]:
    """Wrap raw tool output. Raises ValueError when an expansion (output
    over half budget) names no unresolved question."""
    if not question.strip() and len(output.encode("utf-8")) > budget // 2:
        raise ValueError(
            "context expansion names no unresolved question: state what "
            "this output decides and which paths it covers")
    clean = _sanitize(output)
    raw = clean.encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    critical = [line for line in clean.splitlines()
                if _CRITICAL_RE.search(line)][:20]
    if len(raw) <= budget:
        return {"truncated": False, "digest": digest, "handle": handle,
                "head": clean, "tail": "", "critical": critical,
                "omitted_bytes": 0, "total_bytes": len(raw),
                "question": question.strip(),
                "paths": list(paths or [])}
    head_bytes = raw[:budget // 2]
    tail_bytes = raw[-(budget // 2):]
    head = head_bytes.decode("utf-8", errors="replace")
    tail = tail_bytes.decode("utf-8", errors="replace")
    return {"truncated": True, "digest": digest, "handle": handle,
            "head": head,
            "marker": "...[truncated %d of %d bytes; sha256 %s]..." % (
                len(raw) - len(head_bytes) - len(tail_bytes),
                len(raw), digest[:16]),
            "critical": critical,
            "tail": tail,
            "omitted_bytes": len(raw) - len(head_bytes) - len(tail_bytes),
            "total_bytes": len(raw),
            "question": question.strip(),
            "paths": list(paths or [])}


def retrieve(output: str, offset: int, length: int) -> str:
    """Targeted range retrieval by byte offset (continuation handle)."""
    raw = _sanitize(output).encode("utf-8")
    if offset < 0 or length <= 0 or offset >= len(raw):
        raise ValueError("bad continuation range %d+%d for %d bytes" % (
            offset, length, len(raw)))
    return raw[offset:offset + length].decode("utf-8", errors="replace")


def validate(envelope: Dict[str, Any], output: str,
             budget: int = ENVELOPE_BYTES_MAX) -> List[str]:
    """Return repair strings; empty means the envelope is honest."""
    repairs = []
    raw = _sanitize(output).encode("utf-8")
    want = hashlib.sha256(raw).hexdigest()
    if envelope.get("digest") != want:
        repairs.append("envelope digest does not match output bytes")
    truncated = len(raw) > budget
    if truncated and not envelope.get("truncated"):
        repairs.append("unmarked truncation: output exceeds the envelope "
                       "but truncated is false")
    if envelope.get("truncated") and not envelope.get("marker"):
        repairs.append("truncated envelope has no truncation marker")
    if envelope.get("truncated") and not envelope.get("handle"):
        repairs.append("truncated envelope has no continuation handle")
    return repairs
