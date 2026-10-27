"""queue_core — the v2 execution-queue rules, pure and portable.

Phase 1 of #283. Standard library only, with no harness, provider,
transport or clock code: callers pass state in and get state back, so the
same rules run under any harness, any model provider and any storage
backend (see ``queue_store``). ``queue_v2.schema.json`` describes the
state; ``validate`` enforces it plus the rules a schema cannot express.

State (version 2)::

    {"version": 2, "owner": "kgsmith19", "next_id": 4,
     "items": [{"id": "Q03", "title": "...", "refs": ["o/r#1"],
                "status": "pending", "note": "", "depends_on": ["Q02"]}],
     "archived": ["Q01"],
     "history": {"seq": 7, "head": "<sha256 of event 7>"},
     "handoff": {"seq": 6, "sha256": "<sha256 of the text>"} | null}

Rules
=====

* Order changes only through ``op_move``, which needs the recorded owner
  as ``authorized_by`` plus a reason. ``op_add`` appends; ids are never
  reused.
* ``depends_on`` names earlier or archived items only, so dependencies
  never contradict the order and cannot form a cycle. ``op_transition``
  refuses to start an item with an unmet dependency; ``next_item`` skips
  an item waiting on one.
* ``done`` archives the item: it leaves live state, its id joins
  ``archived`` (so dependents resolve), and its record goes to history.
* Every operation returns ``(new_state, events)``; ``seal`` stamps each
  event with who/when/harness/provider, chains it to the previous event
  by sha256, and advances ``history``. ``chain`` walks back from the
  committed head, so orphaned, junk or forged events are ignored and a
  missing or altered one fails closed.
* At most ``max_active`` items are active at once (optional state key,
  absent means 1, owner-set through ``op_limit`` up to ``MAX_PARALLEL``,
  #302). Claims stay in queue order: a later item starts only when every
  earlier live item is active, blocked or waiting on a dependency.
* The handoff text is stored in its ``handoff`` event; state holds its
  digest. Text that looks like a credential is refused everywhere, and
  a state larger than ``STATE_BUDGET`` is refused rather than truncated.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re

VERSION = 2
MARKER = "<!-- agent-engineering-standard:queue:v2 -->"
STATUSES = ("pending", "active", "blocked")
LIMITS = {"title": 200, "note": 600, "refs": 12, "ref": 120,
          "reason": 600, "handoff": 40000}
# Canonical state bytes; well below GitHub's 65,536-character Issue body
# once the human checklist is rendered alongside it.
STATE_BUDGET = 24576

STATE_KEYS = ("version", "owner", "next_id", "items", "archived",
              "history", "handoff")
OPTIONAL_STATE_KEYS = ("max_active",)
# Owner ceiling for parallel active items (owner authorization, 2026-10-27, #302).
MAX_PARALLEL = 5
ITEM_KEYS = ("id", "title", "refs", "status", "note", "depends_on")
EVENT_KEYS = ("op", "item", "from", "to", "reason", "seq", "prev", "at",
              "actor", "harness", "provider", "hash")
CONTEXT_KEYS = ("actor", "harness", "provider", "at")

_ID = re.compile(r"^Q[0-9]{2,6}$")
_OWNER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_HEX = re.compile(r"^[0-9a-f]{64}$")
_AT = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_BLOCK = re.compile(re.escape(MARKER) + r"\s*```json\s*\n(.*?)\n```", re.S)
SECRET_PATTERNS = (
    re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{22,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"xox[abprs]-[A-Za-z0-9-]{10,}"),
)

_BADGE = {"pending": "⏳ pending", "active": "🔨 active",
          "blocked": "⛔ blocked"}
HEADER = """## 📋 Execution Queue

