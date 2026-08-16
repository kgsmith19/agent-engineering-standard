#!/usr/bin/env python3
"""standardctl — deterministic verification, initialization, and update
tooling for the Agent Engineering Standard.

This is a single-file tool that uses only the Python standard library
(minimum Python 3.9; no PyYAML, no pip installs). It is the machine
counterpart of ``AGENTS.md``: every rule it enforces is stated there or in
``TEMPLATES/manifest.yaml``.

Subcommands
===========

``verify``
    Run every ``check_*`` rule against the repository tree. Exit 0 iff no
    finding of severity ``error`` exists. ``--select policy|lean|security``
    runs a documented subset; ``--json`` emits machine-readable output.

``doctor``
    File-level diagnosis (same checks as ``verify``). With ``--live`` it
    additionally performs read-only GitHub API GETs (requires
    ``GITHUB_TOKEN`` or ``GH_TOKEN``) and prints a desired-versus-actual
    diff for repository settings, the main-protection ruleset, labels, and
    milestones, using ``TEMPLATES/repository-settings.json`` and
    ``TEMPLATES/main-protection.ruleset.json`` as desired state. With
    ``--apply`` (implies ``--live``) it PATCHes settings, creates missing
    labels and the ``vNext`` milestone, and creates or updates the ruleset.

``init --target DIR --standard-ref REF [--apply] [--set KEY=VALUE ...]``
    Render this standard checkout's manifest into a consuming repository.
    Dry-run by default (prints the plan). Mode semantics: ``copy`` is a
    byte copy; ``render`` substitutes ``__TOKEN__`` values; ``adapt``
    installs only when the destination is absent (repo-owned afterwards);
    ``merge`` appends missing lines (used for ``.gitignore``); ``config``
    is live-settings desired state and is never written to the target.
    After rendering, any residual ``__TOKEN__`` in a written destination is
    a hard failure. ``standard.lock`` is written LAST, only after every
    other action succeeded; on any failure the lock is not written.

``update --target DIR --standard-ref REF [--apply] [--set KEY=VALUE ...]``
    Read the target's ``standard.lock``, load the manifest recorded there
    via ``git show <locked-commit>:TEMPLATES/manifest.yaml`` (fail closed
    when unreachable), then re-render copy/render destinations, preserve
    adapt-mode destinations, and delete files named in the new manifest's
    ``retired`` list. The lock is rewritten LAST; a failure mid-apply
    leaves the target's original lock bytes unchanged.

``status --issue N [--json]``
    Local, network-free status for one Issue: branches, worktrees, and the
    gitignored ledger under ``.agent-runtime/issues/<N>/``. The pure core
    functions (``compute_status``, ``release_ready``,
    ``owner_label_authorized``, ``detect_unknown_redispatch``) take plain
    data and never touch the network.

``evidence generate DIR --head SHA --claim id:result:path[,path...] ...``
    Digest every file under DIR and write ``DIR/manifest.json`` in the
    schema below. ``--command exit_code:command-line`` records executed
    commands; ``--diff-base SHA`` (with ``--root``) records
    ``tests_modified`` from ``git diff <SHA> HEAD -- tests/`` and, when
    true, an oracle_changes pointer to the pull request's "Oracle
    changes" section.

``evidence validate DIR --head SHA [--pr-head SHA]``
    Validate ``DIR/manifest.json`` against the evidence schema below.

``evidence index DIR``
    Emit the managed Evidence Index comment body (with its marker) from
    ``DIR/manifest.json`` on stdout.

``worktrees reconcile [--json]``
    Parse ``git worktree list --porcelain`` and report duplicate Issue
    claims and orphaned Issue worktrees.

``worktrees prune-safe [--json]``
    Delete only conclusively safe worktrees; every refusal is reported and
    never deletes.

Evidence manifest JSON schema (schema_version 1)
================================================

``.evidence/manifest.json`` is a single JSON object::

    {
      "schema_version": 1,              // REQUIRED, must equal 1
      "repository": "owner/repo",       // recommended
      "application": "app-slug",        // recommended
      "issue": 77,                      // recommended
      "pr": 80,                         // recommended
      "milestone": "vNext",             // recommended
      "head_sha": "<40-hex>",           // REQUIRED, exact tested head
      "base_sha": "<40-hex>",           // recommended
      "run_id": "runtime identifier",   // recommended
      "timestamp_utc": "ISO-8601",      // recommended
      "provider_roles": {               // recommended
        "builder": "anthropic/<model>",
        "verifier": "openai/<model>"
      },
      "commands": [                     // recommended
        {"command": "python -m unittest ...", "exit_code": 0}
      ],
      "environment": {"os": "...", "python": "..."},
      "claims": [                       // REQUIRED, may not be empty
        {
          "id": "AC1",                  // REQUIRED, unique
          "result": "pass",             // REQUIRED: pass | fail | skipped
          "ui": false,                  // optional; true => screenshot
          "risk": "R1",                 // optional: R0..R3; R2/R3 =>
                                        //   top-level verifier required
          "evidence": ["report.txt"]    // REQUIRED, >= 1 file path, each
                                        //   listed in files[]
        }
      ],
      "files": [                        // REQUIRED
        {
          "path": "report.txt",         // relative to the evidence dir
          "type": "report",             // screenshot | report | log |
                                        //   trace | video | contract |
                                        //   benchmark | corpus | other
          "sha256": "<64-hex>"          // REQUIRED, digest of the file
        }
      ],
      "summary": {"result": "pass"},    // recommended
      "verifier": {                     // REQUIRED when any claim is
        "head": "<40-hex>",             //   risk R2 or R3; head MUST equal
        "provider_family": "openai",    //   head_sha
        "result": "pass"                // REQUIRED inside verifier
      },
      "tests_modified": false,          // optional; true with
                                        //   oracle_changes "None." is a
                                        //   finding
      "oracle_changes": "None."         // REQUIRED: the exact string
                                        //   "None." or a NON-EMPTY list of
                                        //   disclosure objects, e.g.
                                        //   [{"change": "...",
                                        //     "justification": "..."}]
    }

Validation findings use these stable check ids: ``evidence-schema``,
``evidence-head-mismatch``, ``evidence-missing-file``,
``evidence-digest-mismatch``, ``evidence-claim-uncovered``,
``evidence-ui-claim-no-screenshot``, ``evidence-missing-verifier``,
``evidence-undisclosed-oracle-change``.

Subagent ledger format
======================

A ledger is plain text kept under ``.agent-runtime/issues/<n>/``. Task
state lines have the form::

    Task <task-id>: <STATE> [free text]

where ``<STATE>`` is one of DISPATCHING, ACTIVE, COMPLETE, BLOCKED,
UNKNOWN. A line containing the literal ``Reconciliation performed:``
records that worktree/subagent state was re-established; it clears all
previously recorded UNKNOWN marks. Re-dispatching a task that is still
UNKNOWN without an intervening reconciliation line is the finding
``unknown-subagent-redispatch``.

Restricted YAML grammar
=======================

``TEMPLATES/manifest.yaml`` (and the small config files this tool reads,
such as ``project.yaml`` and ``standard.lock``) are parsed with a
deliberately restricted grammar documented in the manifest's header
comment: 2-space indentation; ``key: value`` scalars; ``key:`` block
openers; ``- `` list items that are scalars or flat mappings; ``[]`` as
the only flow form; double-quoted or bare strings; no anchors, aliases,
flow mappings, multi-line scalars, tabs, or duplicate keys. Anything
outside the grammar is rejected with a clear error. Workflow YAML is NOT
parsed with this grammar; ``extract_workflow_structure`` performs
line/indentation-based structural extraction instead.
"""

import argparse
import ast
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TOKEN_ALLOWLIST = {
    "__APP_DISPLAY_NAME__",
    "__APP_SLUG__",
    "__REPOSITORY__",
    "__OWNER_LOGIN__",
    "__DEFAULT_BRANCH__",
    "__PR_GATE_CHECK__",
    "__MAIN_RULESET_NAME__",
    "__STANDARD_COMMIT__",
    "__MANIFEST_SHA256__",
    "__APPLIED_AT_UTC__",
    "__OWNER_BYPASS_ACTOR_ID__",
    "__CHECK_INTEGRATION_ID__",
}

# Actions with a specific expected pin. Every other action still must be
# pinned to a full 40-hex SHA with a trailing "# vX.Y.Z" comment.
PINNED_ACTIONS = {
    "actions/checkout": "3d3c42e5aac5ba805825da76410c181273ba90b1",
    "actions/upload-artifact": "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
}

ADAPTERS = {
    "CLAUDE.md": "# CLAUDE.md\n\n@AGENTS.md\n",
    "GEMINI.md": "# GEMINI.md\n\n@AGENTS.md\n",
}

GATE_WORKFLOW_NAME = "Agent Engineering Standard PR Gate"
GATE_JOB_NAME = "Agent Engineering Standard PR Gate"
MERGE_POLICY_NAME = "Agent Engineering Standard Merge Policy"
RULESET_NAME = "Agent Engineering Standard Main Protection"

WORK_STATE_MARKER = "<!-- agent-engineering-standard:work-state:v1 -->"
EVIDENCE_INDEX_MARKER = "<!-- agent-engineering-standard:evidence-index:v1 -->"

AGENTS_REQUIRED_SECTIONS = [
    "Objective",
    "Owner authority",
    "Sources of truth",
    "Session bootstrap",
    "Provider-neutral roles",
    "Releases and milestones",
    "Thin Issues and work claiming",
    "Worktrees and parallel work",
    "Context recovery and subagent tracking",
    "Risk classification",
    "Intent and behavioral claims",
    "Test quality",
    "Verification flow",
    "Evidence and artifacts",
    "Lean engineering",
    "Documentation and handoff",
    "PR Gate and merge behavior",
    "Agent boundaries",
    "Completion standard",
]

TOKEN_RE = re.compile(r"__[A-Z0-9_]+__")
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
USES_RE = re.compile(r"^\s*(?:-\s+)?uses:\s*(\S+)\s*(#.*)?$")
PIN_COMMENT_RE = re.compile(r"^#\s*v\d")
ISSUE_BRANCH_RE = re.compile(r"^issue/(\d+)-")
LEDGER_TASK_RE = re.compile(
    r"^Task\s+([A-Za-z0-9_.-]+):\s+"
    r"(DISPATCHING|ACTIVE|COMPLETE|BLOCKED|UNKNOWN)\b"
)
LEDGER_RECONCILE_MARK = "Reconciliation performed:"

# Workflow policy checks (pinning, permissions, gate shape) apply only to
# the standard's own workflows. The legacy transitional ci.yml is exempt
# until the manifest ships a pr-gate.yml mapping.
GATE_WORKFLOW_FILE = "pr-gate.yml"
MERGE_POLICY_FILE = "merge-policy.yml"
TRANSITIONAL_WORKFLOW_FILE = "ci.yml"
POLICY_WORKFLOW_FILES = (GATE_WORKFLOW_FILE, MERGE_POLICY_FILE)

GENERIC_GATE_NAMES = {"pr gate", "ci", "tests", "test", "build", "gate"}

VALID_MANIFEST_MODES = {"copy", "render", "adapt", "merge", "config"}

# The strict aggregator enforcement pattern shipped with the pr-gate
# workflow: the final job serializes the full needs context and asserts
# every dependency concluded exactly "success". Its recognizable
# fingerprint is a reference to toJSON(needs) together with a literal
# 'success' comparison inside the final job.
AGGREGATOR_PATTERN_NEEDS = "toJSON(needs)"
AGGREGATOR_PATTERN_SUCCESS = ("'success'", '"success"')

# Paths exempt from the unresolved-token scan: this tool and its tests
# necessarily contain literal token names as data.
UNRESOLVED_TOKEN_EXEMPT_FILES = {"tools/standardctl.py"}
UNRESOLVED_TOKEN_EXEMPT_PREFIXES = ("tests/",)

EXPECTED_LABELS = {
    "status:ready": "0e8a16",
    "status:active": "1d76db",
    "status:blocked": "b60205",
    "risk:R0": "c2e0c6",
    "risk:R1": "bfdadc",
    "risk:R2": "f9d0c4",
    "risk:R3": "e99695",
    "owner:allow-draft": "5319e7",
    "owner:hold-merge": "5319e7",
    "owner:policy-change": "5319e7",
}

EVIDENCE_FILE_TYPES = {
    "screenshot",
    "report",
    "log",
    "trace",
    "video",
    "contract",
    "benchmark",
    "corpus",
    "other",
}

# ---------------------------------------------------------------------------
# Infrastructure
# ---------------------------------------------------------------------------


@dataclass
class Finding:
    """One rule violation: which check, how severe, where, and why."""

    check_id: str
    severity: str  # "error" | "warning"
    path: str
    message: str


