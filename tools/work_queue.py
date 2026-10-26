#!/usr/bin/env python3
"""work_queue — one durable, ordered execution queue stored in a GitHub Issue.

Cloud agent containers are ephemeral, so the order in which work across
repositories is executed must live somewhere every fresh session in every
harness can read: a pinned GitHub Issue. The queue is an ordering of Issue
references plus a per-item status. It tracks no intent, criteria, or
evidence of its own (those stay on Issues and pull requests), so it is not
a second work tracker. Standard library only (Python 3.9+).

The Issue body holds a rendered checklist for humans followed by the
marker ``<!-- agent-engineering-standard:queue:v1 -->`` and a fenced JSON
block, which is the source of truth::

    {"version": 1, "next_id": 3, "items": [
        {"id": "Q01", "title": "...", "refs": ["owner/repo#1"],
         "status": "done", "note": "PR #9 merged at abc1234"}, ...]}

Invariants
==========

* Order is respected: items are only ever appended (``add``); no command
  reorders or deletes. Ids are monotonic and never reused.
* ``start`` refuses while any earlier item is not ``done`` or ``blocked``;
  ``block`` requires a reason, so skipping is always explicit and visible.
* Every write re-reads the Issue immediately before PATCH and aborts when
  ``updated_at`` moved (another writer), instead of overwriting it.
* A missing or malformed queue block fails closed and never writes.

Subcommands
===========

``show``                       print every item with status and refs
``next``                       print the first item neither done nor blocked
``add --title T [--ref R]...`` append one item to the end
``edit ID [--title] [--ref]... [--note]``  change details, never position
``start ID`` / ``done ID --evidence E`` / ``block ID --reason R`` /
``unblock ID``                 status transitions
``init``                       seed an empty queue into a marker-free Issue

The Issue is ``--issue N`` or ``AES_QUEUE_ISSUE`` (default: the owner's
queue, ``DEFAULT_ISSUE``), in ``--repo`` or ``AES_QUEUE_REPO`` (default
``kgsmith19/agent-engineering-standard``).
Authentication: ``GITHUB_TOKEN``/``GH_TOKEN`` when set; otherwise the
request is sent unauthenticated for a harness proxy to authorize.

Exit codes: 0 ok, 1 refused by an invariant, 2 malformed queue,
3 queue empty (``next``), 4 concurrent change, 5 transport failure.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
import urllib.error
import urllib.request

MARKER = "<!-- agent-engineering-standard:queue:v1 -->"
STATUSES = ("pending", "active", "blocked", "done")
DEFAULT_REPO = "kgsmith19/agent-engineering-standard"
# The owner's live queue Issue; --issue / AES_QUEUE_ISSUE override it.
DEFAULT_ISSUE = 277

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_FORMAT = 2
EXIT_EMPTY = 3
EXIT_CONFLICT = 4
EXIT_TRANSPORT = 5

_BLOCK = re.compile(re.escape(MARKER) + r"\s*```json\s*\n(.*?)\n```", re.S)
_CHECK = {"done": "x", "pending": " ", "active": " ", "blocked": " "}
_BADGE = {"done": "✅ done", "pending": "⏳ pending", "active": "🔨 active",
          "blocked": "⛔ blocked"}

HEADER = """## 📋 Execution Queue