Ordered queue of work across the owner's repositories (queue v2). **Order \
is binding**: work the first item that is neither blocked nor waiting on a \
dependency; up to the owner-set cap of items may be active at once, started \
in this order. Only the owner reorders, through `work_queue.py move`, and every \
change is a hash-chained history event (`work_queue.py history`). The JSON \
block below is the source of truth; this checklist is regenerated from it \
on every write.
"""


class QueueError(Exception):
    """An operation was refused by a queue rule."""


class FormatError(QueueError):
    """Stored state or history is malformed; nothing may be written."""


class HistoryError(FormatError):
    """The history does not chain to the committed head."""


class BudgetError(QueueError):
    """A write would exceed a size budget; it is refused, never truncated."""


class SecretError(QueueError):
    """Text that looks like a credential was refused."""


# --------------------------------------------------------------------------
# Encoding and validation
# --------------------------------------------------------------------------


def canonical(value):
    """Deterministic JSON used for hashing."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True)


def size(state):
    """Stored size of ``state`` in UTF-8 bytes (the budgeted quantity)."""
    return len(json.dumps(state, separators=(",", ":"),
                          ensure_ascii=False).encode("utf-8"))


def event_hash(event):
    body = {key: value for key, value in event.items() if key != "hash"}
    return hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()


def text_digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _fail(message):
    raise FormatError(message)


def _id_list(value, label):
    if not isinstance(value, list) or not all(
            isinstance(v, str) and _ID.match(v) for v in value):
        _fail("%s must be a list of item ids" % label)
    if len(set(value)) != len(value):
        _fail("%s holds a duplicate id" % label)


def _dependency_problem(items, archived):
    """Message for the first dependency that is not earlier or archived."""
    seen = set(archived)
    for item in items:
        for dep in item["depends_on"]:
            if dep == item["id"]:
                return "%s cannot depend on itself" % dep
            if dep not in seen:
                return ("%s depends on %s, which is not an earlier or "
                        "archived item" % (item["id"], dep))
        seen.add(item["id"])
    return None


def _validate_item(item, next_id):
    if not isinstance(item, dict) or set(item) != set(ITEM_KEYS):
        _fail("queue item must hold exactly %s" % ", ".join(ITEM_KEYS))
    if not isinstance(item["id"], str) or not _ID.match(item["id"]):
        _fail("bad item id %r" % (item["id"],))
    if int(item["id"][1:]) >= next_id:
        _fail("item %s is not below next_id %d" % (item["id"], next_id))
    title = item["title"]
    if not isinstance(title, str) or not title.strip() or len(title) > LIMITS["title"]:
        _fail("item %s: title must be 1-%d characters" % (item["id"], LIMITS["title"]))
    refs = item["refs"]
    if not isinstance(refs, list) or len(refs) > LIMITS["refs"] or not all(
            isinstance(r, str) and 0 < len(r) <= LIMITS["ref"] for r in refs):
        _fail("item %s: refs must be at most %d strings of 1-%d characters"
              % (item["id"], LIMITS["refs"], LIMITS["ref"]))
    if item["status"] not in STATUSES:
        _fail("item %s: unknown status %r" % (item["id"], item["status"]))
    if not isinstance(item["note"], str) or len(item["note"]) > LIMITS["note"]:
        _fail("item %s: note must be at most %d characters"
              % (item["id"], LIMITS["note"]))
    _id_list(item["depends_on"], "item %s depends_on" % item["id"])


