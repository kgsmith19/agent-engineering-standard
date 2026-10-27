#!/usr/bin/env python3
"""work_queue — one durable, ordered execution queue for every session.

Cloud agent containers are ephemeral, so the order in which work across
repositories is executed must live somewhere every fresh session in every
harness can read. The queue is an ordering of Issue references plus a
per-item status. It tracks no intent, criteria, or evidence of its own
(those stay on Issues and pull requests), so it is not a second work
tracker. Standard library only (Python 3.9+).

Queue v2 (#283) keeps the rules in ``queue_core`` (portable, pure) and
storage in ``queue_store`` adapters, selected by one value:
``--backend`` / ``AES_QUEUE_BACKEND`` = ``github-issue`` (default; Issue
``--issue``/``AES_QUEUE_ISSUE`` in ``--repo``/``AES_QUEUE_REPO``) or
``git-file`` (directory ``--path``/``AES_QUEUE_PATH``, default
``.queue``). A v1 Issue (marker
``<!-- agent-engineering-standard:queue:v1 -->``) is still served by the
v1 code below, unchanged, until it is migrated.

Subcommands
===========

``show`` / ``next``            every item / the item to work now
``add --title T [--ref R]... [--note N] [--depends-on ID]...``  append
``edit ID [--title] [--ref]... [--note] [--depends-on ID]... [--clear-depends-on]``
                               change details, never position
``start ID`` / ``done ID --evidence E`` / ``block ID --reason R`` /
``unblock ID``                 status transitions (done archives)
``move ID --after ID|--before ID --authorized-by OWNER --reason R``
                               the only reorder; owner-only and logged
``history [ID]``               the hash-chained event history
``handoff show`` / ``handoff set --file PATH|-``   the session handoff
``export [--out F]`` / ``import --file F``          lossless bundles
``init [--owner LOGIN]``       create an empty v2 queue in an empty backend
``migrate [--dry-run] [--owner LOGIN]``  v1 Issue + handoff comment -> v2,
                               losslessly (the dry run writes nothing)
``guard --claim OWNER/REPO#N`` / ``guard --pr-event PATH``
                               read-only: exit 1 when a claim or a PR does not
                               match the queue (owner:queue-exempt aside)

History records who (``AES_QUEUE_ACTOR``, else ``GITHUB_ACTOR``/``USER``),
when, the harness (``AES_QUEUE_HARNESS``, else detected) and the provider
(``AES_QUEUE_PROVIDER``, else implied by the harness).
Authentication for GitHub: ``GITHUB_TOKEN``/``GH_TOKEN`` when set;
otherwise the request is sent unauthenticated for a harness proxy to
authorize.

Exit codes: 0 ok, 1 refused by a rule, 2 malformed queue or history,
3 queue empty (``next``) or no handoff, 4 concurrent change, 5 transport
failure.
"""

from __future__ import annotations

import argparse
import copy
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import queue_core as core  # noqa: E402
import queue_store  # noqa: E402

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
    """v1 transport: reads and PATCHes one Issue body via the REST API."""

    def __init__(self, repo, api="https://api.github.com", http=None):
        self.repo = repo
        self.http = http or queue_store._default_http(api)

    def get_issue(self, number):
        issue = self.http("GET", "/repos/%s/issues/%d" % (self.repo, number))
        return issue.get("body") or "", issue["updated_at"]

    def patch_issue(self, number, body):
        self.http("PATCH", "/repos/%s/issues/%d" % (self.repo, number),
                  {"body": body})


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
# Context: who is acting, in which harness, with which provider
# --------------------------------------------------------------------------

# Best-effort detection from variables each harness sets; explicit
# AES_QUEUE_HARNESS / AES_QUEUE_PROVIDER always win (Kilo and any other
# harness set them explicitly).
HARNESS_HINTS = (("CLAUDECODE", "claude-code"), ("GEMINI_CLI", "gemini-cli"),
                 ("CODEX_SANDBOX", "codex"), ("CODEX_MANAGED_BY_NPM", "codex"))
HARNESS_PROVIDER = {"claude-code": "anthropic", "gemini-cli": "gemini",
                    "codex": "openai"}


def detect_context(env, now):
    """The event context for this process: actor, harness, provider, time."""
    harness = env.get("AES_QUEUE_HARNESS") or next(
        (name for var, name in HARNESS_HINTS if env.get(var)), "shell")
    provider = env.get("AES_QUEUE_PROVIDER") or HARNESS_PROVIDER.get(harness,
                                                                      "unknown")
    actor = (env.get("AES_QUEUE_ACTOR") or env.get("GITHUB_ACTOR")
             or env.get("USER") or "unknown")
    return {"actor": actor, "harness": harness, "provider": provider, "at": now}


