"""queue_store — storage adapters for the v2 execution queue.

Phase 1 of #283. Every backend implements one small contract, so moving
the queue off GitHub is one config value plus ``export``/``import``:

``load() -> (state | None, token)``
    The stored state (``None`` when no queue exists) and an opaque token
    naming the version that was read.
``save(state, token)``
    Compare-and-swap: write only if the stored version is still
    ``token`` (``None`` = "no queue may exist yet"), else raise
    ``ConflictError``.
``append(events)`` / ``events()``
    The append-only event log. ``events`` returns every parseable event,
    including orphans from a lost compare-and-swap; ``queue_core.chain``
    decides which are committed.
``check(state, events)``
    Raise ``BudgetError`` if the write would not fit this backend. It is
    called before anything is written.

Backends: ``MemoryAdapter`` (tests), ``GitFileAdapter`` (``queue.json`` +
``history.jsonl`` in any directory, typically inside a git checkout; no
GitHub API), ``GitHubIssueAdapter`` (state rendered in an Issue body,
events in marked Issue comments). Standard library only.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import urllib.error
import urllib.request

import queue_core as core

EVENTS_MARKER = "<!-- agent-engineering-standard:queue:v2:events -->"
V1_MARKER = "<!-- agent-engineering-standard:queue:v1 -->"
EXPORT_FORMAT = "aes-work-queue-export"
# GitHub caps an Issue body and a comment at 65,536 characters.
BODY_LIMIT = 60000
COMMENT_LIMIT = 60000

_EVENTS_BLOCK = re.compile(re.escape(EVENTS_MARKER) + r"\s*```json\s*\n(.*?)\n```",
                           re.S)


class ConflictError(core.QueueError):
    """The store changed between read and write; nothing was overwritten."""


class LegacyQueueError(core.QueueError):
    """The store holds a v1 queue, which v1 code must handle."""


def _line(event):
    return json.dumps(event, ensure_ascii=False, separators=(",", ":"))


def _check_state_size(state, limit):
    if core.size(state) > limit:
        raise core.BudgetError("queue state would be %d bytes, over this "
                               "backend's %d-byte limit; nothing written"
                               % (core.size(state), limit))


class MemoryAdapter:
    """In-process store for tests."""

    name = "memory"

    def __init__(self):
        self.limit = core.STATE_BUDGET
        self._state = None
        self._version = 0
        self._events = []

    def load(self):
        return copy.deepcopy(self._state), self._version if self._state else None

    def check(self, state, events):
        _check_state_size(state, self.limit)

    def save(self, state, token):
        current = self._version if self._state else None
        if token != current:
            raise ConflictError("memory queue changed since it was read")
        self._state = copy.deepcopy(state)
        self._version += 1

    def append(self, events):
        self._events.extend(copy.deepcopy(events))

    def events(self):
        return copy.deepcopy(self._events)


class GitFileAdapter:
    """``queue.json`` + ``history.jsonl`` under one directory.

    Compare-and-swap uses the sha256 of ``queue.json`` under an exclusive
    ``queue.lock`` (created with O_EXCL) and an atomic rename. The files
    are plain JSON and JSONL, so any git host, or none, can carry them;
    committing them is ordinary git work for the caller.
    """

    name = "git-file"

    def __init__(self, root):
        self.root = root
        self.limit = core.STATE_BUDGET
        self.state_path = os.path.join(root, "queue.json")
        self.history_path = os.path.join(root, "history.jsonl")
        self.lock_path = os.path.join(root, "queue.lock")

    def _read(self):
        try:
            with open(self.state_path, "rb") as handle:
                return handle.read()
        except FileNotFoundError:
            return None

    def load(self):
        raw = self._read()
        if raw is None:
            return None, None
        try:
            state = json.loads(raw.decode("utf-8"))
        except ValueError as exc:
            raise core.FormatError("%s is malformed: %s" % (self.state_path, exc))
        core.validate(state)
        return state, hashlib.sha256(raw).hexdigest()

    def check(self, state, events):
        _check_state_size(state, self.limit)

    def _locked(self, action):
        os.makedirs(self.root, exist_ok=True)
        try:
            fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise ConflictError(
                "%s is held by another writer; if no writer is running, "
                "remove it and re-run" % self.lock_path)
        try:
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return action()
        finally:
            os.unlink(self.lock_path)

    def save(self, state, token):
        def write():
            raw = self._read()
            current = hashlib.sha256(raw).hexdigest() if raw is not None else None
            if current != token:
                raise ConflictError("%s changed since it was read; nothing "
                                    "written, re-run" % self.state_path)
            temp = self.state_path + ".tmp"
            with open(temp, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(state, indent=1, ensure_ascii=False) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, self.state_path)
        self._locked(write)

    def append(self, events):
        def write():
            with open(self.history_path, "a", encoding="utf-8") as handle:
                handle.write("".join(_line(e) + "\n" for e in events))
                handle.flush()
                os.fsync(handle.fileno())
        self._locked(write)

    def events(self):
        try:
            with open(self.history_path, encoding="utf-8") as handle:
                lines = handle.read().splitlines()
        except FileNotFoundError:
            return []
        found = []
        for line in lines:
            try:
                found.append(json.loads(line))
            except ValueError:
                continue
        return found


def _default_http(api="https://api.github.com"):
    """urllib JSON client; GITHUB_TOKEN/GH_TOKEN when set, else the proxy."""
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")

    def http(method, path, payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(api + path, data=data, method=method)
        request.add_header("Accept", "application/vnd.github+json")
        request.add_header("Content-Type", "application/json")
        if token:
            request.add_header("Authorization", "Bearer " + token)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except (urllib.error.URLError, ValueError) as exc:
            raise IOError("GitHub %s %s failed: %s" % (method, path, exc))

    return http


class GitHubIssueAdapter:
    """State rendered in an Issue body; events in marked Issue comments.

    GitHub offers no conditional PATCH, so ``save`` re-reads the body and
    compares its sha256 immediately before the PATCH, then reads it back
    and raises ``ConflictError`` if another writer landed in between.
    Comments are trusted only through the hash chain from the committed
    head, so anyone's comment is harmless.
    """

    name = "github-issue"

    def __init__(self, repo, issue, http=None):
        self.repo = repo
        self.issue = issue
        self.http = http or _default_http()
        self.limit = core.STATE_BUDGET
        self.body_limit = BODY_LIMIT
        self.comment_limit = COMMENT_LIMIT
        self._path = "/repos/%s/issues/%d" % (repo, issue)

    def _body(self):
        return self.http("GET", self._path).get("body") or ""

    def load(self):
        body = self._body()
        token = hashlib.sha256(body.encode("utf-8")).hexdigest()
        if core.MARKER in body:
            return core.parse_block(body), token
        if V1_MARKER in body:
            raise LegacyQueueError("Issue #%d holds a v1 queue" % self.issue)
        return None, token

    def _comments(self, events):
        """Split ``events`` into marked comment bodies under the limit."""
        bodies, batch = [], []

        def render(batch):
            return "%s\n```json\n%s\n```\n" % (
                EVENTS_MARKER, json.dumps(batch, ensure_ascii=False, indent=0))

        for event in events:
            if len(render([event])) > self.comment_limit:
                raise core.BudgetError(
                    "history event %s would exceed the %d-character comment "
                    "limit; nothing written" % (event["seq"], self.comment_limit))
            if batch and len(render(batch + [event])) > self.comment_limit:
                bodies.append(render(batch))
                batch = []
            batch.append(event)
        if batch:
            bodies.append(render(batch))
        return bodies

    def check(self, state, events):
        _check_state_size(state, self.limit)
        body = core.render_markdown(state)
        if len(body) > self.body_limit:
            raise core.BudgetError("rendered Issue body would be %d characters, "
                                   "over the %d limit; nothing written"
                                   % (len(body), self.body_limit))
        self._comments(events)

    def save(self, state, token):
        current = self._body()
        if hashlib.sha256(current.encode("utf-8")).hexdigest() != token:
            raise ConflictError("Issue #%d changed since it was read; nothing "
                                "written, re-run" % self.issue)
        body = core.render_markdown(state)
        self.http("PATCH", self._path, {"body": body})
        if self._body() != body:
            raise ConflictError("Issue #%d was written by another session "
                                "during this write; re-read it with show and "
                                "re-run" % self.issue)

    def append(self, events):
        for body in self._comments(events):
            self.http("POST", self._path + "/comments", {"body": body})

    def events(self):
        found, page = [], 1
        while True:
            batch = self.http("GET", "%s/comments?per_page=100&page=%d"
                              % (self._path, page))
            for comment in batch:
                match = _EVENTS_BLOCK.search(comment.get("body") or "")
                if not match:
                    continue
                try:
                    parsed = json.loads(match.group(1))
                except ValueError:
                    continue
                if isinstance(parsed, list):
                    found.extend(e for e in parsed if isinstance(e, dict))
            if len(batch) < 100:
                return found
            page += 1


# --------------------------------------------------------------------------
# Write protocol, export and import
# --------------------------------------------------------------------------


def commit(adapter, change, ctx, create=False):
    """Load, apply ``change``, seal, check, append events, then CAS-save.

    Events are appended before the state that points at them, so a lost
    compare-and-swap leaves only unreachable orphans, never a committed
    state with missing history.
    """
    state, token = adapter.load()
    if create:
        if state is not None:
            raise core.QueueError("a queue already exists here; init refused")
    elif state is None:
        raise core.FormatError("no queue found in the %s backend" % adapter.name)
    new, events = change(state)
    new, sealed = core.seal(new, events, ctx)
    adapter.check(new, sealed)
    adapter.append(sealed)
    adapter.save(new, token)
    return new


def export_bundle(adapter):
    state, _ = adapter.load()
    if state is None:
        raise core.FormatError("no queue to export in the %s backend" % adapter.name)
    return {"format": EXPORT_FORMAT, "version": core.VERSION, "state": state,
            "events": core.chain(adapter.events(), state)}


def import_bundle(adapter, bundle):
    """Write an exported queue into an empty backend, verbatim."""
    if not isinstance(bundle, dict) or bundle.get("format") != EXPORT_FORMAT \
            or bundle.get("version") != core.VERSION \
            or set(bundle) != {"format", "version", "state", "events"}:
        raise core.FormatError("not a v2 queue export bundle")
    state, events = bundle["state"], bundle["events"]
    core.validate(state)
    if not isinstance(events, list) or core.chain(events, state) != events:
        raise core.FormatError("bundle history does not chain exactly to its state")
    core.scan_secrets(bundle)
    existing, token = adapter.load()
    if existing is not None:
        raise core.QueueError("import needs an empty backend; %s already holds "
                              "a queue" % adapter.name)
    adapter.check(state, events)
    adapter.append(events)
    adapter.save(state, token)
    return state