def validate(state):
    """Fail closed unless ``state`` is a well-formed v2 queue."""
    if (not isinstance(state, dict) or not set(STATE_KEYS) <= set(state)
            or set(state) - set(STATE_KEYS) - set(OPTIONAL_STATE_KEYS)):
        _fail("queue must be an object holding exactly %s (optionally %s)"
              % (", ".join(STATE_KEYS), ", ".join(OPTIONAL_STATE_KEYS)))
    if "max_active" in state and not (
            _is_int(state["max_active"]) and 1 <= state["max_active"] <= MAX_PARALLEL):
        _fail("max_active must be an integer from 1 to %d" % MAX_PARALLEL)
    if state["version"] != VERSION or not _is_int(state["version"]):
        _fail("queue version must be %d" % VERSION)
    if not isinstance(state["owner"], str) or not _OWNER.match(state["owner"]):
        _fail("queue owner must be a login")
    next_id = state["next_id"]
    if not _is_int(next_id) or next_id < 1:
        _fail("next_id must be a positive integer")
    if not isinstance(state["items"], list):
        _fail("queue items must be a list")
    for item in state["items"]:
        _validate_item(item, next_id)
    _id_list(state["archived"], "archived")
    live = [item["id"] for item in state["items"]]
    if len(set(live)) != len(live):
        _fail("duplicate item id")
    if set(live) & set(state["archived"]):
        _fail("an item is both live and archived")
    if any(int(i[1:]) >= next_id for i in state["archived"]):
        _fail("an archived id is not below next_id")
    problem = _dependency_problem(state["items"], state["archived"])
    if problem:
        _fail(problem)
    history = state["history"]
    if not isinstance(history, dict) or set(history) != {"seq", "head"}:
        _fail("history must hold exactly seq and head")
    if not _is_int(history["seq"]) or history["seq"] < 0:
        _fail("history seq must be a non-negative integer")
    head = history["head"]
    if head is not None and not (isinstance(head, str) and _HEX.match(head)):
        _fail("history head must be a sha256 hex digest or null")
    if (history["seq"] == 0) != (head is None):
        _fail("history head is null exactly when seq is 0")
    handoff = state["handoff"]
    if handoff is not None:
        if (not isinstance(handoff, dict) or set(handoff) != {"seq", "sha256"}
                or not _is_int(handoff["seq"]) or handoff["seq"] < 1
                or not isinstance(handoff["sha256"], str)
                or not _HEX.match(handoff["sha256"])):
            _fail("handoff must be null or hold exactly seq and sha256")
        if handoff["seq"] > history["seq"]:
            _fail("handoff seq is beyond the history head")


# --------------------------------------------------------------------------
# Queries
# --------------------------------------------------------------------------


def find(state, item_id):
    for item in state["items"]:
        if item["id"] == item_id:
            return item
    if item_id in state["archived"]:
        raise QueueError("%s is done and archived" % item_id)
    raise QueueError("no queue item %s" % item_id)


def waiting_on(state, item):
    """Dependencies of ``item`` that are not done (archived) yet."""
    return [dep for dep in item["depends_on"] if dep not in state["archived"]]


def next_item(state):
    """First pending or active item with every dependency met, or None."""
    for item in state["items"]:
        if item["status"] in ("pending", "active") and not waiting_on(state, item):
            return item
    return None


def max_active(state):
    """How many items may be active at once (absent means 1)."""
    return state.get("max_active", 1)


def active_items(state):
    return [item for item in state["items"] if item["status"] == "active"]


def next_startable(state):
    """First pending item with every dependency met: the next one to start."""
    for item in state["items"]:
        if item["status"] == "pending" and not waiting_on(state, item):
            return item
    return None


def upcoming(state):
    """The item to work next: the next one to start while the cap has room,
    otherwise (and always under a cap of 1) ``next_item``."""
    if max_active(state) > 1 and len(active_items(state)) < max_active(state):
        return next_startable(state) or next_item(state)
    return next_item(state)


def history(events, item_id=None):
    """Committed events, optionally only those about ``item_id``."""
    return [e for e in events if item_id is None or e["item"] == item_id]


# --------------------------------------------------------------------------
# Operations: each returns (new_state, unsealed events) and never mutates
# --------------------------------------------------------------------------


def _event(op, item, before, after, reason=""):
    return {"op": op, "item": item, "from": before, "to": after,
            "reason": reason}


def _text(value, label, limit, required=True):
    if not isinstance(value, str):
        raise QueueError("%s must be text" % label)
    value = value.strip()
    if required and not value:
        raise QueueError("%s must not be empty" % label)
    if len(value) > limit:
        raise QueueError("%s is longer than %d characters" % (label, limit))
    if _CONTROL.search(value) or "<!--" in value:
        raise QueueError("%s must be one line without HTML comments" % label)
    return value


def _refs(refs):
    refs = [_text(r, "ref", LIMITS["ref"]) for r in refs]
    if len(refs) > LIMITS["refs"]:
        raise QueueError("at most %d refs per item" % LIMITS["refs"])
    return refs