@dataclass
class Report:
    """Aggregated findings from one verification run."""

    findings: List[Finding] = field(default_factory=list)

    def extend(self, findings: List[Finding]) -> None:
        self.findings.extend(findings)

    def ok(self) -> bool:
        """True iff no finding of severity error exists."""
        return not any(f.severity == "error" for f in self.findings)

    def counts(self) -> Dict[str, int]:
        out = {"error": 0, "warning": 0}
        for f in self.findings:
            out[f.severity] = out.get(f.severity, 0) + 1
        return out

    def to_text(self, label: str = "verify") -> str:
        lines = []
        for f in self.findings:
            lines.append(
                "%s %s %s: %s"
                % (f.severity.upper(), f.check_id, f.path, f.message)
            )
        c = self.counts()
        if self.ok() and c["warning"] == 0:
            lines.append("%s: OK" % label)
        else:
            lines.append(
                "%s: %d error(s), %d warning(s)"
                % (label, c["error"], c["warning"])
            )
        return "\n".join(lines)

    def to_json(self) -> str:
        return json.dumps(
            {
                "ok": self.ok(),
                "counts": self.counts(),
                "findings": [asdict(f) for f in self.findings],
            },
            indent=2,
            sort_keys=True,
        )


def sha256_file(path: Path) -> str:
    """Streaming SHA-256 of a file (never loads the whole file)."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_git(root: Path, *args: str) -> "subprocess.CompletedProcess":
    """Run git rooted at *root*, capturing text output; never raises."""
    return subprocess.run(
        ["git", "-C", str(root)] + list(args),
        capture_output=True,
        text=True,
        check=False,
    )


def git_out(root: Path, *args: str) -> str:
    """Run git and return stdout; raise RuntimeError on failure."""
    proc = run_git(root, *args)
    if proc.returncode != 0:
        raise RuntimeError(
            "git %s failed in %s: %s"
            % (" ".join(args), root, proc.stderr.strip())
        )
    return proc.stdout


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------


class RestrictedYamlError(ValueError):
    """Input that falls outside the restricted manifest grammar."""


_BARE_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")
_FORBIDDEN_VALUE_LEADS = ("&", "*", "|", ">", "{", "%", "!", "`")


def _parse_scalar(raw: str, lineno: int) -> Any:
    """Parse one restricted-grammar scalar value."""
    value = raw.strip()
    if value == "[]":
        return []
    if value.startswith('"'):
        if len(value) < 2 or not value.endswith('"'):
            raise RestrictedYamlError(
                "line %d: unterminated quoted string" % lineno
            )
        inner = value[1:-1]
        if '"' in inner:
            raise RestrictedYamlError(
                "line %d: escape sequences and embedded quotes are not "
                "supported in the restricted grammar" % lineno
            )
        return inner
    if value.startswith(_FORBIDDEN_VALUE_LEADS) or value.startswith("["):
        raise RestrictedYamlError(
            "line %d: anchors, aliases, flow collections, and block "
            "scalars are outside the restricted grammar: %r" % (lineno, value)
        )
    if "#" in value:
        raise RestrictedYamlError(
            "line %d: inline comments are not supported in the restricted "
            "grammar: %r" % (lineno, value)
        )
    if value.isdigit():
        return int(value)
    return value


def parse_restricted_yaml(text: str, origin: str = "<string>") -> Dict:
    """Parse the restricted YAML grammar documented in the module docstring.

    Returns a nested structure of dicts, lists, strings, and ints.
    Rejects anything outside the grammar with RestrictedYamlError.
    """
    lines: List[Tuple[int, str, int]] = []
    for i, raw in enumerate(text.split("\n")):
        lineno = i + 1
        if "\t" in raw:
            raise RestrictedYamlError(
                "%s line %d: tabs are not permitted" % (origin, lineno)
            )
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if indent % 2 != 0:
            raise RestrictedYamlError(
                "%s line %d: indentation must be a multiple of 2 spaces"
                % (origin, lineno)
            )
        lines.append((indent, stripped, lineno))

    pos = [0]  # boxed cursor shared by the nested parse functions

    def error(lineno: int, message: str) -> RestrictedYamlError:
        return RestrictedYamlError("%s line %d: %s" % (origin, lineno, message))

    def parse_block(indent: int) -> Any:
        if pos[0] >= len(lines) or lines[pos[0]][0] != indent:
            lineno = lines[pos[0] - 1][2] if pos[0] else 0
            raise error(lineno, "expected an indented block")
        if lines[pos[0]][1].startswith("- "):
            return parse_list(indent)
        return parse_mapping(indent)

    def parse_mapping(indent: int) -> Dict:
        out: Dict[str, Any] = {}
        while pos[0] < len(lines):
            line_indent, content, lineno = lines[pos[0]]
            if line_indent < indent:
                break
            if line_indent > indent:
                raise error(lineno, "unexpected indentation")
            if content.startswith("- "):
                raise error(
                    lineno, "list item where a mapping entry was expected"
                )
            key, sep, rest = content.partition(":")
            key = key.strip()
            if not sep:
                raise error(lineno, "expected 'key: value' or 'key:'")
            if not _BARE_KEY_RE.match(key):
                raise error(lineno, "invalid key %r" % key)
            if key in out:
                raise error(lineno, "duplicate key %r" % key)
            rest = rest.strip()
            pos[0] += 1
            if rest == "":
                if pos[0] >= len(lines) or lines[pos[0]][0] <= indent:
                    raise error(
                        lineno, "key %r opens a block but nothing follows" % key
                    )
                if lines[pos[0]][0] != indent + 2:
                    raise error(
                        lines[pos[0]][2],
                        "nested blocks must be indented exactly 2 further",
                    )
                out[key] = parse_block(indent + 2)
            else:
                out[key] = _parse_scalar(rest, lineno)
        return out

    def parse_list(indent: int) -> List:
        items: List[Any] = []
        while pos[0] < len(lines):
            line_indent, content, lineno = lines[pos[0]]
            if line_indent != indent or not content.startswith("- "):
                if line_indent > indent:
                    raise error(lineno, "unexpected indentation in list")
                break
            rest = content[2:].strip()
            pos[0] += 1
            if not rest:
                raise error(lineno, "empty list items are not permitted")
            if _looks_like_kv(rest):
                key, _, value = rest.partition(":")
                key = key.strip()
                value = value.strip()
                if not _BARE_KEY_RE.match(key):
                    raise error(lineno, "invalid key %r in list item" % key)
                if not value:
                    raise error(
                        lineno,
                        "list items may only contain flat 'key: value' "
                        "pairs (no nested blocks)",
                    )
                item = {key: _parse_scalar(value, lineno)}
                while (
                    pos[0] < len(lines)
                    and lines[pos[0]][0] == indent + 2
                    and not lines[pos[0]][1].startswith("- ")
                ):
                    _, cont, cont_lineno = lines[pos[0]]
                    ckey, csep, cval = cont.partition(":")
                    ckey = ckey.strip()
                    cval = cval.strip()
                    if not csep or not cval or not _BARE_KEY_RE.match(ckey):
                        raise error(
                            cont_lineno,
                            "list-item continuation must be flat "
                            "'key: value'",
                        )
                    if ckey in item:
                        raise error(
                            cont_lineno, "duplicate key %r in list item" % ckey
                        )
                    item[ckey] = _parse_scalar(cval, cont_lineno)
                    pos[0] += 1
                items.append(item)
            else:
                items.append(_parse_scalar(rest, lineno))
        return items

    def _looks_like_kv(rest: str) -> bool:
        key, sep, value = rest.partition(":")
        if not sep:
            return False
        # "live:settings" style scalars are quoted in the grammar; a bare
        # word followed by ": " (or line end) is a mapping entry.
        return bool(_BARE_KEY_RE.match(key.strip())) and (
            value == "" or value.startswith(" ")
        )

    if not lines:
        return {}
    result = parse_mapping(0)
    if pos[0] < len(lines):
        raise error(lines[pos[0]][2], "trailing unparsed content")
    return result


def parse_manifest(text: str, origin: str = "TEMPLATES/manifest.yaml") -> Dict:
    """Parse and structurally validate the distribution manifest."""
    data = parse_restricted_yaml(text, origin)
    if not isinstance(data, dict):
        raise RestrictedYamlError("%s: manifest must be a mapping" % origin)
    return data


def extract_workflow_structure(text: str) -> Dict:
    """Line/indentation-based structural extraction from workflow YAML.

    Returns a dict with:
      name              workflow name or None
      triggers          list of trigger event names under on:
      has_path_filter   True when paths:/paths-ignore: appears under on:
      permissions       None (absent) | str ("read-all"...) | dict
      jobs              ordered {job_id: {name, needs, if, permissions,
                        steps, raw}}; each step is {name, uses, run}

    This is intentionally a regex/indentation heuristic, not a YAML
    parser; it only extracts the structure the policy checks need.
    """

    def unquote(value: str) -> str:
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            return value[1:-1]
        return value

    struct: Dict[str, Any] = {
        "name": None,
        "triggers": [],
        "has_path_filter": False,
        "permissions": None,
        "jobs": {},
    }
    lines = text.split("\n")
    current_top: Optional[str] = None
    current_job: Optional[str] = None
    job_subkey: Optional[str] = None
    job_spans: Dict[str, List[int]] = {}
    current_step: Optional[Dict[str, Any]] = None

    for idx, raw in enumerate(lines):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        stripped = raw.strip()

        if indent == 0:
            current_job = None
            job_subkey = None
            current_step = None
            match = re.match(r"^([A-Za-z_'\"][\w'\"-]*):\s*(.*)$", stripped)
            if not match:
                current_top = None
                continue
            key = match.group(1).strip("'\"")
            value = match.group(2).strip()
            current_top = "on" if key in ("on", "true") else key
            if current_top == "name":
                struct["name"] = unquote(value)
            elif current_top == "on" and value:
                inline = value.strip("[]")
                struct["triggers"].extend(
                    part.strip() for part in inline.split(",") if part.strip()
                )
            elif current_top == "permissions":
                struct["permissions"] = {} if value in ("", "{}") else value
            continue

        if current_top == "on":
            if indent == 2:
                match = re.match(r"^([\w-]+):", stripped)
                if match:
                    struct["triggers"].append(match.group(1))
            if re.match(r"^(paths|paths-ignore):", stripped):
                struct["has_path_filter"] = True
        elif current_top == "permissions":
            match = re.match(r"^([\w-]+):\s*(\S+)$", stripped)
            if match and isinstance(struct["permissions"], dict):
                struct["permissions"][match.group(1)] = match.group(2)
        elif current_top == "jobs":
            if indent == 2:
                match = re.match(r"^([A-Za-z_][\w-]*):\s*$", stripped)
                if match:
                    current_job = match.group(1)
                    job_subkey = None
                    current_step = None
                    struct["jobs"][current_job] = {
                        "name": None,
                        "needs": [],
                        "if": None,
                        "permissions": None,
                        "steps": [],
                        "raw": "",
                    }
                    job_spans[current_job] = [idx, idx]
                continue
            if current_job is None:
                continue
            job = struct["jobs"][current_job]
            job_spans[current_job][1] = idx
            if indent == 4:
                current_step = None
                match = re.match(r"^([\w-]+):\s*(.*)$", stripped)
                if not match:
                    continue
                key = match.group(1)
                value = match.group(2).strip()
                job_subkey = key
                if key == "name":
                    job["name"] = unquote(value)
                elif key == "if":
                    job["if"] = value
                elif key == "needs":
                    if value:
                        inline = value.strip("[]")
                        job["needs"] = [
                            part.strip().strip("'\"")
                            for part in inline.split(",")
                            if part.strip()
                        ]
                elif key == "permissions":
                    job["permissions"] = {} if value in ("", "{}") else value
            elif indent >= 6:
                if job_subkey == "needs" and stripped.startswith("- "):
                    job["needs"].append(stripped[2:].strip().strip("'\""))
                elif job_subkey == "permissions" and indent == 6:
                    match = re.match(r"^([\w-]+):\s*(\S+)$", stripped)
                    if match and isinstance(job["permissions"], dict):
                        job["permissions"][match.group(1)] = match.group(2)
                elif job_subkey == "steps":
                    if stripped.startswith("- "):
                        current_step = {"name": None, "uses": None, "run": None}
                        job["steps"].append(current_step)
                        rest = stripped[2:].strip()
                    elif current_step is not None:
                        rest = stripped
                    else:
                        continue
                    match = re.match(r"^(name|uses|run):\s*(.*)$", rest)
                    if match and current_step is not None:
                        key = match.group(1)
                        value = match.group(2).strip()
                        if key == "run":
                            current_step["run"] = value or "|"
                        else:
                            current_step[key] = unquote(value)

    for job_id, span in job_spans.items():
        struct["jobs"][job_id]["raw"] = "\n".join(lines[span[0]: span[1] + 1])
    return struct


def workflow_has_write_permission(struct: Dict) -> bool:
    """True when the workflow or any job declares a write permission."""

    def block_writes(block: Any) -> bool:
        if block is None:
            return False
        if isinstance(block, str):
            return "write" in block
        return any(str(level).strip() == "write" for level in block.values())

    if block_writes(struct.get("permissions")):
        return True
    return any(
        block_writes(job.get("permissions"))
        for job in struct.get("jobs", {}).values()
    )


def final_gate_job(struct: Dict) -> Optional[Tuple[str, Dict]]:
    """Pick the aggregator job: largest needs list, else the last job."""
    jobs = struct.get("jobs", {})
    if not jobs:
        return None
    best_id = None
    best_needs = -1
    for job_id, job in jobs.items():
        if len(job.get("needs", [])) > best_needs:
            best_id = job_id
            best_needs = len(job.get("needs", []))
    if best_needs <= 0:
        best_id = list(jobs)[-1]
    return best_id, jobs[best_id]


def parse_worktree_porcelain(text: str) -> List[Dict]:
    """Parse ``git worktree list --porcelain`` output into dicts.

    Blocks are separated by blank lines and contain ``worktree <path>``,
    ``HEAD <sha>``, ``branch refs/heads/<name>`` or ``detached``, and an
    optional ``locked`` line.
    """
    worktrees: List[Dict] = []
    current: Dict[str, Any] = {}
    for raw in text.split("\n"):
        line = raw.rstrip()
        if not line:
            if current:
                worktrees.append(current)
                current = {}
            continue
        if line.startswith("worktree "):
            current = {
                "path": line[len("worktree "):],
                "head": None,
                "branch": None,
                "detached": False,
                "locked": False,
            }
        elif line.startswith("HEAD "):
            current["head"] = line[len("HEAD "):]
        elif line.startswith("branch "):
            ref = line[len("branch "):]
            prefix = "refs/heads/"
            current["branch"] = (
                ref[len(prefix):] if ref.startswith(prefix) else ref
            )
        elif line == "detached":
            current["detached"] = True
        elif line == "locked" or line.startswith("locked "):
            current["locked"] = True
    if current:
        worktrees.append(current)
    return worktrees


# ---------------------------------------------------------------------------
# Repository model
# ---------------------------------------------------------------------------


class RepoModel:
    """Lazy view of one repository tree for the check functions.

    Files come from ``git ls-files --cached --others --exclude-standard``
    (tracked plus unignored-untracked), so verification sees the tree a
    commit would capture even before staging. Content is always read from
    the working tree.
    """

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self._files: Optional[List[str]] = None
        self._bytes_cache: Dict[str, Optional[bytes]] = {}
        self._manifest: Optional[Dict] = None
        self._manifest_error: Optional[str] = None
        self._manifest_loaded = False
        self._project: Optional[Dict] = None
        self._project_loaded = False
        self._workflows: Optional[Dict[str, Dict]] = None

    def files(self) -> List[str]:
        if self._files is None:
            proc = run_git(
                self.root,
                "ls-files",
                "--cached",
                "--others",
                "--exclude-standard",
            )
            if proc.returncode != 0:
                self._files = []
            else:
                seen = set()
                out = []
                for line in proc.stdout.splitlines():
                    line = line.strip()
                    if line and line not in seen:
                        seen.add(line)
                        out.append(line)
                self._files = sorted(out)
        return self._files

    def exists(self, rel: str) -> bool:
        return (self.root / rel).is_file()

    def read_bytes(self, rel: str) -> Optional[bytes]:
        if rel not in self._bytes_cache:
            path = self.root / rel
            try:
                self._bytes_cache[rel] = path.read_bytes()
            except OSError:
                self._bytes_cache[rel] = None
        return self._bytes_cache[rel]

    def read_text(self, rel: str) -> Optional[str]:
        data = self.read_bytes(rel)
        if data is None:
            return None
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return None

    @property
    def manifest_error(self) -> Optional[str]:
        self.manifest  # trigger load
        return self._manifest_error

    @property
    def manifest(self) -> Optional[Dict]:
        if not self._manifest_loaded:
            self._manifest_loaded = True
            text = self.read_text("TEMPLATES/manifest.yaml")
            if text is not None:
                try:
                    self._manifest = parse_manifest(text)
                except RestrictedYamlError as exc:
                    self._manifest_error = str(exc)
        return self._manifest

    @property
    def project(self) -> Optional[Dict]:
        if not self._project_loaded:
            self._project_loaded = True
            text = self.read_text("project.yaml")
            if text is not None:
                try:
                    self._project = parse_restricted_yaml(text, "project.yaml")
                except RestrictedYamlError:
                    self._project = None
        return self._project

    @property
    def is_standard_repo(self) -> bool:
        project = self.project or {}
        section = project.get("project", {})
        return (
            isinstance(section, dict)
            and section.get("type") == "engineering-standard"
        )

    def manifest_has_gate_mapping(self) -> bool:
        manifest = self.manifest or {}
        for mapping in manifest.get("mappings", []):
            if not isinstance(mapping, dict):
                continue
            dest = str(mapping.get("dest", ""))
            source = str(mapping.get("source", ""))
            if dest.endswith(GATE_WORKFLOW_FILE) or source.endswith(
                GATE_WORKFLOW_FILE
            ):
                return True
        return False

    def workflows(self) -> Dict[str, Dict]:
        """Workflow files present on disk: {filename: {text, structure}}."""
        if self._workflows is None:
            self._workflows = {}
            wf_dir = self.root / ".github" / "workflows"
            if wf_dir.is_dir():
                for path in sorted(wf_dir.iterdir()):
                    if path.suffix not in (".yml", ".yaml"):
                        continue
                    try:
                        text = path.read_text(encoding="utf-8")
                    except (OSError, UnicodeDecodeError):
                        continue
                    self._workflows[path.name] = {
                        "text": text,
                        "structure": extract_workflow_structure(text),
                        "rel": ".github/workflows/" + path.name,
                    }
        return self._workflows


# ---------------------------------------------------------------------------
# Check functions
# ---------------------------------------------------------------------------


def check_template_pairs(model: RepoModel) -> List[Finding]:
    """Every copy-mode manifest mapping with an existing dest must be
    byte-identical to its source (ISSUE.md <-> work-item.md,
    PULL_REQUEST.md <-> PULL_REQUEST_TEMPLATE.md, adapters)."""
    findings: List[Finding] = []
    manifest = model.manifest
    if not manifest:
        return findings
    for mapping in manifest.get("mappings", []):
        if not isinstance(mapping, dict) or mapping.get("mode") != "copy":
            continue
        source = str(mapping.get("source", ""))
        dest = str(mapping.get("dest", ""))
        if not source or not dest or source == dest:
            continue
        if dest == ".github/ISSUE_TEMPLATE/config.yml":
            continue  # reported by issue-config-mismatch
        if not model.exists(dest):
            continue
        src_bytes = model.read_bytes(source)
        dest_bytes = model.read_bytes(dest)
        if src_bytes is None:
            continue  # manifest-integrity reports the missing source
        if src_bytes != dest_bytes:
            findings.append(
                Finding(
                    "template-pair-mismatch",
                    "error",
                    dest,
                    "not byte-identical to canonical source %s" % source,
                )
            )
    return findings


def check_issue_config(model: RepoModel) -> List[Finding]:
    """TEMPLATES/ISSUE_CONFIG.yml and .github/ISSUE_TEMPLATE/config.yml
    must be byte-identical."""
    canonical = "TEMPLATES/ISSUE_CONFIG.yml"
    active = ".github/ISSUE_TEMPLATE/config.yml"
    if not model.exists(canonical):
        return []
    if not model.exists(active):
        return [
            Finding(
                "issue-config-mismatch",
                "error",
                active,
                "active copy of %s is missing" % canonical,
            )
        ]
    if model.read_bytes(canonical) != model.read_bytes(active):
        return [
            Finding(
                "issue-config-mismatch",
                "error",
                active,
                "not byte-identical to %s" % canonical,
            )
        ]
    return []


def check_adapters(model: RepoModel) -> List[Finding]:
    """Provider adapters must exist and contain exactly the import line;
    any extra content is duplicated policy."""
    findings: List[Finding] = []
    for name, expected in ADAPTERS.items():
        data = model.read_bytes(name)
        if data is None:
            findings.append(
                Finding(
                    "adapter-missing",
                    "error",
                    name,
                    "provider adapter is absent",
                )
            )
        elif data != expected.encode("utf-8"):
            findings.append(
                Finding(
                    "adapter-policy-duplication",
                    "error",
                    name,
                    "adapter must contain only the canonical import line; "
                    "policy belongs in AGENTS.md",
                )
            )
    return findings


def check_root_self_lock(model: RepoModel) -> List[Finding]:
    """The standard repository must not carry a root standard.lock
    pinning itself."""
    if not model.is_standard_repo:
        return []
    if model.exists("standard.lock") or "standard.lock" in model.files():
        return [
            Finding(
                "root-self-lock",
                "error",
                "standard.lock",
                "the standard repository must not pin itself with a root "
                "standard.lock",
            )
        ]
    return []


_FORBIDDEN_SEGMENTS = {"spec", "specs", "prd", "prds", "adr", "adrs"}
_FORBIDDEN_TRACKED_PREFIXES = (".superpowers/", ".agent-runtime/")
_FORBIDDEN_WORKFLOW_CONTENT = re.compile(
    r"(ai[_-]?review|watchdog)", re.IGNORECASE
)


def check_forbidden_artifacts(model: RepoModel) -> List[Finding]:
    """No forbidden process artifacts: test ledgers, SPEC/PRD/ADR
    documents, changelogs, committed plans, AI-review or watchdog
    workflow references."""
    findings: List[Finding] = []

    def forbid(path: str, reason: str) -> None:
        findings.append(Finding("forbidden-artifact", "error", path, reason))

    for path in model.files():
        lower = path.lower()
        segments = lower.split("/")
        base = segments[-1]
        stem = base.rsplit(".", 1)[0]
        dir_segments = segments[:-1]
        if stem == "test_ledger" or stem == "test-ledger":
            forbid(path, "test ledgers are forbidden")
        elif any(seg in _FORBIDDEN_SEGMENTS for seg in dir_segments):
            forbid(path, "SPEC/PRD/ADR directories are forbidden")
        elif stem in _FORBIDDEN_SEGMENTS or re.match(r"^adr[-_0-9]", stem):
            forbid(path, "SPEC/PRD/ADR documents are forbidden")
        elif base == "system_requirements.md":
            forbid(path, "System_Requirements documents are forbidden")
        elif stem.startswith("changelog") or stem == "changes":
            forbid(path, "changelog files are forbidden")
        elif "implementation-plan" in base or "implementation_plan" in base:
            forbid(path, "committed plan files are forbidden")
        elif lower.startswith(_FORBIDDEN_TRACKED_PREFIXES):
            forbid(
                path,
                "agent workspace folders must stay gitignored, never "
                "tracked",
            )
        elif "ai_review" in lower or "ai-review" in lower or (
            "watchdog" in base
        ):
            forbid(path, "AI-review/watchdog artifacts are forbidden")

    for name, workflow in model.workflows().items():
        if _FORBIDDEN_WORKFLOW_CONTENT.search(workflow["text"]):
            forbid(
                workflow["rel"],
                "workflow references forbidden AI-review/watchdog "
                "automation",
            )
    return findings


def check_unknown_tokens(model: RepoModel) -> List[Finding]:
    """Rendering tokens inside TEMPLATES/ must come from the allowlist."""
    findings: List[Finding] = []
    for path in model.files():
        if not path.startswith("TEMPLATES/"):
            continue
        text = model.read_text(path)
        if text is None:
            continue
        for token in sorted(set(TOKEN_RE.findall(text))):
            if token not in TOKEN_ALLOWLIST:
                findings.append(
                    Finding(
                        "unknown-token",
                        "error",
                        path,
                        "token %s is not in the allowlist" % token,
                    )
                )
    return findings


def check_unresolved_tokens(model: RepoModel) -> List[Finding]:
    """No __TOKEN__ may appear outside TEMPLATES/ (rendered trees must be
    fully resolved). The tool and its tests are exempt because they name
    tokens as data."""
    findings: List[Finding] = []
    for path in model.files():
        if path.startswith("TEMPLATES/"):
            continue
        if path in UNRESOLVED_TOKEN_EXEMPT_FILES:
            continue
        if path.startswith(UNRESOLVED_TOKEN_EXEMPT_PREFIXES):
            continue
        text = model.read_text(path)
        if text is None:
            continue
        for token in sorted(set(TOKEN_RE.findall(text))):
            findings.append(
                Finding(
                    "unresolved-token",
                    "error",
                    path,
                    "unresolved rendering token %s outside TEMPLATES/"
                    % token,
                )
            )
    return findings


def check_unauthorized_workflows(model: RepoModel) -> List[Finding]:
    """Only pr-gate.yml and merge-policy.yml may exist under
    .github/workflows/ (plus transitional ci.yml while the manifest has
    no pr-gate mapping)."""
    allowed = {GATE_WORKFLOW_FILE, MERGE_POLICY_FILE}
    if not model.manifest_has_gate_mapping():
        allowed.add(TRANSITIONAL_WORKFLOW_FILE)
    findings: List[Finding] = []
    names = set(model.workflows())
    for path in model.files():
        if path.startswith(".github/workflows/"):
            names.add(path.rsplit("/", 1)[-1])
    for name in sorted(names):
        if name not in allowed:
            findings.append(
                Finding(
                    "unauthorized-workflow",
                    "error",
                    ".github/workflows/" + name,
                    "workflow is not part of the standard "
                    "(allowed: %s)" % ", ".join(sorted(allowed)),
                )
            )
    return findings


def action_pinning_findings(rel: str, text: str) -> List[Finding]:
    """Directly-testable core of check_action_pinning for one workflow."""
    findings: List[Finding] = []
    for raw in text.split("\n"):
        match = USES_RE.match(raw)
        if not match:
            continue
        value = match.group(1).strip("'\"")
        comment = (match.group(2) or "").strip()
        name, _, ref = value.partition("@")
        segments = name.split("/")
        action = "/".join(segments[:2]) if len(segments) >= 2 else name
        if not ref or not SHA40_RE.match(ref):
            findings.append(
                Finding(
                    "floating-action-ref",
                    "error",
                    rel,
                    "uses: %s is not pinned to a full 40-hex commit SHA"
                    % value,
                )
            )
            continue
        if not PIN_COMMENT_RE.match(comment):
            findings.append(
                Finding(
                    "floating-action-ref",
                    "error",
                    rel,
                    "uses: %s lacks the required trailing '# vX.Y.Z' "
                    "version comment" % value,
                )
            )
        expected = PINNED_ACTIONS.get(action)
        if expected and ref != expected:
            findings.append(
                Finding(
                    "floating-action-ref",
                    "error",
                    rel,
                    "%s must be pinned to %s, found %s"
                    % (action, expected, ref),
                )
            )
    return findings


def check_action_pinning(model: RepoModel) -> List[Finding]:
    """Every action used by the standard's workflows is pinned to a full
    SHA with a version comment; PINNED_ACTIONS SHAs must match exactly."""
    findings: List[Finding] = []
    for name, workflow in model.workflows().items():
        if name not in POLICY_WORKFLOW_FILES:
            continue
        findings.extend(action_pinning_findings(workflow["rel"], workflow["text"]))
    return findings


_PR_CODE_RUN_RE = re.compile(
    r"(gh\s+pr\s+checkout|git\s+fetch[^\n]*(?:refs/pull|\bpull/))",
    re.IGNORECASE,
)


def privileged_pr_checkout_findings(rel: str, text: str, struct: Dict) -> List[Finding]:
    """Directly-testable core of check_privileged_pr_checkout."""
    privileged = "pull_request_target" in struct.get(
        "triggers", []
    ) or workflow_has_write_permission(struct)
    if not privileged:
        return []
    sensitive = []
    for raw in text.split("\n"):
        match = USES_RE.match(raw)
        if match:
            value = match.group(1)
            if "checkout" in value or "download-artifact" in value:
                sensitive.append(value)
    if _PR_CODE_RUN_RE.search(text):
        sensitive.append("PR ref fetch in run step")
    if not sensitive:
        return []
    return [
        Finding(
            "privileged-pr-checkout",
            "error",
            rel,
            "privileged workflow (write permissions or "
            "pull_request_target) checks out or downloads PR-controlled "
            "content: %s" % ", ".join(sorted(set(sensitive))),
        )
    ]


def check_privileged_pr_checkout(model: RepoModel) -> List[Finding]:
    """No privileged workflow may execute or download PR-controlled
    content."""
    findings: List[Finding] = []
    for workflow in model.workflows().values():
        findings.extend(
            privileged_pr_checkout_findings(
                workflow["rel"], workflow["text"], workflow["structure"]
            )
        )
    return findings


def check_workflow_permissions(model: RepoModel) -> List[Finding]:
    """The standard's workflows declare explicit permissions and the PR
    Gate workflow stays read-only."""
    findings: List[Finding] = []
    for name, workflow in model.workflows().items():
        if name not in POLICY_WORKFLOW_FILES:
            continue
        struct = workflow["structure"]
        if struct.get("permissions") is None:
            findings.append(
                Finding(
                    "workflow-permissions",
                    "error",
                    workflow["rel"],
                    "workflow has no explicit top-level permissions block",
                )
            )
        if name == GATE_WORKFLOW_FILE and workflow_has_write_permission(struct):
            findings.append(
                Finding(
                    "workflow-permissions",
                    "error",
                    workflow["rel"],
                    "the PR Gate workflow must not hold any write "
                    "permission",
                )
            )
    return findings


def check_gate_path_filters(model: RepoModel) -> List[Finding]:
    """The required PR Gate workflow must not use path filters; a
    path-filtered required check silently never reports."""
    workflow = model.workflows().get(GATE_WORKFLOW_FILE)
    if not workflow:
        return []
    if workflow["structure"].get("has_path_filter"):
        return [
            Finding(
                "required-workflow-path-filter",
                "error",
                workflow["rel"],
                "the required gate workflow must not use paths/"
                "paths-ignore filters",
            )
        ]
    return []


def gate_name_findings(rel: str, struct: Dict) -> List[Finding]:
    """Directly-testable core of check_gate_names."""
    findings: List[Finding] = []
    name = (struct.get("name") or "").strip()
    if name.casefold() in GENERIC_GATE_NAMES:
        findings.append(
            Finding(
                "generic-gate-name",
                "error",
                rel,
                "workflow name %r is generic; use the application-"
                "specific gate name (for this repository: %r)"
                % (name, GATE_WORKFLOW_NAME),
            )
        )
    final = final_gate_job(struct)
    if final:
        job_id, job = final
        job_name = (job.get("name") or job_id).strip()
        if job_name.casefold() in GENERIC_GATE_NAMES:
            findings.append(
                Finding(
                    "generic-gate-name",
                    "error",
                    rel,
                    "final gate job name %r is generic; the required "
                    "check context must be application-specific" % job_name,
                )
            )
    return findings


def check_gate_names(model: RepoModel) -> List[Finding]:
    """The gate workflow and its final job carry the application-specific
    gate name, never a generic one."""
    workflow = model.workflows().get(GATE_WORKFLOW_FILE)
    if not workflow:
        return []
    return gate_name_findings(workflow["rel"], workflow["structure"])


def gate_aggregator_findings(rel: str, struct: Dict) -> List[Finding]:
    """Directly-testable core of check_gate_aggregator."""
    findings: List[Finding] = []
    final = final_gate_job(struct)
    if not final:
        return findings
    job_id, job = final
    condition = job.get("if") or ""
    if "always()" not in condition:
        findings.append(
            Finding(
                "aggregator-accepts-skipped",
                "error",
                rel,
                "final gate job %r must run with 'if: always()' so "
                "skipped dependencies cannot vanish" % job_id,
            )
        )
    raw = job.get("raw", "")
    if not (
        AGGREGATOR_PATTERN_NEEDS in raw
        and any(mark in raw for mark in AGGREGATOR_PATTERN_SUCCESS)
    ):
        findings.append(
            Finding(
                "aggregator-accepts-skipped",
                "error",
                rel,
                "final gate job %r lacks the strict enforcement pattern "
                "(serialize toJSON(needs) and require every result == "
                "'success')" % job_id,
            )
        )
    other_jobs = {j for j in struct.get("jobs", {}) if j != job_id}
    needs = set(job.get("needs", []))
    if needs != other_jobs:
        findings.append(
            Finding(
                "aggregator-needs-incomplete",
                "error",
                rel,
                "final gate job %r needs %s but the workflow defines %s"
                % (job_id, sorted(needs), sorted(other_jobs)),
            )
        )
    return findings


def check_gate_aggregator(model: RepoModel) -> List[Finding]:
    """The gate's final job runs always(), rejects every non-success
    conclusion, and depends on every other job."""
    workflow = model.workflows().get(GATE_WORKFLOW_FILE)
    if not workflow:
        return []
    return gate_aggregator_findings(workflow["rel"], workflow["structure"])


def gate_noop_findings(rel: str, struct: Dict) -> List[Finding]:
    """Directly-testable core of check_gate_noop_stages."""
    findings: List[Finding] = []
    for job_id, job in struct.get("jobs", {}).items():
        effective = False
        for step in job.get("steps", []):
            if step.get("run") is not None:
                effective = True
            uses = step.get("uses") or ""
            if uses and "checkout" not in uses:
                effective = True
        if not effective:
            findings.append(
                Finding(
                    "noop-stage",
                    "error",
                    rel,
                    "gate job %r performs no verification (no run step "
                    "and no non-checkout action); empty-success stages "
                    "are forbidden" % job_id,
                )
            )
    return findings


def check_gate_noop_stages(model: RepoModel) -> List[Finding]:
    """No gate job may be an empty success."""
    workflow = model.workflows().get(GATE_WORKFLOW_FILE)
    if not workflow:
        return []
    return gate_noop_findings(workflow["rel"], workflow["structure"])


_OVERRIDE_RE = re.compile(
    r"may override\b.*\bat any time", re.IGNORECASE | re.DOTALL
)
AUTHORITY_WAIVER_PHRASE = "Not run by owner instruction."
AUTHORITY_MACHINE_PHRASE = "ultimate machine gate"


def check_agents_authority(model: RepoModel) -> List[Finding]:
    """AGENTS.md keeps the 19 required sections in order and the owner-
    and machine-authority language."""
    findings: List[Finding] = []
    text = model.read_text("AGENTS.md")
    if text is None:
        return [
            Finding(
                "missing-authority-language",
                "error",
                "AGENTS.md",
                "AGENTS.md is missing",
            )
        ]
    headings = [
        line[3:].strip()
        for line in text.split("\n")
        if line.startswith("## ")
    ]
    cursor = 0
    missing = []
    for required in AGENTS_REQUIRED_SECTIONS:
        try:
            cursor = headings.index(required, cursor) + 1
        except ValueError:
            missing.append(required)
    if missing:
        findings.append(
            Finding(
                "missing-authority-language",
                "error",
                "AGENTS.md",
                "required sections missing or out of order: %s"
                % ", ".join(missing),
            )
        )
    if AUTHORITY_WAIVER_PHRASE not in text:
        findings.append(
            Finding(
                "missing-authority-language",
                "error",
                "AGENTS.md",
                "missing the owner-waiver phrase %r" % AUTHORITY_WAIVER_PHRASE,
            )
        )
    if not _OVERRIDE_RE.search(text):
        findings.append(
            Finding(
                "missing-authority-language",
                "error",
                "AGENTS.md",
                "missing an owner-override statement matching "
                "/may override .* at any time/i",
            )
        )
    if AUTHORITY_MACHINE_PHRASE not in text:
        findings.append(
            Finding(
                "missing-authority-language",
                "error",
                "AGENTS.md",
                "missing the machine-authority phrase %r"
                % AUTHORITY_MACHINE_PHRASE,
            )
        )
    return findings


AGENTS_SOFT_LINE_BUDGET = 350
AGENTS_HARD_LINE_BUDGET = 420


def check_agents_line_budget(model: RepoModel) -> List[Finding]:
    """AGENTS.md stays within its line budget (soft 350 + tolerance,
    warning above 420); a bloated policy file stops being read."""
    text = model.read_text("AGENTS.md")
    if text is None:
        return []
    count = len(text.split("\n"))
    if count > AGENTS_HARD_LINE_BUDGET:
        return [
            Finding(
                "agents-line-budget",
                "warning",
                "AGENTS.md",
                "%d lines exceeds the budget of %d (soft %d)"
                % (count, AGENTS_HARD_LINE_BUDGET, AGENTS_SOFT_LINE_BUDGET),
            )
        ]
    return []


def check_test_justifications(model: RepoModel) -> List[Finding]:
    """Every def test_ in tests/ carries a docstring stating the
    protected behavior and the defect it catches."""
    findings: List[Finding] = []
    for path in model.files():
        if not path.startswith("tests/") or not path.endswith(".py"):
            continue
        text = model.read_text(path)
        if text is None:
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            findings.append(
                Finding(
                    "missing-test-justification",
                    "error",
                    path,
                    "test file is unparseable: %s" % exc,
                )
            )
            continue
        for node in ast.walk(tree):
            if isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef)
            ) and node.name.startswith("test_"):
                if not (ast.get_docstring(node) or "").strip():
                    findings.append(
                        Finding(
                            "missing-test-justification",
                            "error",
                            path,
                            "%s lacks a docstring justifying the protected "
                            "behavior and the defect it catches" % node.name,
                        )
                    )
    return findings


def check_manifest_integrity(model: RepoModel) -> List[Finding]:
    """The distribution manifest parses, every source exists, modes are
    valid, dests are unique, and retired entries are not still mapped."""
    if not (model.root / "TEMPLATES").is_dir():
        return []  # consuming repository: no manifest expected
    findings: List[Finding] = []
    manifest_path = "TEMPLATES/manifest.yaml"
    if not model.exists(manifest_path):
        return [
            Finding(
                "manifest-integrity",
                "error",
                manifest_path,
                "distribution manifest is missing",
            )
        ]
    if model.manifest is None:
        return [
            Finding(
                "manifest-integrity",
                "error",
                manifest_path,
                "manifest is unparseable: %s" % model.manifest_error,
            )
        ]
    manifest = model.manifest
    if manifest.get("schema_version") != 1:
        findings.append(
            Finding(
                "manifest-integrity",
                "error",
                manifest_path,
                "schema_version must be 1",
            )
        )
    mappings = manifest.get("mappings")
    if not isinstance(mappings, list) or not mappings:
        findings.append(
            Finding(
                "manifest-integrity",
                "error",
                manifest_path,
                "manifest has no mappings list",
            )
        )
        mappings = []
    seen_dests: Dict[str, int] = {}
    dests = set()
    for index, mapping in enumerate(mappings):
        label = "mappings[%d]" % index
        if not isinstance(mapping, dict):
            findings.append(
                Finding(
                    "manifest-integrity",
                    "error",
                    manifest_path,
                    "%s is not a mapping" % label,
                )
            )
            continue
        source = str(mapping.get("source", ""))
        dest = str(mapping.get("dest", ""))
        mode = str(mapping.get("mode", ""))
        if not source or not dest or not mode:
            findings.append(
                Finding(
                    "manifest-integrity",
                    "error",
                    manifest_path,
                    "%s must define source, dest, and mode" % label,
                )
            )
            continue
        if mode not in VALID_MANIFEST_MODES:
            findings.append(
                Finding(
                    "manifest-integrity",
                    "error",
                    manifest_path,
                    "%s has invalid mode %r (valid: %s)"
                    % (label, mode, ", ".join(sorted(VALID_MANIFEST_MODES))),
                )
            )
        if not model.exists(source):
            findings.append(
                Finding(
                    "manifest-integrity",
                    "error",
                    manifest_path,
                    "%s source %s does not exist" % (label, source),
                )
            )
        if dest in seen_dests:
            findings.append(
                Finding(
                    "manifest-integrity",
                    "error",
                    manifest_path,
                    "duplicate dest %s (mappings[%d] and %s)"
                    % (dest, seen_dests[dest], label),
                )
            )
        seen_dests[dest] = index
        dests.add(dest)
    retired = manifest.get("retired", [])
    if isinstance(retired, list):
        for entry in retired:
            if str(entry) in dests:
                findings.append(
                    Finding(
                        "manifest-integrity",
                        "error",
                        manifest_path,
                        "retired entry %s is still an active mapping dest"
                        % entry,
                    )
                )
    for token in manifest.get("tokens", []) or []:
        if str(token) not in TOKEN_ALLOWLIST:
            findings.append(
                Finding(
                    "manifest-integrity",
                    "error",
                    manifest_path,
                    "manifest token %s is not in the tool allowlist" % token,
                )
            )
    return findings


# Check registry: (group, function). --select runs one group; the groups
# are documented in the verify --help text.
CHECKS: List[Tuple[str, Any]] = [
    ("policy", check_template_pairs),
    ("policy", check_issue_config),
    ("policy", check_adapters),
    ("policy", check_root_self_lock),
    ("policy", check_agents_authority),
    ("policy", check_manifest_integrity),
    ("policy", check_test_justifications),
    ("lean", check_forbidden_artifacts),
    ("lean", check_agents_line_budget),
    ("security", check_unknown_tokens),
    ("security", check_unresolved_tokens),
    ("security", check_unauthorized_workflows),
    ("security", check_action_pinning),
    ("security", check_privileged_pr_checkout),
    ("security", check_workflow_permissions),
    ("security", check_gate_path_filters),
    ("security", check_gate_names),
    ("security", check_gate_aggregator),
    ("security", check_gate_noop_stages),
]


def run_checks(model: RepoModel, select: Optional[str] = None) -> Report:
    """Run all checks (or one --select group) and return the Report."""
    report = Report()
    for group, check in CHECKS:
        if select and group != select:
            continue
        report.extend(check(model))
    return report


# ---------------------------------------------------------------------------
# verify / doctor subcommands
# ---------------------------------------------------------------------------


def cmd_verify(args: argparse.Namespace) -> int:
    model = RepoModel(Path(args.root))
    report = run_checks(model, args.select)
    print(report.to_json() if args.json else report.to_text())
    return 0 if report.ok() else 1


class GitHubApi:
    """Minimal urllib GitHub API client. All network access for doctor
    goes through this class so tests never need the network; the base URL
    is injectable."""

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.token = token

    def request(
        self,
        method: str,
        path: str,
        payload: Optional[Dict] = None,
    ) -> Tuple[int, Any]:
        url = self.base_url + path
        data = None
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer %s" % self.token,
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "standardctl",
        }
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            url, data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(request) as response:
                body = response.read().decode("utf-8")
                return response.status, (json.loads(body) if body else None)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            try:
                parsed = json.loads(body)
            except ValueError:
                parsed = body
            return exc.code, parsed

    def get(self, path: str) -> Tuple[int, Any]:
        return self.request("GET", path)


def diff_repository_settings(desired: Dict, actual: Dict) -> List[Tuple[str, Any, Any]]:
    """Pure desired-vs-actual comparison for repository settings."""
    diffs = []
    for key, want in desired.items():
        have = actual.get(key)
        if have != want:
            diffs.append((key, want, have))
    return diffs


def missing_label_names(expected: List[str], actual: List[str]) -> List[str]:
    """Pure: expected label names absent from the live label list."""
    have = {name.casefold() for name in actual}
    return [name for name in expected if name.casefold() not in have]


def render_ruleset_template(text: str, context: Dict[str, str]) -> str:
    """Render the ruleset JSON template's tokens (doctor renders before
    parsing; the raw template is deliberately not strict JSON because the
    actor and integration ids are bare integers)."""
    return render_tokens(text, context)


def cmd_doctor(args: argparse.Namespace) -> int:
    model = RepoModel(Path(args.root))
    report = run_checks(model)
    print(report.to_text())
    exit_code = 0 if report.ok() else 1
    if not (args.live or args.apply):
        return exit_code

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        print("doctor --live requires GITHUB_TOKEN or GH_TOKEN")
        return 1
    project = model.project or {}
    section = project.get("project", {}) if isinstance(project, dict) else {}
    repository = section.get("repository")
    if not repository:
        print("doctor --live requires project.yaml with project.repository")
        return 1
    api = GitHubApi(args.api_base_url, token)
    desired_settings = json.loads(
        (model.root / "TEMPLATES" / "repository-settings.json").read_text(
            encoding="utf-8"
        )
    )
    status, actual = api.get("/repos/%s" % repository)
    if status != 200:
        print("GET /repos/%s failed: %s" % (repository, status))
        return 1
    print("== repository settings ==")
    diffs = diff_repository_settings(desired_settings, actual)
    for key, want, have in diffs:
        print("  %s: desired=%r actual=%r" % (key, want, have))
    if not diffs:
        print("  in sync")

    status, labels = api.get("/repos/%s/labels?per_page=100" % repository)
    label_names = [lab["name"] for lab in labels] if status == 200 else []
    missing = missing_label_names(sorted(EXPECTED_LABELS), label_names)
    print("== labels ==")
    print("  missing: %s" % (", ".join(missing) if missing else "none"))

    status, milestones = api.get(
        "/repos/%s/milestones?state=open&per_page=100" % repository
    )
    milestone_titles = (
        [m["title"] for m in milestones] if status == 200 else []
    )
    print("== milestones ==")
    print(
        "  open: %s"
        % (", ".join(milestone_titles) if milestone_titles else "none")
    )

    ruleset_context = dict(args.set_values)
    display = section.get("display_name", "")
    ruleset_context.setdefault(
        "__MAIN_RULESET_NAME__",
        (project.get("protection", {}) or {}).get(
            "ruleset", "%s Main Protection" % display
        ),
    )
    ruleset_context.setdefault(
        "__PR_GATE_CHECK__",
        (project.get("ci", {}) or {}).get(
            "required_check", "%s PR Gate" % display
        ),
    )
    ruleset_name = ruleset_context["__MAIN_RULESET_NAME__"]
    status, rulesets = api.get("/repos/%s/rulesets?per_page=100" % repository)
    live_ruleset = None
    if status == 200:
        for entry in rulesets:
            if entry.get("name") == ruleset_name:
                live_ruleset = entry
    print("== ruleset ==")
    print(
        "  %r: %s"
        % (ruleset_name, "present" if live_ruleset else "MISSING")
    )
    if live_ruleset:
        status, detail = api.get(
            "/repos/%s/rulesets/%s" % (repository, live_ruleset["id"])
        )
        if status == 200:
            contexts = []
            for rule in detail.get("rules", []):
                if rule.get("type") == "required_status_checks":
                    for check in rule.get("parameters", {}).get(
                        "required_status_checks", []
                    ):
                        contexts.append(check.get("context"))
            print("  required checks: %s" % (contexts or "none"))

    if not args.apply:
        return exit_code

    print("== applying ==")
    status, _ = api.request("PATCH", "/repos/%s" % repository, desired_settings)
    print("  PATCH settings: %s" % status)
    for name in missing:
        status, _ = api.request(
            "POST",
            "/repos/%s/labels" % repository,
            {"name": name, "color": EXPECTED_LABELS[name]},
        )
        print("  create label %s: %s" % (name, status))
    if "vNext" not in milestone_titles:
        status, _ = api.request(
            "POST", "/repos/%s/milestones" % repository, {"title": "vNext"}
        )
        print("  create milestone vNext: %s" % status)
    template_text = (
        model.root / "TEMPLATES" / "main-protection.ruleset.json"
    ).read_text(encoding="utf-8")
    rendered = render_ruleset_template(template_text, ruleset_context)
    if TOKEN_RE.search(rendered):
        print(
            "  ruleset not applied: unresolved tokens %s (pass --set)"
            % sorted(set(TOKEN_RE.findall(rendered)))
        )
        return 1
    payload = json.loads(rendered)
    if live_ruleset:
        status, _ = api.request(
            "PUT",
            "/repos/%s/rulesets/%s" % (repository, live_ruleset["id"]),
            payload,
        )
        print("  PUT ruleset: %s" % status)
    else:
        status, _ = api.request(
            "POST", "/repos/%s/rulesets" % repository, payload
        )
        print("  POST ruleset: %s" % status)
    return exit_code


# ---------------------------------------------------------------------------
# init / update subcommands
# ---------------------------------------------------------------------------


def render_tokens(text: str, context: Dict[str, str]) -> str:
    """Substitute every context token; unknown tokens are left in place
    for the residual scan to catch."""
    for token, value in context.items():
        text = text.replace(token, str(value))
    return text


def parse_set_values(pairs: List[str]) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for pair in pairs or []:
        key, sep, value = pair.partition("=")
        if not sep or not TOKEN_RE.fullmatch(key):
            raise SystemExit(
                "--set expects __TOKEN__=value, got %r" % pair
            )
        if key not in TOKEN_ALLOWLIST:
            raise SystemExit("--set token %s is not in the allowlist" % key)
        values[key] = value
    return values


def build_render_context(
    standard_root: Path,
    ref: str,
    manifest_bytes: bytes,
    set_values: Dict[str, str],
) -> Dict[str, str]:
    """Assemble the token substitution map for init/update rendering."""
    context = dict(set_values)
    commit = git_out(standard_root, "rev-parse", ref).strip()
    context["__STANDARD_COMMIT__"] = commit
    context["__MANIFEST_SHA256__"] = hashlib.sha256(manifest_bytes).hexdigest()
    context.setdefault("__APPLIED_AT_UTC__", utc_now_iso())
    display = context.get("__APP_DISPLAY_NAME__")
    if display:
        context.setdefault("__PR_GATE_CHECK__", "%s PR Gate" % display)
        context.setdefault(
            "__MAIN_RULESET_NAME__", "%s Main Protection" % display
        )
    return context


def merge_gitignore(existing: Optional[str], fragment: str) -> str:
    """Append fragment lines missing from the existing .gitignore,
    preserving existing content and local additions."""
    if existing is None:
        existing = ""
    have = {line.strip() for line in existing.split("\n") if line.strip()}
    additions = [
        line
        for line in fragment.split("\n")
        if line.strip() and line.strip() not in have
    ]
    if not additions:
        return existing
    merged = existing
    if merged and not merged.endswith("\n"):
        merged += "\n"
    merged += "\n".join(additions) + "\n"
    return merged


@dataclass
class PlanAction:
    """One planned init/update action against the target tree."""

    mode: str  # copy | render | adapt | merge | config | retire | lock
    source: str
    dest: str
    action: str  # human-readable decision


def build_plan(
    manifest: Dict,
    standard_root: Path,
    target: Path,
    updating: bool,
) -> List[PlanAction]:
    """Turn manifest mappings (and, when updating, retired entries) into
    an ordered action plan. The standard.lock render is always ordered
    last so a failed apply never advances the lock."""
    actions: List[PlanAction] = []
    lock_action: Optional[PlanAction] = None
    for mapping in manifest.get("mappings", []):
        source = str(mapping.get("source", ""))
        dest = str(mapping.get("dest", ""))
        mode = str(mapping.get("mode", ""))
        if mode == "config":
            actions.append(
                PlanAction(mode, source, dest, "live desired state; not written")
            )
            continue
        if mode == "adapt" and (target / dest).exists():
            actions.append(
                PlanAction(mode, source, dest, "exists; repo-owned, preserved")
            )
            continue
        if mode == "render" and dest == "standard.lock":
            lock_action = PlanAction(
                "lock", source, dest, "written last, only after success"
            )
            continue
        verb = {
            "copy": "byte copy",
            "render": "render with token substitution",
            "adapt": "install (absent)",
            "merge": "merge missing lines",
        }.get(mode, mode)
        actions.append(PlanAction(mode, source, dest, verb))
    if updating:
        for entry in manifest.get("retired", []) or []:
            dest = str(entry)
            if (target / dest).exists():
                actions.append(
                    PlanAction("retire", "", dest, "delete retired file")
                )
    if lock_action:
        actions.append(lock_action)
    return actions


def print_plan(actions: List[PlanAction], target: Path, apply: bool) -> None:
    print("plan for target %s:" % target)
    for action in actions:
        arrow = "%s -> %s" % (action.source, action.dest) if action.source else action.dest
        print("  [%s] %s (%s)" % (action.mode, arrow, action.action))
    if not apply:
        print("DRY RUN (no --apply): nothing written")


def apply_plan(
    actions: List[PlanAction],
    standard_root: Path,
    target: Path,
    context: Dict[str, str],
) -> List[str]:
    """Execute every non-lock action; returns the relative paths written.

    Raises on the first failure. The caller only writes the lock after
    this function (and the residual-token scan) succeed.
    """
    written: List[str] = []
    for action in actions:
        if action.mode in ("config", "lock"):
            continue
        if action.action.endswith("preserved"):
            continue
        source_path = standard_root / action.source
        dest_path = target / action.dest
        if action.mode == "retire":
            dest_path.unlink()
            written.append(action.dest)
            continue
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        if action.mode == "copy":
            data = source_path.read_bytes()
            dest_path.write_bytes(data)
        elif action.mode == "adapt":
            # First install renders tokens (a no-op for token-free
            # sources); afterwards the destination is repo-owned and
            # never rewritten, so tokens must not survive install.
            text = source_path.read_text(encoding="utf-8")
            dest_path.write_text(render_tokens(text, context), encoding="utf-8")
        elif action.mode == "render":
            text = source_path.read_text(encoding="utf-8")
            dest_path.write_text(render_tokens(text, context), encoding="utf-8")
        elif action.mode == "merge":
            existing = None
            if dest_path.exists():
                existing = dest_path.read_text(encoding="utf-8")
            fragment = source_path.read_text(encoding="utf-8")
            dest_path.write_text(
                merge_gitignore(existing, fragment), encoding="utf-8"
            )
        else:
            raise RuntimeError("unknown plan mode %r" % action.mode)
        written.append(action.dest)
    return written


def residual_token_findings(target: Path, written: List[str]) -> List[str]:
    """Scan every written destination for unresolved __TOKEN__ residue."""
    problems = []
    for rel in written:
        path = target / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        tokens = sorted(set(TOKEN_RE.findall(text)))
        if tokens:
            problems.append("%s: %s" % (rel, ", ".join(tokens)))
    return problems


def write_lock(
    standard_root: Path, target: Path, context: Dict[str, str]
) -> None:
    template = (standard_root / "TEMPLATES" / "standard.lock").read_text(
        encoding="utf-8"
    )
    (target / "standard.lock").write_text(
        render_tokens(template, context), encoding="utf-8"
    )


def cmd_init(args: argparse.Namespace) -> int:
    standard_root = Path(args.root).resolve()
    target = Path(args.target).resolve()
    manifest_path = standard_root / "TEMPLATES" / "manifest.yaml"
    try:
        manifest_bytes = manifest_path.read_bytes()
        manifest = parse_manifest(manifest_bytes.decode("utf-8"))
    except (OSError, RestrictedYamlError) as exc:
        print("init: cannot load manifest: %s" % exc)
        return 1
    try:
        set_values = parse_set_values(args.set)
        context = build_render_context(
            standard_root, args.standard_ref, manifest_bytes, set_values
        )
    except (RuntimeError, SystemExit) as exc:
        print("init: %s" % exc)
        return 1
    actions = build_plan(manifest, standard_root, target, updating=False)
    print_plan(actions, target, args.apply)
    if not args.apply:
        return 0
    target.mkdir(parents=True, exist_ok=True)
    try:
        written = apply_plan(actions, standard_root, target, context)
    except (OSError, RuntimeError) as exc:
        print("init: apply failed, lock not written: %s" % exc)
        return 1
    problems = residual_token_findings(target, written)
    if problems:
        print("init: unresolved tokens remain, lock not written:")
        for problem in problems:
            print("  " + problem)
        return 1
    write_lock(standard_root, target, context)
    print("init: applied %d action(s); standard.lock written" % len(written))
    return 0


def derive_context_from_target(target: Path) -> Dict[str, str]:
    """Best-effort token values recovered from the target's project.yaml
    (--set always overrides)."""
    values: Dict[str, str] = {}
    path = target / "project.yaml"
    if not path.is_file():
        return values
    try:
        data = parse_restricted_yaml(
            path.read_text(encoding="utf-8"), str(path)
        )
    except (OSError, RestrictedYamlError):
        return values
    section = data.get("project", {}) if isinstance(data, dict) else {}
    if isinstance(section, dict):
        mapping = {
            "display_name": "__APP_DISPLAY_NAME__",
            "slug": "__APP_SLUG__",
            "repository": "__REPOSITORY__",
            "owner": "__OWNER_LOGIN__",
            "default_branch": "__DEFAULT_BRANCH__",
        }
        for key, token in mapping.items():
            value = section.get(key)
            if value:
                values[token] = str(value)
    ci = data.get("ci", {}) if isinstance(data, dict) else {}
    if isinstance(ci, dict) and ci.get("required_check"):
        values["__PR_GATE_CHECK__"] = str(ci["required_check"])
    protection = data.get("protection", {}) if isinstance(data, dict) else {}
    if isinstance(protection, dict) and protection.get("ruleset"):
        values["__MAIN_RULESET_NAME__"] = str(protection["ruleset"])
    return values


def cmd_update(args: argparse.Namespace) -> int:
    standard_root = Path(args.root).resolve()
    target = Path(args.target).resolve()
    lock_path = target / "standard.lock"
    if not lock_path.is_file():
        print("update: target has no standard.lock; run init first")
        return 1
    original_lock_bytes = lock_path.read_bytes()
    try:
        lock = parse_restricted_yaml(
            original_lock_bytes.decode("utf-8"), str(lock_path)
        )
    except (RestrictedYamlError, UnicodeDecodeError) as exc:
        print("update: unreadable standard.lock: %s" % exc)
        return 1
    locked_commit = str(
        (lock.get("standard", {}) or {}).get("commit", "")
    ).strip()
    if not SHA40_RE.match(locked_commit):
        print("update: standard.lock has no valid locked commit")
        return 1
    # Fail closed: the manifest recorded by the lock must be reachable.
    old_show = run_git(
        standard_root, "show", "%s:TEMPLATES/manifest.yaml" % locked_commit
    )
    if old_show.returncode != 0:
        print(
            "update: locked commit %s or its manifest is unreachable in "
            "%s; refusing to proceed" % (locked_commit, standard_root)
        )
        return 1
    try:
        old_manifest = parse_manifest(old_show.stdout, "locked manifest")
    except RestrictedYamlError as exc:
        print("update: locked manifest is unparseable: %s" % exc)
        return 1
    manifest_path = standard_root / "TEMPLATES" / "manifest.yaml"
    try:
        manifest_bytes = manifest_path.read_bytes()
        manifest = parse_manifest(manifest_bytes.decode("utf-8"))
    except (OSError, RestrictedYamlError) as exc:
        print("update: cannot load new manifest: %s" % exc)
        return 1
    try:
        set_values = parse_set_values(args.set)
        context = derive_context_from_target(target)
        context.update(set_values)
        context = build_render_context(
            standard_root, args.standard_ref, manifest_bytes, context
        )
    except (RuntimeError, SystemExit) as exc:
        print("update: %s" % exc)
        return 1
    actions = build_plan(manifest, standard_root, target, updating=True)
    new_dests = {
        str(m.get("dest"))
        for m in manifest.get("mappings", [])
        if isinstance(m, dict)
    }
    for mapping in old_manifest.get("mappings", []):
        if not isinstance(mapping, dict):
            continue
        dest = str(mapping.get("dest", ""))
        if (
            dest
            and dest not in new_dests
            and mapping.get("mode") in ("copy", "render")
            and (target / dest).exists()
        ):
            print(
                "note: %s was managed by the locked manifest but is no "
                "longer mapped; left in place" % dest
            )
    print_plan(actions, target, args.apply)
    if not args.apply:
        return 0
    try:
        written = apply_plan(actions, standard_root, target, context)
        problems = residual_token_findings(target, written)
        if problems:
            print("update: unresolved tokens remain, lock not advanced:")
            for problem in problems:
                print("  " + problem)
            return 1
        write_lock(standard_root, target, context)
    except (OSError, RuntimeError) as exc:
        # The lock is only ever written after full success; restore
        # defensively in case the failure happened inside write_lock.
        try:
            if lock_path.read_bytes() != original_lock_bytes:
                lock_path.write_bytes(original_lock_bytes)
        except OSError:
            pass
        print("update: apply failed, lock not advanced: %s" % exc)
        return 1
    print("update: applied %d action(s); standard.lock advanced" % len(written))
    return 0


# ---------------------------------------------------------------------------
# status subcommand (pure cores + local CLI)
# ---------------------------------------------------------------------------


def detect_unknown_redispatch(ledger_text: Optional[str]) -> List[Finding]:
    """A task marked UNKNOWN must not be re-dispatched without an
    intervening 'Reconciliation performed:' line (ledger format is in the
    module docstring)."""
    findings: List[Finding] = []
    if not ledger_text:
        return findings
    unknown_tasks: set = set()
    for lineno, raw in enumerate(ledger_text.split("\n"), start=1):
        line = raw.strip()
        if LEDGER_RECONCILE_MARK in line:
            unknown_tasks.clear()
            continue
        match = LEDGER_TASK_RE.match(line)
        if not match:
            continue
        task, state = match.group(1), match.group(2)
        if state == "UNKNOWN":
            unknown_tasks.add(task)
        elif state == "DISPATCHING" and task in unknown_tasks:
            findings.append(
                Finding(
                    "unknown-subagent-redispatch",
                    "error",
                    "ledger line %d" % lineno,
                    "Task %s was re-dispatched while UNKNOWN without a "
                    "'%s' line" % (task, LEDGER_RECONCILE_MARK),
                )
            )
            unknown_tasks.discard(task)
    return findings


def compute_status(
    issue: Dict,
    pull_requests: List[Dict],
    branches: List[str],
    worktrees: List[Dict],
    ledger_text: Optional[str],
) -> Dict:
    """Pure status computation: no network, no filesystem access."""
    task_states: Dict[str, str] = {}
    if ledger_text:
        for raw in ledger_text.split("\n"):
            match = LEDGER_TASK_RE.match(raw.strip())
            if match:
                task_states[match.group(1)] = match.group(2)
    findings = detect_unknown_redispatch(ledger_text)
    number = issue.get("number")
    issue_branches = [
        b
        for b in branches
        if ISSUE_BRANCH_RE.match(b)
        and ISSUE_BRANCH_RE.match(b).group(1) == str(number)
    ]
    issue_worktrees = [
        w
        for w in worktrees
        if w.get("branch")
        and ISSUE_BRANCH_RE.match(w["branch"])
        and ISSUE_BRANCH_RE.match(w["branch"]).group(1) == str(number)
    ]
    return {
        "issue": number,
        "title": issue.get("title"),
        "state": issue.get("state"),
        "labels": issue.get("labels", []),
        "branches": issue_branches,
        "worktrees": issue_worktrees,
        "pull_requests": pull_requests,
        "task_states": task_states,
        "findings": [asdict(f) for f in findings],
    }


def release_ready(milestone_issues: List[Dict]) -> Tuple[bool, List[str]]:
    """A release is ready only when every required Issue is closed and
    the milestone's VERIFY: Issue exists and is closed."""
    reasons: List[str] = []
    verify_issues = [
        issue
        for issue in milestone_issues
        if str(issue.get("title", "")).startswith("VERIFY:")
    ]
    if not verify_issues:
        reasons.append("milestone has no 'VERIFY: <milestone> release' Issue")
    for issue in milestone_issues:
        title = str(issue.get("title", ""))
        state = str(issue.get("state", "open")).lower()
        required = issue.get("required", True)
        if state != "closed" and required:
            if title.startswith("VERIFY:"):
                reasons.append(
                    "verification Issue #%s is still open" % issue.get("number")
                )
            else:
                reasons.append(
                    "required Issue #%s (%s) is still open"
                    % (issue.get("number"), title or "untitled")
                )
    return (not reasons, reasons)