Ordered queue of work across the owner's repositories. **Order is binding**: \
work the first item that is neither done nor blocked. Interruptions only edit \
an item's details or append to the end. Edit with `tools/work_queue.py` \
(agent-engineering-standard); the JSON block below is the source of truth \
and the checklist is regenerated from it on every write.
"""


class QueueError(Exception):
    """A command was refused by a queue invariant."""


class QueueFormatError(QueueError):
    """The Issue body holds no valid queue block."""


class ConcurrentChangeError(QueueError):
    """The Issue changed between read and write."""


# --------------------------------------------------------------------------
# Pure core
# --------------------------------------------------------------------------


def parse(body):
    """Return the queue state held in ``body``; fail closed when invalid."""
    match = _BLOCK.search(body or "")
    if not match:
        raise QueueFormatError("no queue block (marker %s) in Issue body" % MARKER)
    try:
        state = json.loads(match.group(1))
    except ValueError as exc:
        raise QueueFormatError("queue JSON is malformed: %s" % exc)
    _validate(state)
    return state


def _validate(state):
    if not isinstance(state, dict) or state.get("version") != 1:
        raise QueueFormatError("queue must be an object with version 1")
    items = state.get("items")
    if not isinstance(items, list):
        raise QueueFormatError("queue items must be a list")
    next_id = state.get("next_id")
    if not isinstance(next_id, int) or next_id < 1:
        raise QueueFormatError("next_id must be a positive integer")
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            raise QueueFormatError("queue item must be an object")
        for key, kind in (("id", str), ("title", str), ("refs", list),
                          ("status", str), ("note", str)):
            if not isinstance(item.get(key), kind):
                raise QueueFormatError("item %r: field %r must be %s"
                                       % (item.get("id"), key, kind.__name__))
        if item["status"] not in STATUSES:
            raise QueueFormatError("item %s: unknown status %r"
                                   % (item["id"], item["status"]))
        if item["id"] in seen:
            raise QueueFormatError("duplicate item id %s" % item["id"])
        seen.add(item["id"])


def render(state):
    """Render ``state`` as an Issue body: checklist, then the JSON block."""
    lines = [HEADER]
    upcoming = next_item(state)
    for item in state["items"]:
        refs = ", ".join(item["refs"]) or "no refs"
        line = "- [%s] **%s** %s — %s · %s" % (
            _CHECK[item["status"]], item["id"], item["title"], refs,
            _BADGE[item["status"]])
        if upcoming is not None and item["id"] == upcoming["id"]:
            line += " · 👉 **NEXT**"
        if item["note"]:
            line += "\n  - %s" % item["note"]
        lines.append(line)
    if not state["items"]:
        lines.append("_Queue is empty._")
    lines.append("")
    lines.append(MARKER)
    lines.append("```json")
    lines.append(json.dumps(state, indent=1, ensure_ascii=False))
    lines.append("```")
    return "\n".join(lines) + "\n"


def next_item(state):
    """First item that is neither done nor blocked, or None."""
    for item in state["items"]:
        if item["status"] not in ("done", "blocked"):
            return item
    return None


def _find(state, item_id):
    for item in state["items"]:
        if item["id"] == item_id:
            return item
    raise QueueError("no queue item %s" % item_id)


def append(state, title, refs, note):
    """Return a copy of ``state`` with one pending item appended."""
    if not title.strip():
        raise QueueError("an item needs a title")
    new = copy.deepcopy(state)
    new["items"].append({
        "id": "Q%02d" % new["next_id"],
        "title": title.strip(),
        "refs": list(refs),
        "status": "pending",
        "note": note,
    })
    new["next_id"] += 1
    return new


def edit(state, item_id, title=None, refs=None, note=None):
    """Return a copy with one item's details changed; position untouched."""
    new = copy.deepcopy(state)
    item = _find(new, item_id)
    if title is not None:
        if not title.strip():
            raise QueueError("an item needs a title")
        item["title"] = title.strip()
    if refs is not None:
        item["refs"] = list(refs)
    if note is not None:
        item["note"] = note
    return new


def transition(state, item_id, action, reason=""):
    """Return a copy with one status transition applied, or refuse."""
    new = copy.deepcopy(state)
    item = _find(new, item_id)
    if action == "start":
        for earlier in new["items"]:
            if earlier is item:
                break
            if earlier["status"] not in ("done", "blocked"):
                raise QueueError(
                    "cannot start %s: earlier item %s is %s (finish it, or "
                    "block it with a reason)" % (item_id, earlier["id"],
                                                  earlier["status"]))
        if item["status"] == "done":
            raise QueueError("%s is already done" % item_id)
        item["status"] = "active"
    elif action == "done":
        if not reason.strip():
            raise QueueError("done requires --evidence (merged PR, exact head)")
        item["status"] = "done"
        item["note"] = reason.strip()
    elif action == "block":
        if not reason.strip():
            raise QueueError("block requires a non-empty --reason")
        item["status"] = "blocked"
        item["note"] = reason.strip()
    elif action == "unblock":
        if item["status"] != "blocked":
            raise QueueError("%s is not blocked" % item_id)
        item["status"] = "pending"
    else:
        raise QueueError("unknown transition %r" % action)
    return new


def empty_state():
    return {"version": 1, "next_id": 1, "items": []}


# --------------------------------------------------------------------------
# Transport
# --------------------------------------------------------------------------