def _deps(state, item_id, deps):
    deps = list(deps)
    if len(set(deps)) != len(deps):
        raise QueueError("depends_on holds a duplicate")
    earlier = set(state["archived"])
    for item in state["items"]:
        if item["id"] == item_id:
            break
        earlier.add(item["id"])
    for dep in deps:
        if dep == item_id:
            raise QueueError("%s cannot depend on itself" % dep)
        if dep not in earlier:
            raise QueueError("%s must depend on earlier or archived items; "
                             "%s is not one" % (item_id, dep))
    return deps


def op_init(owner):
    if not isinstance(owner, str) or not _OWNER.match(owner):
        raise QueueError("queue owner must be a login, got %r" % (owner,))
    state = {"version": VERSION, "owner": owner, "next_id": 1, "items": [],
             "archived": [], "history": {"seq": 0, "head": None},
             "handoff": None}
    return state, [_event("init", None, None, {"owner": owner})]


def op_add(state, title, refs=(), note="", depends_on=()):
    new = copy.deepcopy(state)
    item_id = "Q%02d" % new["next_id"]
    item = {"id": item_id,
            "title": _text(title, "title", LIMITS["title"]),
            "refs": _refs(refs),
            "status": "pending",
            "note": _text(note, "note", LIMITS["note"], required=False),
            "depends_on": _deps(new, item_id, depends_on)}
    new["items"].append(item)
    new["next_id"] += 1
    return new, [_event("add", item_id, None, copy.deepcopy(item))]


def op_edit(state, item_id, title=None, refs=None, note=None, depends_on=None):
    """Change an item's details; its position never changes."""
    new = copy.deepcopy(state)
    item = find(new, item_id)
    proposed = {}
    if title is not None:
        proposed["title"] = _text(title, "title", LIMITS["title"])
    if refs is not None:
        proposed["refs"] = _refs(refs)
    if note is not None:
        proposed["note"] = _text(note, "note", LIMITS["note"], required=False)
    if depends_on is not None:
        proposed["depends_on"] = _deps(new, item_id, depends_on)
    changed = {k: v for k, v in proposed.items() if item[k] != v}
    if not changed:
        raise QueueError("edit %s changes nothing" % item_id)
    before = {k: copy.deepcopy(item[k]) for k in changed}
    item.update(copy.deepcopy(changed))
    return new, [_event("edit", item_id, before, changed)]


def op_transition(state, item_id, action, reason=""):
    """start / block / unblock / done (done archives the item)."""
    new = copy.deepcopy(state)
    if action not in ("start", "block", "unblock", "done"):
        raise QueueError("unknown transition %r" % action)
    item = find(new, item_id)
    status = item["status"]
    if action == "start":
        if status != "pending":
            raise QueueError("cannot start %s: it is %s%s" % (
                item_id, status,
                " (unblock it first)" if status == "blocked" else ""))
        cap = max_active(new)
        for earlier in new["items"]:
            if earlier is item:
                break
            if earlier["status"] == "blocked" or waiting_on(new, earlier):
                continue
            if earlier["status"] == "active" and cap > 1:
                continue
            raise QueueError(
                "cannot start %s: earlier item %s is %s (finish it, or "
                "block it with a reason)" % (item_id, earlier["id"],
                                              earlier["status"]))
        running = active_items(new)
        if len(running) >= cap:
            raise QueueError(
                "cannot start %s: %d of %d allowed items are already active (%s); "
                "finish one first, or ask the owner to raise the cap with "
                "`limit`" % (item_id, len(running), cap,
                             ", ".join(i["id"] for i in running)))
        unmet = waiting_on(new, item)
        if unmet:
            raise QueueError("cannot start %s: it depends on %s, not done yet"
                             % (item_id, ", ".join(unmet)))
        item["status"] = "active"
        return new, [_event("start", item_id, status, "active")]
    if action == "block":
        reason = _text(reason, "block reason", LIMITS["reason"])
        if status == "blocked":
            raise QueueError("%s is already blocked" % item_id)
        item["status"] = "blocked"
        item["note"] = reason[:LIMITS["note"]]
        return new, [_event("block", item_id, status, "blocked", reason)]
    if action == "unblock":
        if status != "blocked":
            raise QueueError("%s is not blocked" % item_id)
        item["status"] = "pending"
        return new, [_event("unblock", item_id, status, "pending")]
    reason = _text(reason, "done evidence (merged PR, exact head)",
                   LIMITS["reason"])
    if status == "pending":
        raise QueueError("cannot finish %s: it was never started" % item_id)
    record = copy.deepcopy(item)
    new["items"].remove(item)
    new["archived"].append(item_id)
    return new, [_event("done", item_id, status, "done", reason),
                 _event("archive", item_id, record, "archived")]