def _utc_now():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

V1_COMMANDS = ("show", "next", "init", "add", "edit", "start", "unblock",
               "done", "block")
BACKENDS = ("github-issue", "git-file")
HANDOFF_V1_MARKER = "<!-- agent-engineering-standard:handoff:v1 -->"
MIGRATE_HINT = ("holds a v1 queue; this needs v2, so migrate it first "
                "(phase 2, kgsmith19/agent-engineering-standard#285)")


def _describe(item):
    refs = ", ".join(item["refs"]) or "no refs"
    text = "%s [%s] %s — %s" % (item["id"], item["status"], item["title"], refs)
    if item.get("depends_on"):
        text += "\n    depends on %s" % ", ".join(item["depends_on"])
    if item["note"]:
        text += "\n    %s" % item["note"]
    return text


def build_parser(env=None):
    env = os.environ if env is None else env
    parser = argparse.ArgumentParser(prog="work_queue", description=__doc__.split("\n")[0])
    parser.add_argument("--backend", default=None,
                        help="storage backend: %s (default: $AES_QUEUE_BACKEND "
                        "or github-issue)" % ", ".join(BACKENDS))
    parser.add_argument("--issue", type=int,
                        default=int(env.get("AES_QUEUE_ISSUE") or DEFAULT_ISSUE),
                        help="queue Issue number (default: $AES_QUEUE_ISSUE or %d)"
                        % DEFAULT_ISSUE)
    parser.add_argument("--repo", default=env.get("AES_QUEUE_REPO", DEFAULT_REPO))
    parser.add_argument("--path", default=None,
                        help="git-file directory (default: $AES_QUEUE_PATH or .queue)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("show", help="print every item")
    sub.add_parser("next", help="print the next item to work")
    init = sub.add_parser("init", help="create an empty queue (v2) in an empty backend")
    init.add_argument("--owner", help="the login allowed to reorder "
                      "(default: the --repo owner)")
    add = sub.add_parser("add", help="append an item to the end")
    add.add_argument("--title", required=True)
    add.add_argument("--ref", action="append", default=[])
    add.add_argument("--note", default="")
    add.add_argument("--depends-on", action="append", default=[])
    ed = sub.add_parser("edit", help="change an item's details (never its position)")
    ed.add_argument("id")
    ed.add_argument("--title")
    ed.add_argument("--ref", action="append")
    ed.add_argument("--note")
    ed.add_argument("--depends-on", action="append")
    ed.add_argument("--clear-depends-on", action="store_true")
    for name in ("start", "unblock"):
        sub.add_parser(name).add_argument("id")
    done = sub.add_parser("done")
    done.add_argument("id")
    done.add_argument("--evidence", required=True)
    block = sub.add_parser("block")
    block.add_argument("id")
    block.add_argument("--reason", required=True)
    move = sub.add_parser("move", help="owner-authorized reorder (logged)")
    move.add_argument("id")
    anchor = move.add_mutually_exclusive_group(required=True)
    anchor.add_argument("--after")
    anchor.add_argument("--before")
    move.add_argument("--authorized-by", required=True)
    move.add_argument("--reason", required=True)
    limit = sub.add_parser("limit", help="owner-authorized cap on parallel "
                           "active items, 1-%d (logged)" % core.MAX_PARALLEL)
    limit.add_argument("n", type=int)
    limit.add_argument("--authorized-by", required=True)
    limit.add_argument("--reason", required=True)
    hist = sub.add_parser("history", help="print the hash-chained history")
    hist.add_argument("id", nargs="?")
    handoff = sub.add_parser("handoff", help="show or set the session handoff")
    handoff_sub = handoff.add_subparsers(dest="handoff_command", required=True)
    handoff_sub.add_parser("show")
    handoff_set = handoff_sub.add_parser("set")
    handoff_set.add_argument("--file", required=True, help="path, or - for stdin")
    export = sub.add_parser("export", help="write a lossless export bundle")
    export.add_argument("--out", help="file (default: stdout)")
    imp = sub.add_parser("import", help="load an export bundle into an empty backend")
    imp.add_argument("--file", required=True)
    mig = sub.add_parser("migrate", help="migrate a v1 Issue (and its handoff "
                         "comment) to v2 losslessly")
    mig.add_argument("--dry-run", action="store_true",
                     help="print exactly what would be written; write nothing")
    mig.add_argument("--owner", help="the login allowed to reorder "
                     "(default: the --repo owner)")
    guard = sub.add_parser("guard", help="exit non-zero when work does not match "
                           "the queue (read-only)")
    what = guard.add_mutually_exclusive_group(required=True)
    what.add_argument("--claim", metavar="OWNER/REPO#N",
                      help="refuse claiming an Issue not on the active or next item")
    what.add_argument("--pr-event", metavar="PATH",
                      help="a pull_request event payload ($GITHUB_EVENT_PATH): refuse "
                      "unless every Issue it closes is on an active item")
    return parser


def _main_v1(args, transport):
    """The v1 behaviour, unchanged, for a v1 Issue."""
    if args.command not in V1_COMMANDS or getattr(args, "depends_on", None) \
            or getattr(args, "clear_depends_on", False):
        print("refused: Issue #%d %s" % (args.issue, MIGRATE_HINT), file=sys.stderr)
        return EXIT_REFUSED
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


def _short(value):
    return "-" if value is None else (
        value if isinstance(value, str) else core.canonical(value))


def _read_text(path):
    if path == "-":
        return sys.stdin.read()
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _run_v2(args, adapter, ctx):
    command = args.command
    if command in ("show", "next", "history", "export") or (
            command == "handoff" and args.handoff_command == "show"):
        state, _ = adapter.load()
        if state is None:
            raise core.FormatError("no queue found in the %s backend" % adapter.name)
        if command == "show":
            if core.max_active(state) > 1:
                print("parallel: up to %d active (%d active now)" % (
                    core.max_active(state), len(core.active_items(state))))
            for item in state["items"]:
                print(_describe(item))
            if state["archived"]:
                print("archived: %s" % ", ".join(state["archived"]))
        elif command == "next":
            item = core.upcoming(state)
            if item is None:
                print("QUEUE EMPTY")
                return EXIT_EMPTY
            print(_describe(item))
        elif command == "history":
            for e in core.history(core.chain(adapter.events(), state), args.id):
                print("%d %s %s %s/%s %s %s %s -> %s%s" % (
                    e["seq"], e["at"], e["actor"], e["harness"], e["provider"],
                    e["op"], e["item"] or "-", _short(e["from"]), _short(e["to"]),
                    (" — " + e["reason"]) if e["reason"] else ""))
        elif command == "export":
            text = json.dumps(queue_store.export_bundle(adapter), indent=1,
                              ensure_ascii=False) + "\n"
            if args.out:
                with open(args.out, "w", encoding="utf-8") as handle:
                    handle.write(text)
            else:
                sys.stdout.write(text)
        else:
            text = core.handoff_text(state, core.chain(adapter.events(), state))
            if text is None:
                print("NO HANDOFF")
                return EXIT_EMPTY
            sys.stdout.write(text)
        return EXIT_OK
    if command == "import":
        try:
            bundle = json.loads(_read_text(args.file))
        except ValueError as exc:
            raise core.FormatError("export bundle is not JSON: %s" % exc)
        queue_store.import_bundle(adapter, bundle)
        print("ok")
        return EXIT_OK
    if command == "init":
        owner = args.owner or args.repo.split("/")[0]
        queue_store.commit(adapter, lambda s: core.op_init(owner), ctx, create=True)
        print("ok")
        return EXIT_OK
    if command == "add":
        change = lambda s: core.op_add(s, args.title, args.ref, args.note,  # noqa: E731
                                       args.depends_on)
    elif command == "edit":
        deps = [] if args.clear_depends_on else args.depends_on
        change = lambda s: core.op_edit(s, args.id, args.title, args.ref,  # noqa: E731
                                        args.note, deps)
    elif command == "move":
        change = lambda s: core.op_move(s, args.id, args.after, args.before,  # noqa: E731
                                        args.authorized_by, args.reason)
    elif command == "limit":
        change = lambda s: core.op_limit(s, args.n, args.authorized_by,  # noqa: E731
                                         args.reason)
    elif command == "handoff":
        text = _read_text(args.file)
        change = lambda s: core.op_handoff(s, text)  # noqa: E731
    else:
        reason = getattr(args, "evidence", None) or getattr(args, "reason", None) or ""
        change = lambda s: core.op_transition(s, args.id, command, reason)  # noqa: E731
    state = queue_store.commit(adapter, change, ctx)
    if command == "add":
        print("appended %s" % state["items"][-1]["id"])
    print("ok")
    return EXIT_OK


def _run_migrate(args, adapter, ctx):
    if not isinstance(adapter, queue_store.GitHubIssueAdapter):
        raise core.QueueError("migrate reads a v1 queue, which only exists in "
                              "the github-issue backend")
    owner = args.owner or args.repo.split("/")[0]
    plan = queue_store.migrate_issue(adapter, parse, owner, ctx,
                                     dry_run=args.dry_run,
                                     handoff_marker=HANDOFF_V1_MARKER)
    state, live = plan["state"], [i["id"] for i in plan["state"]["items"]]
    print("migrate: Issue #%d v1 -> v2 (%s)" % (
        args.issue, "dry run, nothing written" if args.dry_run else "written"))
    for item in plan["v1"]["items"]:
        print("%s %s -> %s" % (item["id"], item["status"], "archived"
                               if item["id"] in state["archived"]
                               else "live #%d" % (live.index(item["id"]) + 1)))
    print("lossless: v1 state reconstructs exactly from the migrate event")
    text = plan["handoff_text"]
    if text is None:
        print("handoff: no owner-authored v1 handoff comment found")
    else:
        print("handoff: comment %s, %d chars, sha256 %s" % (
            plan["handoff_comment"], len(text), core.text_digest(text)))
    print("events: %d (seq 1..%d)" % (len(plan["events"]),
                                      state["history"]["seq"]))
    print("--- v2 state ---")
    print(json.dumps(state, indent=1, ensure_ascii=False))
    if text is not None:
        print("--- handoff (%d chars) ---" % len(text))
        print(text)
    print("--- end ---")
    return EXIT_OK


def _timeline(http, repo, number):
    events, page = [], 1
    while True:
        batch = http("GET", "/repos/%s/issues/%d/timeline?per_page=100&page=%d"
                     % (repo, number, page))
        events.extend(batch)
        if len(batch) < 100:
            return events
        page += 1


def _run_guard(args, adapter, http):
    state, _ = adapter.load()
    if state is None:
        raise core.FormatError("no queue found in the %s backend" % adapter.name)
    if args.claim:
        print(core.guard_claim(state, args.claim))
        return EXIT_OK
    try:
        with open(args.pr_event, encoding="utf-8") as handle:
            event = json.load(handle)
        pr, repo = event["pull_request"], event["repository"]["full_name"]
        number = int(pr["number"])
        labels = [label.get("name") for label in pr.get("labels") or []]
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise core.FormatError("not a readable pull_request event: %s" % exc)
    exempt = False
    if core.EXEMPT_LABEL in labels:
        exempt = core.owner_label_authorized(
            _timeline(http or getattr(adapter, "http", None) or queue_store._default_http(),
                      repo, number), core.EXEMPT_LABEL, state["owner"])
        if not exempt:
            print("guard: the %s label is present but was not applied by the owner "
                  "(%s); it is ignored" % (core.EXEMPT_LABEL, state["owner"]),
                  file=sys.stderr)
    print(core.guard_pr(state, core.closing_refs(pr.get("body"), repo), exempt))
    return EXIT_OK


def _adapter_for(args, env, http):
    backend = args.backend or env.get("AES_QUEUE_BACKEND") or "github-issue"
    if backend not in BACKENDS:
        raise core.QueueError("unknown backend %r (choose %s)"
                              % (backend, ", ".join(BACKENDS)))
    if backend == "git-file":
        return queue_store.GitFileAdapter(args.path or env.get("AES_QUEUE_PATH")
                                          or ".queue")
    return queue_store.GitHubIssueAdapter(args.repo, args.issue, http=http)


def main(argv=None, transport=None, adapter=None, http=None, env=None, now=None):
    """Run the CLI. ``transport`` is the v1 API and always runs v1 code;
    ``adapter`` / ``http`` / ``env`` / ``now`` are v2 injection seams."""
    env = os.environ if env is None else env
    args = build_parser(env).parse_args(argv)
    if args.issue < 1:
        print("error: --issue must be a positive Issue number", file=sys.stderr)
        return EXIT_REFUSED
    if transport is not None:
        return _main_v1(args, transport)
    try:
        adapter = adapter or _adapter_for(args, env, http)
        ctx = detect_context(env, now or _utc_now())
        if args.command == "migrate":
            return _run_migrate(args, adapter, ctx)
        if args.command == "guard":
            return _run_guard(args, adapter, http)
        try:
            return _run_v2(args, adapter, ctx)
        except queue_store.LegacyQueueError:
            return _main_v1(args, GitHubTransport(args.repo, http=http))
    except core.FormatError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return EXIT_FORMAT
    except queue_store.ConflictError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return EXIT_CONFLICT
    except core.QueueError as exc:
        print("refused: %s" % exc, file=sys.stderr)
        return EXIT_REFUSED
    except (IOError, OSError, KeyError) as exc:
        print("error: transport: %s" % exc, file=sys.stderr)
        return EXIT_TRANSPORT


if __name__ == "__main__":
    sys.exit(main())