class GitHubTransport:
    """Reads and PATCHes one Issue body via the REST API (urllib only)."""

    def __init__(self, repo, api="https://api.github.com"):
        self.repo = repo
        self.api = api
        self.token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")

    def _request(self, method, number, payload=None):
        url = "%s/repos/%s/issues/%d" % (self.api, self.repo, number)
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("Accept", "application/vnd.github+json")
        request.add_header("Content-Type", "application/json")
        if self.token:
            request.add_header("Authorization", "Bearer " + self.token)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except (urllib.error.URLError, ValueError) as exc:
            raise IOError("GitHub %s issue #%d failed: %s" % (method, number, exc))

    def get_issue(self, number):
        issue = self._request("GET", number)
        return issue.get("body") or "", issue["updated_at"]

    def patch_issue(self, number, body):
        self._request("PATCH", number, {"body": body})


def _mutate(transport, number, change, seed=False):
    """Read, apply ``change``, re-read to detect a race, then PATCH once."""
    body, stamp = transport.get_issue(number)
    if seed:
        if MARKER in body:
            raise QueueError("Issue #%d already holds a queue; init refused" % number)
        state = change(empty_state())
    else:
        state = change(parse(body))
    _validate(state)
    _, fresh = transport.get_issue(number)
    if fresh != stamp:
        raise ConcurrentChangeError(
            "Issue #%d changed since it was read; nothing written, re-run" % number)
    transport.patch_issue(number, render(state))
    return state


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _describe(item):
    refs = ", ".join(item["refs"]) or "no refs"
    text = "%s [%s] %s — %s" % (item["id"], item["status"], item["title"], refs)
    if item["note"]:
        text += "\n    %s" % item["note"]
    return text


def build_parser():
    parser = argparse.ArgumentParser(prog="work_queue", description=__doc__.split("\n")[0])
    parser.add_argument("--issue", type=int,
                        default=int(os.environ.get("AES_QUEUE_ISSUE") or DEFAULT_ISSUE),
                        help="queue Issue number (default: $AES_QUEUE_ISSUE or %d)"
                        % DEFAULT_ISSUE)
    parser.add_argument("--repo", default=os.environ.get("AES_QUEUE_REPO", DEFAULT_REPO))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("show", help="print every item")
    sub.add_parser("next", help="print the next item to work")
    sub.add_parser("init", help="seed an empty queue into a marker-free Issue")
    add = sub.add_parser("add", help="append an item to the end")
    add.add_argument("--title", required=True)
    add.add_argument("--ref", action="append", default=[])
    add.add_argument("--note", default="")
    ed = sub.add_parser("edit", help="change an item's details (never its position)")
    ed.add_argument("id")
    ed.add_argument("--title")
    ed.add_argument("--ref", action="append")
    ed.add_argument("--note")
    for name in ("start", "unblock"):
        sub.add_parser(name).add_argument("id")
    done = sub.add_parser("done")
    done.add_argument("id")
    done.add_argument("--evidence", required=True)
    block = sub.add_parser("block")
    block.add_argument("id")
    block.add_argument("--reason", required=True)
    return parser


def main(argv=None, transport=None):
    args = build_parser().parse_args(argv)
    if args.issue < 1:
        print("error: --issue must be a positive Issue number", file=sys.stderr)
        return EXIT_REFUSED
    transport = transport or GitHubTransport(args.repo)
    try:
        if args.command in ("show", "next"):
            state = parse(transport.get_issue(args.issue)[0])
            if args.command == "show":
                for item in state["items"]:
                    print(_describe(item))
                return EXIT_OK
            item = next_item(state)
            if item is None:
                print("QUEUE EMPTY")
                return EXIT_EMPTY
            print(_describe(item))
            return EXIT_OK
        if args.command == "init":
            _mutate(transport, args.issue, lambda s: s, seed=True)
        elif args.command == "add":
            state = _mutate(transport, args.issue,
                            lambda s: append(s, args.title, args.ref, args.note))
            print("appended %s" % state["items"][-1]["id"])
        elif args.command == "edit":
            _mutate(transport, args.issue,
                    lambda s: edit(s, args.id, args.title, args.ref, args.note))
        else:
            reason = getattr(args, "evidence", None) or getattr(args, "reason", None) or ""
            _mutate(transport, args.issue,
                    lambda s: transition(s, args.id, args.command, reason))
        print("ok")
        return EXIT_OK
    except QueueFormatError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return EXIT_FORMAT
    except ConcurrentChangeError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return EXIT_CONFLICT
    except QueueError as exc:
        print("refused: %s" % exc, file=sys.stderr)
        return EXIT_REFUSED
    except (IOError, KeyError) as exc:
        print("error: transport: %s" % exc, file=sys.stderr)
        return EXIT_TRANSPORT


if __name__ == "__main__":
    sys.exit(main())