def owner_label_authorized(
    timeline_events: List[Dict], label: str, owner_login: str
) -> bool:
    """True iff the most recent 'labeled' event for *label* has actor ==
    owner_login and no later 'unlabeled' event removed it. Events are in
    chronological order."""
    authorized = False
    for event in timeline_events:
        label_obj = event.get("label") or {}
        name = label_obj.get("name") if isinstance(label_obj, dict) else None
        name = name or event.get("label_name")
        if name != label:
            continue
        kind = event.get("event")
        if kind == "labeled":
            actor = event.get("actor") or {}
            login = actor.get("login") if isinstance(actor, dict) else None
            login = login or event.get("actor_login")
            authorized = login == owner_login
        elif kind == "unlabeled":
            authorized = False
    return authorized


def read_issue_ledger(root: Path, issue_number: int) -> Optional[str]:
    """Concatenate every readable text file in the Issue's gitignored
    ledger directory."""
    ledger_dir = root / ".agent-runtime" / "issues" / str(issue_number)
    if not ledger_dir.is_dir():
        return None
    chunks = []
    for path in sorted(ledger_dir.rglob("*")):
        if not path.is_file():
            continue
        try:
            chunks.append(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
    return "\n".join(chunks) if chunks else None


def cmd_status(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    branches: List[str] = []
    proc = run_git(
        root, "for-each-ref", "--format=%(refname:short)", "refs/heads"
    )
    if proc.returncode == 0:
        branches = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    worktrees: List[Dict] = []
    proc = run_git(root, "worktree", "list", "--porcelain")
    if proc.returncode == 0:
        worktrees = parse_worktree_porcelain(proc.stdout)
    ledger_text = read_issue_ledger(root, args.issue)
    # Without a token this stays local: the Issue dict is minimal and the
    # pull-request list is empty (API parts are skipped by design).
    status = compute_status(
        {"number": args.issue}, [], branches, worktrees, ledger_text
    )
    if args.json:
        print(json.dumps(status, indent=2, sort_keys=True))
    else:
        print("Issue #%s" % status["issue"])
        print("  branches: %s" % (", ".join(status["branches"]) or "none"))
        print(
            "  worktrees: %s"
            % (", ".join(w["path"] for w in status["worktrees"]) or "none")
        )
        if status["task_states"]:
            for task, state in sorted(status["task_states"].items()):
                print("  task %s: %s" % (task, state))
        for finding in status["findings"]:
            print(
                "  %s %s: %s"
                % (finding["severity"].upper(), finding["check_id"], finding["message"])
            )
    return 0 if not status["findings"] else 1


# ---------------------------------------------------------------------------
# evidence subcommand
# ---------------------------------------------------------------------------


def validate_evidence(
    manifest: Dict,
    evidence_dir: Path,
    head: str,
    pr_head: Optional[str] = None,
) -> List[Finding]:
    """Validate a parsed evidence manifest against the schema documented
    in the module docstring. Pure except for hashing listed files."""
    findings: List[Finding] = []
    where = str(evidence_dir / "manifest.json")

    def bad(check_id: str, message: str) -> None:
        findings.append(Finding(check_id, "error", where, message))

    if manifest.get("schema_version") != 1:
        bad("evidence-schema", "schema_version must be 1")
    head_sha = str(manifest.get("head_sha", ""))
    if head_sha != head:
        bad(
            "evidence-head-mismatch",
            "manifest head_sha %s does not equal the required head %s"
            % (head_sha or "<missing>", head),
        )
    if pr_head is not None and head_sha != pr_head:
        bad(
            "evidence-head-mismatch",
            "manifest head_sha %s does not equal the PR head %s"
            % (head_sha or "<missing>", pr_head),
        )

    files = manifest.get("files")
    file_types: Dict[str, str] = {}
    if not isinstance(files, list):
        bad("evidence-schema", "files must be a list")
        files = []
    for entry in files:
        if not isinstance(entry, dict) or not entry.get("path"):
            bad("evidence-schema", "files[] entries need path/type/sha256")
            continue
        rel = str(entry["path"])
        ftype = str(entry.get("type", "other"))
        if ftype not in EVIDENCE_FILE_TYPES:
            bad("evidence-schema", "file %s has unknown type %r" % (rel, ftype))
        file_types[rel] = ftype
        path = evidence_dir / rel
        if not path.is_file():
            findings.append(
                Finding(
                    "evidence-missing-file",
                    "error",
                    str(path),
                    "listed evidence file does not exist",
                )
            )
            continue
        expected = str(entry.get("sha256", ""))
        actual = sha256_file(path)
        if actual != expected:
            findings.append(
                Finding(
                    "evidence-digest-mismatch",
                    "error",
                    str(path),
                    "sha256 %s does not match manifest %s"
                    % (actual, expected or "<missing>"),
                )
            )

    claims = manifest.get("claims")
    if not isinstance(claims, list) or not claims:
        bad("evidence-schema", "claims must be a non-empty list")
        claims = []
    needs_verifier = False
    for claim in claims:
        if not isinstance(claim, dict) or not claim.get("id"):
            bad("evidence-schema", "claims[] entries need an id")
            continue
        claim_id = str(claim["id"])
        evidence_files = [
            str(p) for p in claim.get("evidence", []) if str(p) in file_types
        ]
        if not evidence_files:
            bad(
                "evidence-claim-uncovered",
                "claim %s has no evidence file listed in files[]" % claim_id,
            )
        if claim.get("ui") is True:
            if not any(
                file_types.get(p) == "screenshot" for p in evidence_files
            ):
                bad(
                    "evidence-ui-claim-no-screenshot",
                    "UI claim %s references no screenshot-type evidence"
                    % claim_id,
                )
        if str(claim.get("risk", "")) in ("R2", "R3"):
            needs_verifier = True
    if needs_verifier:
        verifier = manifest.get("verifier")
        if (
            not isinstance(verifier, dict)
            or str(verifier.get("head", "")) != head_sha
            or not verifier.get("result")
        ):
            bad(
                "evidence-missing-verifier",
                "R2/R3 claims require a top-level verifier object with "
                "head == head_sha and a result",
            )

    oracle = manifest.get("oracle_changes")
    if oracle is None:
        bad(
            "evidence-schema",
            "top-level oracle_changes is required: 'None.' or a non-empty "
            "list of disclosure objects",
        )
    elif isinstance(oracle, str):
        if oracle != "None.":
            bad(
                "evidence-schema",
                "oracle_changes string form must be exactly 'None.'",
            )
    elif isinstance(oracle, list):
        if not oracle:
            bad(
                "evidence-schema",
                "oracle_changes list form must be non-empty",
            )
    else:
        bad("evidence-schema", "oracle_changes must be 'None.' or a list")
    if manifest.get("tests_modified") is True and oracle == "None.":
        bad(
            "evidence-undisclosed-oracle-change",
            "tests_modified is true but oracle_changes claims 'None.'",
        )
    return findings


def evidence_index_body(manifest: Dict) -> str:
    """Render the managed Evidence Index comment body from a manifest."""
    lines = [EVIDENCE_INDEX_MARKER, "## Evidence Index", ""]
    repo = manifest.get("repository", "?")
    lines.append(
        "- Repository: %s | Issue: #%s | PR: #%s | Milestone: %s"
        % (
            repo,
            manifest.get("issue", "?"),
            manifest.get("pr", "?"),
            manifest.get("milestone", "?"),
        )
    )
    lines.append(
        "- Head: `%s` (base `%s`)"
        % (manifest.get("head_sha", "?"), manifest.get("base_sha", "?"))
    )
    lines.append(
        "- Run: %s at %s"
        % (manifest.get("run_id", "?"), manifest.get("timestamp_utc", "?"))
    )
    summary = manifest.get("summary", {})
    if isinstance(summary, dict) and summary.get("result"):
        lines.append("- Summary: %s" % summary["result"])
    verifier = manifest.get("verifier")
    if isinstance(verifier, dict):
        lines.append(
            "- Verifier: %s at `%s` -> %s"
            % (
                verifier.get("provider_family", "?"),
                verifier.get("head", "?"),
                verifier.get("result", "?"),
            )
        )
    lines.append("")
    lines.append("| Claim | Result | Evidence |")
    lines.append("| --- | --- | --- |")
    for claim in manifest.get("claims", []) or []:
        if not isinstance(claim, dict):
            continue
        evidence = ", ".join(
            "`%s`" % p for p in claim.get("evidence", [])
        )
        lines.append(
            "| %s | %s | %s |"
            % (claim.get("id", "?"), claim.get("result", "?"), evidence)
        )
    lines.append("")
    lines.append("| File | Type | SHA-256 |")
    lines.append("| --- | --- | --- |")
    for entry in manifest.get("files", []) or []:
        if not isinstance(entry, dict):
            continue
        lines.append(
            "| `%s` | %s | `%s` |"
            % (
                entry.get("path", "?"),
                entry.get("type", "?"),
                entry.get("sha256", "?"),
            )
        )
    return "\n".join(lines)


EVIDENCE_TYPE_BY_EXTENSION = {
    ".png": "screenshot",
    ".jpg": "screenshot",
    ".jpeg": "screenshot",
    ".txt": "log",
    ".log": "log",
    ".json": "report",
    ".html": "report",
    ".xml": "report",
    ".zip": "trace",
    ".webm": "video",
    ".mp4": "video",
}


def generate_evidence_manifest(
    evidence_dir: Path,
    head: str,
    claims: List[str],
    base: Optional[str] = None,
    repository: Optional[str] = None,
    application: Optional[str] = None,
    issue: Optional[int] = None,
    pr: Optional[int] = None,
    milestone: Optional[str] = None,
    run_id: Optional[str] = None,
    commands: Optional[List[str]] = None,
    diff_base: Optional[str] = None,
    repo_root: Optional[Path] = None,
) -> Dict:
    """Build a schema_version-1 evidence manifest from an evidence
    directory's contents.

    Claim specs are ``id:result:path[,path...]`` with paths relative to
    the evidence directory. Command specs are ``exit_code:command line``.
    When ``diff_base`` and ``repo_root`` are given and ``git diff
    --name-only <diff_base> HEAD -- tests/`` is non-empty, the manifest
    records ``tests_modified: true`` with an oracle_changes entry
    pointing at the pull request's "Oracle changes" section — the
    canonical disclosure location — instead of "None."; the semantic
    disclosure itself always lives in the pull request.
    """
    files = []
    for path in sorted(evidence_dir.rglob("*")):
        if not path.is_file() or path.name == "manifest.json":
            continue
        rel = path.relative_to(evidence_dir).as_posix()
        ftype = EVIDENCE_TYPE_BY_EXTENSION.get(path.suffix.lower(), "other")
        files.append(
            {"path": rel, "type": ftype, "sha256": sha256_file(path)}
        )
    claim_entries = []
    worst = "pass"
    for spec in claims:
        parts = spec.split(":", 2)
        if len(parts) != 3 or not parts[0] or not parts[1] or not parts[2]:
            raise ValueError(
                "claim spec %r is not id:result:path[,path...]" % spec
            )
        claim_id, result, paths = parts
        if result not in ("pass", "fail", "skipped"):
            raise ValueError("claim %s result %r invalid" % (claim_id, result))
        if result != "pass":
            worst = "fail"
        claim_entries.append(
            {
                "id": claim_id,
                "result": result,
                "evidence": [p for p in paths.split(",") if p],
            }
        )
    command_entries = []
    for spec in commands or []:
        code, _, line = spec.partition(":")
        command_entries.append(
            {"command": line, "exit_code": int(code)}
        )
    tests_modified = False
    if diff_base and repo_root is not None:
        proc = run_git(
            Path(repo_root), "diff", "--name-only", diff_base, "HEAD",
            "--", "tests/",
        )
        tests_modified = proc.returncode == 0 and bool(proc.stdout.strip())
    oracle_changes: Any = "None."
    if tests_modified:
        oracle_changes = [
            {
                "summary": (
                    "Test files changed in this change set; the semantic "
                    "disclosure is recorded in the pull request's "
                    "'Oracle changes' section."
                )
            }
        ]
    manifest: Dict[str, Any] = {
        "schema_version": 1,
        "head_sha": head,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "os": platform.platform(),
            "python": platform.python_version(),
        },
        "claims": claim_entries,
        "files": files,
        "summary": {"result": worst},
        "tests_modified": tests_modified,
        "oracle_changes": oracle_changes,
    }
    if base:
        manifest["base_sha"] = base
    if repository:
        manifest["repository"] = repository
    if application:
        manifest["application"] = application
    if issue is not None:
        manifest["issue"] = issue
    if pr is not None:
        manifest["pr"] = pr
    if milestone:
        manifest["milestone"] = milestone
    if run_id:
        manifest["run_id"] = run_id
    if command_entries:
        manifest["commands"] = command_entries
    return manifest


def cmd_evidence_generate(args: argparse.Namespace) -> int:
    evidence_dir = Path(args.dir).resolve()
    if not evidence_dir.is_dir():
        print("ERROR evidence-schema %s: not a directory" % evidence_dir)
        return 1
    try:
        manifest = generate_evidence_manifest(
            evidence_dir,
            head=args.head,
            claims=args.claim or [],
            base=args.base,
            repository=args.repository,
            application=args.application,
            issue=args.issue,
            pr=args.pr,
            milestone=args.milestone,
            run_id=args.run_id,
            commands=args.command or [],
            diff_base=args.diff_base,
            repo_root=Path(args.root),
        )
    except ValueError as exc:
        print("ERROR evidence-schema: %s" % exc)
        return 1
    out = evidence_dir / "manifest.json"
    out.write_text(
        json.dumps(manifest, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    print("evidence: wrote %s" % out)
    return 0


def cmd_evidence(args: argparse.Namespace) -> int:
    evidence_dir = Path(args.dir).resolve()
    manifest_path = evidence_dir / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(
            "%s evidence-schema %s: manifest unreadable: %s"
            % ("ERROR", manifest_path, exc)
        )
        return 1
    if args.evidence_command == "index":
        print(evidence_index_body(manifest))
        return 0
    findings = validate_evidence(manifest, evidence_dir, args.head, args.pr_head)
    report = Report(findings)
    print(report.to_json() if args.json else report.to_text("evidence"))
    return 0 if report.ok() else 1


# ---------------------------------------------------------------------------
# worktrees subcommand
# ---------------------------------------------------------------------------


def reconcile_worktrees(root: Path) -> Tuple[List[Dict], List[Finding]]:
    """Cross-reference worktrees against branches: duplicate Issue claims
    are errors; Issue worktrees with no remote branch are reported as
    orphans (informational)."""
    text = git_out(root, "worktree", "list", "--porcelain")
    worktrees = parse_worktree_porcelain(text)
    findings: List[Finding] = []
    by_issue: Dict[str, List[Dict]] = {}
    for worktree in worktrees:
        branch = worktree.get("branch") or ""
        match = ISSUE_BRANCH_RE.match(branch)
        if match:
            by_issue.setdefault(match.group(1), []).append(worktree)
    for issue_number, claimants in sorted(by_issue.items()):
        if len(claimants) > 1:
            findings.append(
                Finding(
                    "worktree-duplicate-claim",
                    "error",
                    ", ".join(w["path"] for w in claimants),
                    "Issue #%s is claimed by %d worktrees; exactly one "
                    "implementation writer is allowed"
                    % (issue_number, len(claimants)),
                )
            )
    remote_branches: List[str] = []
    proc = run_git(
        root, "for-each-ref", "--format=%(refname:short)", "refs/remotes"
    )
    if proc.returncode == 0:
        remote_branches = [
            line.strip() for line in proc.stdout.splitlines() if line.strip()
        ]
    for worktree in worktrees:
        branch = worktree.get("branch") or ""
        if not ISSUE_BRANCH_RE.match(branch):
            continue
        if not any(remote.endswith("/" + branch) for remote in remote_branches):
            findings.append(
                Finding(
                    "worktree-orphan",
                    "warning",
                    worktree["path"],
                    "worktree branch %s has no matching remote branch and "
                    "no known open PR; investigate before removing" % branch,
                )
            )
    return worktrees, findings


def _ledger_mentions_active(root: Path, worktree_path: str) -> bool:
    """True when any ledger line under .agent-runtime/ marks this
    worktree ACTIVE or UNKNOWN."""
    runtime = root / ".agent-runtime"
    if not runtime.is_dir():
        return False
    needles = {worktree_path, Path(worktree_path).name}
    for path in runtime.rglob("*"):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line in text.split("\n"):
            if ("ACTIVE" in line or "UNKNOWN" in line) and any(
                needle in line for needle in needles
            ):
                return True
    return False


def branch_content_merged(
    main_root: Path, default_branch: str, branch: str
) -> bool:
    """True when the branch's content is already contained in the default
    branch.

    Ancestry covers fast-forward and merge-commit history. Squash merges
    rewrite history, so ancestry fails for them; simulating the merge with
    ``git merge-tree --write-tree`` and comparing the resulting tree to
    the default branch's current tree recognizes exactly the branches
    that would add nothing new. A conflicting simulated merge is
    ambiguous and reports not-merged, which keeps pruning fail-safe.
    """
    ancestor = run_git(
        main_root, "merge-base", "--is-ancestor", branch, default_branch
    )
    if ancestor.returncode == 0:
        return True
    merge = run_git(
        main_root, "merge-tree", "--write-tree", default_branch, branch
    )
    if merge.returncode != 0:
        return False
    lines = merge.stdout.strip().splitlines()
    if not lines:
        return False
    tip_tree = run_git(
        main_root, "rev-parse", "%s^{tree}" % default_branch
    )
    return (
        tip_tree.returncode == 0
        and lines[0].strip() == tip_tree.stdout.strip()
    )


def prune_safe_worktrees(root: Path) -> Tuple[List[str], List[Finding]]:
    """Delete only conclusively safe worktrees; everything else becomes a
    worktree-unsafe-prune refusal that never deletes.

    Safe requires ALL of: clean tree; branch content fully represented in
    the default branch per ``branch_content_merged`` (ancestry, or a
    simulated ``git merge-tree`` merge whose result equals the default
    branch's tree — squash merges rewrite history, so ancestry alone is
    insufficient); no unpushed commits relative to an existing upstream;
    not locked; no ACTIVE/UNKNOWN ledger entry mentioning it.
    """
    text = git_out(root, "worktree", "list", "--porcelain")
    worktrees = parse_worktree_porcelain(text)
    if not worktrees:
        return [], []
    main_root = Path(worktrees[0]["path"])
    default_branch = "main"
    project_path = main_root / "project.yaml"
    if project_path.is_file():
        try:
            data = parse_restricted_yaml(
                project_path.read_text(encoding="utf-8"), str(project_path)
            )
            default_branch = (
                (data.get("project", {}) or {}).get("default_branch")
                or default_branch
            )
        except (OSError, RestrictedYamlError):
            pass
    deleted: List[str] = []
    findings: List[Finding] = []
    for worktree in worktrees[1:]:
        wt_path = worktree["path"]
        reasons: List[str] = []
        if worktree.get("locked"):
            reasons.append("worktree is locked")
        branch = worktree.get("branch")
        if worktree.get("detached") or not branch:
            reasons.append("detached HEAD (no branch to reconcile)")
        proc = run_git(Path(wt_path), "status", "--porcelain")
        if proc.returncode != 0 or proc.stdout.strip():
            reasons.append("working tree is not clean")
        if branch:
            if not branch_content_merged(main_root, default_branch, branch):
                reasons.append(
                    "branch %s is not fully represented in %s"
                    % (branch, default_branch)
                )
            upstream = run_git(
                Path(wt_path),
                "rev-parse",
                "--abbrev-ref",
                "--symbolic-full-name",
                "@{upstream}",
            )
            if upstream.returncode == 0:
                ahead = run_git(
                    Path(wt_path), "rev-list", "--count", "@{upstream}..HEAD"
                )
                if ahead.returncode != 0 or ahead.stdout.strip() != "0":
                    reasons.append("unpushed commits relative to upstream")
        if _ledger_mentions_active(main_root, wt_path):
            reasons.append("ledger records an ACTIVE/UNKNOWN entry for it")
        if reasons:
            findings.append(
                Finding(
                    "worktree-unsafe-prune",
                    "warning",
                    wt_path,
                    "refusing to delete: " + "; ".join(reasons),
                )
            )
            continue
        removal = run_git(main_root, "worktree", "remove", wt_path)
        if removal.returncode != 0:
            findings.append(
                Finding(
                    "worktree-unsafe-prune",
                    "warning",
                    wt_path,
                    "refusing to delete: git worktree remove failed: %s"
                    % removal.stderr.strip(),
                )
            )
            continue
        deleted.append(wt_path)
    return deleted, findings


def cmd_worktrees(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    if args.worktrees_command == "reconcile":
        try:
            worktrees, findings = reconcile_worktrees(root)
        except RuntimeError as exc:
            print("worktrees reconcile: %s" % exc)
            return 1
        if args.json:
            print(
                json.dumps(
                    {
                        "worktrees": worktrees,
                        "findings": [asdict(f) for f in findings],
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            for worktree in worktrees:
                print(
                    "worktree %s branch=%s"
                    % (worktree["path"], worktree.get("branch"))
                )
            for finding in findings:
                print(
                    "%s %s %s: %s"
                    % (
                        finding.severity.upper(),
                        finding.check_id,
                        finding.path,
                        finding.message,
                    )
                )
        return 0 if not any(f.severity == "error" for f in findings) else 1
    # prune-safe
    try:
        deleted, findings = prune_safe_worktrees(root)
    except RuntimeError as exc:
        print("worktrees prune-safe: %s" % exc)
        return 1
    if args.json:
        print(
            json.dumps(
                {
                    "deleted": deleted,
                    "findings": [asdict(f) for f in findings],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        for path in deleted:
            print("deleted %s" % path)
        for finding in findings:
            print(
                "%s %s %s: %s"
                % (
                    finding.severity.upper(),
                    finding.check_id,
                    finding.path,
                    finding.message,
                )
            )
        if not deleted and not findings:
            print("nothing to prune")
    return 0


# ---------------------------------------------------------------------------
# argparse main
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="standardctl",
        description=(
            "Deterministic verification, initialization, and update "
            "tooling for the Agent Engineering Standard."
        ),
    )
    parser.add_argument(
        "--root",
        default=".",
        help="repository root to operate on (default: current directory)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_verify = sub.add_parser(
        "verify",
        help="run all checks; exit 0 iff no error-severity finding",
        description=(
            "Check groups for --select: policy (template pairs, adapters, "
            "AGENTS.md authority, manifest integrity, test justifications, "
            "root self-lock), lean (forbidden artifacts, AGENTS.md line "
            "budget), security (tokens, workflow allowlist, action "
            "pinning, privileged checkout, permissions, gate shape)."
        ),
    )
    p_verify.add_argument(
        "--select", choices=["policy", "lean", "security"], default=None
    )
    p_verify.add_argument("--json", action="store_true")
    p_verify.set_defaults(func=cmd_verify)

    p_doctor = sub.add_parser(
        "doctor",
        help="file-level verify plus optional live GitHub settings diff",
    )
    p_doctor.add_argument("--live", action="store_true")
    p_doctor.add_argument("--apply", action="store_true")
    p_doctor.add_argument(
        "--api-base-url",
        default="https://api.github.com",
        help="GitHub API base URL (injectable for testing)",
    )
    p_doctor.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="__TOKEN__=VALUE",
        help="token values for rendering the ruleset template",
    )
    p_doctor.set_defaults(func=_doctor_dispatch)

    p_init = sub.add_parser(
        "init", help="render the standard into a consuming repository"
    )
    p_init.add_argument("--target", required=True)
    p_init.add_argument("--standard-ref", required=True)
    p_init.add_argument("--apply", action="store_true")
    p_init.add_argument(
        "--set", action="append", default=[], metavar="__TOKEN__=VALUE"
    )
    p_init.set_defaults(func=cmd_init)

    p_update = sub.add_parser(
        "update", help="update a consuming repository from its lock"
    )
    p_update.add_argument("--target", required=True)
    p_update.add_argument("--standard-ref", required=True)
    p_update.add_argument("--apply", action="store_true")
    p_update.add_argument(
        "--set", action="append", default=[], metavar="__TOKEN__=VALUE"
    )
    p_update.set_defaults(func=cmd_update)

    p_status = sub.add_parser(
        "status", help="local status for one Issue (no network)"
    )
    p_status.add_argument("--issue", type=int, required=True)
    p_status.add_argument("--json", action="store_true")
    p_status.set_defaults(func=cmd_status)

    p_evidence = sub.add_parser(
        "evidence", help="validate or index an evidence bundle"
    )
    evidence_sub = p_evidence.add_subparsers(
        dest="evidence_command", required=True
    )
    p_validate = evidence_sub.add_parser("validate")
    p_validate.add_argument("dir")
    p_validate.add_argument("--head", required=True)
    p_validate.add_argument("--pr-head", default=None)
    p_validate.add_argument("--json", action="store_true")
    p_validate.set_defaults(func=cmd_evidence)
    p_generate = evidence_sub.add_parser("generate")
    p_generate.add_argument("dir")
    p_generate.add_argument("--head", required=True)
    p_generate.add_argument("--base", default=None)
    p_generate.add_argument("--repository", default=None)
    p_generate.add_argument("--application", default=None)
    p_generate.add_argument("--issue", type=int, default=None)
    p_generate.add_argument("--pr", type=int, default=None)
    p_generate.add_argument("--milestone", default=None)
    p_generate.add_argument("--run-id", default=None)
    p_generate.add_argument("--claim", action="append", default=[])
    p_generate.add_argument("--command", action="append", default=[])
    p_generate.add_argument("--diff-base", default=None)
    p_generate.add_argument("--root", default=".")
    p_generate.set_defaults(func=cmd_evidence_generate)
    p_index = evidence_sub.add_parser("index")
    p_index.add_argument("dir")
    p_index.set_defaults(func=cmd_evidence, head=None, pr_head=None, json=False)

    p_worktrees = sub.add_parser(
        "worktrees", help="reconcile or safely prune worktrees"
    )
    worktrees_sub = p_worktrees.add_subparsers(
        dest="worktrees_command", required=True
    )
    p_reconcile = worktrees_sub.add_parser("reconcile")
    p_reconcile.add_argument("--json", action="store_true")
    p_reconcile.set_defaults(func=cmd_worktrees)
    p_prune = worktrees_sub.add_parser("prune-safe")
    p_prune.add_argument("--json", action="store_true")
    p_prune.set_defaults(func=cmd_worktrees)

    return parser


def _doctor_dispatch(args: argparse.Namespace) -> int:
    args.set_values = parse_set_values(args.set)
    if args.apply:
        args.live = True
    return cmd_doctor(args)


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