def op_move(state, item_id, after=None, before=None, authorized_by="",
            reason=""):
    """The only reorder: owner-authorized, reasoned, and logged."""
    if authorized_by != state["owner"]:
        raise QueueError("move needs --authorized-by %s (the queue owner); "
                         "an agent cannot reorder on its own authority"
                         % state["owner"])
    reason = _text(reason, "move reason", LIMITS["reason"])
    if (after is None) == (before is None):
        raise QueueError("move needs exactly one of --after or --before")
    anchor = after if after is not None else before
    new = copy.deepcopy(state)
    item = find(new, item_id)
    if anchor == item_id:
        raise QueueError("cannot move %s relative to itself" % item_id)
    find(new, anchor)
    order = [i["id"] for i in new["items"]]
    old_after = order[order.index(item_id) - 1] if order.index(item_id) else None
    new["items"].remove(item)
    index = [i["id"] for i in new["items"]].index(anchor)
    new["items"].insert(index + 1 if after is not None else index, item)
    reordered = [i["id"] for i in new["items"]]
    if reordered == order:
        raise QueueError("move %s has no effect" % item_id)
    problem = _dependency_problem(new["items"], new["archived"])
    if problem:
        raise QueueError("move refused: %s" % problem)
    position = reordered.index(item_id)
    new_after = reordered[position - 1] if position else None
    return new, [_event("move", item_id, {"after": old_after},
                        {"after": new_after, "authorized_by": authorized_by},
                        reason)]


def op_limit(state, n, authorized_by="", reason=""):
    """Owner-authorized change to how many items may be active at once."""
    if authorized_by != state["owner"]:
        raise QueueError("limit needs --authorized-by %s (the queue owner); "
                         "an agent cannot raise its own concurrency"
                         % state["owner"])
    reason = _text(reason, "limit reason", LIMITS["reason"])
    if not _is_int(n) or not 1 <= n <= MAX_PARALLEL:
        raise QueueError("limit must be an integer from 1 to %d, got %r"
                         % (MAX_PARALLEL, n))
    before = max_active(state)
    if n == before:
        raise QueueError("limit is already %d" % n)
    running = len(active_items(state))
    if n < running:
        raise QueueError("cannot lower the limit to %d: %d items are active; "
                         "finish or block some first" % (n, running))
    new = copy.deepcopy(state)
    new["max_active"] = n
    return new, [_event("limit", None, before,
                        {"max_active": n, "authorized_by": authorized_by}, reason)]


def op_handoff(state, text):
    if not isinstance(text, str) or not text.strip():
        raise QueueError("handoff text must not be empty")
    if len(text) > LIMITS["handoff"]:
        raise QueueError("handoff is longer than %d characters" % LIMITS["handoff"])
    previous = state["handoff"]["sha256"] if state["handoff"] else None
    event = _event("handoff", None, previous,
                   {"sha256": text_digest(text), "chars": len(text)})
    event["text"] = text
    return copy.deepcopy(state), [event]


def _exact(value, label, limit, required=True):
    """``_text`` that refuses rather than alters: migration must be lossless."""
    if _text(value, label, limit, required) != value:
        raise QueueError("%s has surrounding whitespace" % label)
    return value


def op_migrate(v1, owner):
    """A v1 queue as v2 state. Done items are archived with their records,
    and the ``migrate`` event holds the whole v1 state verbatim, so the
    history alone reconstructs it (``v1_from_history``)."""
    if not isinstance(v1, dict) or v1.get("version") != 1:
        raise FormatError("migrate needs a version 1 queue")
    state, _ = op_init(owner)
    state["next_id"] = v1["next_id"]
    events = [_event("migrate", None, copy.deepcopy(v1),
                     {"version": VERSION, "owner": owner}, "v1 -> v2")]
    for item in v1["items"]:
        label = "cannot migrate %s:" % item["id"]
        if not _ID.match(item["id"]):
            raise QueueError("%s its id is not a v2 id" % label)
        if item["status"] == "done":
            state["archived"].append(item["id"])
            events.append(_event("archive", item["id"], copy.deepcopy(item),
                                 "archived"))
            continue
        state["items"].append({
            "id": item["id"],
            "title": _exact(item["title"], label + " title", LIMITS["title"]),
            "refs": [_exact(r, label + " ref", LIMITS["ref"]) for r in item["refs"]],
            "status": item["status"],
            "note": _exact(item["note"], label + " note", LIMITS["note"],
                           required=False),
            "depends_on": []})
        if len(item["refs"]) > LIMITS["refs"]:
            raise QueueError("%s more than %d refs" % (label, LIMITS["refs"]))
    return state, events


def v1_from_history(events):
    """The v1 state a migrated queue started from, from its history."""
    found = [e for e in events if e["op"] == "migrate"]
    if len(found) != 1:
        raise HistoryError("history holds %d migrate events, want 1" % len(found))
    return copy.deepcopy(found[0]["from"])


def check_migration(v1, state, events):
    """Fail closed unless ``state`` + history are exactly ``v1`` in v2 form."""
    if v1_from_history(chain(events, state)) != v1:
        raise FormatError("history does not reconstruct the v1 queue exactly")
    live = [dict(item, depends_on=[]) for item in v1["items"]
            if item["status"] != "done"]
    done = [item["id"] for item in v1["items"] if item["status"] == "done"]
    if state["items"] != live or state["archived"] != done \
            or state["next_id"] != v1["next_id"]:
        raise FormatError("migrated state does not mirror the v1 queue")


# --------------------------------------------------------------------------
# Sealing and history
# --------------------------------------------------------------------------


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, inner in value.items():
            yield key
            yield from _strings(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from _strings(inner)


def scan_secrets(value):
    """Refuse when any string in ``value`` looks like a credential."""
    for text in _strings(value):
        for number, pattern in enumerate(SECRET_PATTERNS, start=1):
            if pattern.search(text):
                raise SecretError(
                    "text looks like a credential (pattern %d); queue state "
                    "and history are published, so remove it" % number)


def _check_context(ctx):
    if not isinstance(ctx, dict):
        raise QueueError("event context must be an object")
    for key in CONTEXT_KEYS:
        value = ctx.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > 120 \
                or _CONTROL.search(value):
            raise QueueError("event context %s must be one line of text" % key)
    if not _AT.match(ctx["at"]):
        raise QueueError("event time must be UTC YYYY-MM-DDTHH:MM:SSZ")


def seal(state, events, ctx):
    """Stamp, hash-chain and commit ``events`` onto ``state``."""
    _check_context(ctx)
    new = copy.deepcopy(state)
    seq, head = new["history"]["seq"], new["history"]["head"]
    sealed = []
    for event in events:
        event = copy.deepcopy(event)
        seq += 1
        event.update({"seq": seq, "prev": head, "at": ctx["at"],
                      "actor": ctx["actor"], "harness": ctx["harness"],
                      "provider": ctx["provider"]})
        event["hash"] = event_hash(event)
        head = event["hash"]
        if event["op"] == "handoff":
            new["handoff"] = {"seq": seq, "sha256": event["to"]["sha256"]}
        sealed.append(event)
    new["history"] = {"seq": seq, "head": head}
    scan_secrets(new)
    scan_secrets(sealed)
    validate(new)
    if size(new) > STATE_BUDGET:
        raise BudgetError("queue state would be %d bytes, over the %d-byte "
                          "budget; nothing written" % (size(new), STATE_BUDGET))
    return new, sealed


def _well_formed_event(event):
    if not isinstance(event, dict):
        return False
    keys = set(event)
    if not set(EVENT_KEYS) <= keys or keys - set(EVENT_KEYS) - {"text"}:
        return False
    if not _is_int(event["seq"]) or event["seq"] < 1:
        return False
    if not isinstance(event["hash"], str) or not _HEX.match(event["hash"]):
        return False
    try:
        return event_hash(event) == event["hash"]
    except (TypeError, ValueError):
        return False


def chain(events, state):
    """The committed history, oldest first, walked back from the head.

    Events no committed head reaches (a lost compare-and-swap, junk,
    forgeries) are ignored; a missing or altered link fails closed.
    """
    by_hash = {}
    for event in events:
        if _well_formed_event(event):
            by_hash[event["hash"]] = event
    head, seq = state["history"]["head"], state["history"]["seq"]
    walked = []
    while head is not None:
        event = by_hash.get(head)
        if event is None:
            raise HistoryError("history is missing event %d (%s...)"
                               % (seq, head[:12]))
        if event["seq"] != seq:
            raise HistoryError("history event %s... has seq %r, want %d"
                               % (head[:12], event["seq"], seq))
        walked.append(event)
        head, seq = event["prev"], seq - 1
    if seq != 0:
        raise HistoryError("history ends at seq %d instead of 1" % (seq + 1))
    walked.reverse()
    return walked


def handoff_text(state, events):
    """The committed handoff text, verified against its digest, or None."""
    pointer = state["handoff"]
    if pointer is None:
        return None
    for event in events:
        if event["seq"] == pointer["seq"] and event["op"] == "handoff":
            text = event.get("text")
            if not isinstance(text, str) or text_digest(text) != pointer["sha256"] \
                    or event["to"].get("sha256") != pointer["sha256"]:
                raise HistoryError("handoff text does not match its digest")
            return text
    raise HistoryError("handoff event %d is not in history" % pointer["seq"])


# --------------------------------------------------------------------------
# Guard: is this claim or pull request queue work? (#287)
# --------------------------------------------------------------------------

EXEMPT_LABEL = "owner:queue-exempt"
_REF = re.compile(r"^(?:([A-Za-z0-9][A-Za-z0-9._-]*)/([A-Za-z0-9._-]+))?#([1-9][0-9]*)$")
_CLOSING = re.compile(r"(?i)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+"
                      r"((?:[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9._-]+)?#[1-9][0-9]*)\b")


def normalize_ref(ref, default_repo=None):
    """``owner/repo#N`` in lower case; ``#N`` needs ``default_repo``."""
    match = _REF.match((ref or "").strip())
    if not match or (not match.group(1) and not default_repo):
        raise QueueError("not an Issue reference: %r (want owner/repo#N)" % (ref,))
    repo = "%s/%s" % match.group(1, 2) if match.group(1) else default_repo
    return "%s#%s" % (repo.lower(), match.group(3))


def closing_refs(body, repo):
    """Issues a PR body closes (GitHub's closing keywords), in order, once each."""
    refs = []
    for raw in _CLOSING.findall(body or ""):
        ref = normalize_ref(raw, repo)
        if ref not in refs:
            refs.append(ref)
    return refs


def owner_label_authorized(events, label, owner):
    """True iff the latest ``labeled`` event for ``label`` is by ``owner`` and
    no later ``unlabeled`` removed it. Mirrors standardctl.owner_label_authorized
    (a test holds them equal), so queue guard and merge policy share one rule."""
    authorized = False
    for event in events:
        label_obj = event.get("label") or {}
        name = (label_obj.get("name") if isinstance(label_obj, dict) else None) \
            or event.get("label_name")
        if name != label:
            continue
        if event.get("event") == "labeled":
            actor = event.get("actor") or {}
            login = (actor.get("login") if isinstance(actor, dict) else None) \
                or event.get("actor_login")
            authorized = login == owner
        elif event.get("event") == "unlabeled":
            authorized = False
    return authorized


def _item_refs(item):
    return {normalize_ref(ref) for ref in item["refs"] if _REF.match(ref.strip())
            and "/" in ref}


def _queue_position(state):
    return active_items(state), upcoming(state)


def guard_claim(state, ref):
    """Claiming ``ref`` is allowed only for an active item or the next item."""
    ref = normalize_ref(ref)
    active, upcoming = _queue_position(state)
    for item in active + ([upcoming] if upcoming else []):
        if ref in _item_refs(item):
            return "guard: ok, %s is on %s (%s)" % (ref, item["id"], item["status"])
    names = ", ".join(i["id"] for i in active) or "none"
    raise QueueError(
        "guard: claim of %s refused, it is not on the active or next queue item "
        "(active: %s, next: %s). Work the queue in order; only the owner adds or "
        "moves items." % (ref, names, upcoming["id"] if upcoming else "none"))


def guard_pr(state, refs, exempt):
    """A PR passes only if every Issue it closes is on an active item, or the
    owner exempted it with ``EXEMPT_LABEL``."""
    if exempt:
        return "guard: ok, exempt by the owner's %s label" % EXEMPT_LABEL
    if not refs:
        raise QueueError("guard: this PR closes no Issue, so it cannot be matched "
                         "to the queue")
    active, _ = _queue_position(state)
    owned = {}
    for item in active:
        for ref in _item_refs(item):
            owned[ref] = item["id"]
    off = [ref for ref in refs if ref not in owned]
    if off:
        raise QueueError(
            "guard: %s not on an active queue item (active: %s). Claim it through "
            "the queue first, or ask the owner for the %s label."
            % (", ".join(off) + (" is" if len(off) == 1 else " are"),
               ", ".join(i["id"] for i in active) or "none", EXEMPT_LABEL))
    return "guard: ok, %s on %s" % (", ".join(refs), ", ".join(sorted(set(owned[r] for r in refs))))


# --------------------------------------------------------------------------
# Markdown rendering (used by document-style backends such as an Issue)
# --------------------------------------------------------------------------


def render_markdown(state):
    """Human checklist followed by the marker and the JSON source of truth."""
    lines = [HEADER]
    if max_active(state) > 1:
        lines.append("**Parallel: up to %d active (%d active now).** The owner "
                     "sets this with `work_queue.py limit`.\n"
                     % (max_active(state), len(active_items(state))))
    following = upcoming(state)
    for item in state["items"]:
        refs = ", ".join(item["refs"]) or "no refs"
        line = "- [ ] **%s** %s — %s · %s" % (item["id"], item["title"], refs,
                                             _BADGE[item["status"]])
        if following is not None and item["id"] == following["id"]:
            line += " · 👉 **NEXT**"
        if item["depends_on"]:
            line += "\n  - depends on %s" % ", ".join(item["depends_on"])
        if item["note"]:
            line += "\n  - %s" % item["note"]
        lines.append(line)
    if not state["items"]:
        lines.append("_Queue is empty._")
    if state["archived"]:
        lines.append("")
        lines.append("✅ **Done and archived:** %s. `work_queue.py history <id>` "
                     "shows each item's evidence." % ", ".join(state["archived"]))
    if state["handoff"]:
        lines.append("")
        lines.append("🧭 **Handoff:** `python3 tools/work_queue.py handoff show` "
                     "(history event %d)." % state["handoff"]["seq"])
    lines += ["", MARKER, "```json",
              json.dumps(state, indent=1, ensure_ascii=False), "```"]
    return "\n".join(lines) + "\n"


def parse_block(body):
    """The v2 state held in a rendered document; fail closed when invalid."""
    match = _BLOCK.search(body or "")
    if not match:
        raise FormatError("no v2 queue block (marker %s)" % MARKER)
    try:
        state = json.loads(match.group(1))
    except ValueError as exc:
        raise FormatError("queue JSON is malformed: %s" % exc)
    validate(state)
    return state
