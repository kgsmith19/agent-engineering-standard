"""Defect-sensitive tests for tools/queue_core.py (Issue #284, phase 1 of #283).

Strategy: the v2 core is pure, so every rule is exercised on plain data.
Each operation returns ``(new_state, events)`` and ``seal`` turns those
events into the hash-chained history, so tests can assert both the
resulting order and what the history recorded. A schema-agreement suite
replays one corpus through the core validator and a small JSON Schema
subset validator, so the published schema cannot drift from the rules.
"""

import copy
import json
import re
import sys
import unittest
from pathlib import Path

WORKTREE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKTREE / "tools"))
import queue_core as core  # noqa: E402

CTX = {"actor": "kgsmith19", "harness": "claude-code",
       "provider": "anthropic", "at": "2026-10-26T20:00:00Z"}


def build(*specs, owner="kgsmith19"):
    """A sealed queue from ``(title, status, depends_on)`` specs, in order."""
    state, events = core.op_init(owner)
    state, _ = core.seal(state, events, CTX)
    for title, status, deps in specs:
        state, _ = core.seal(*core.op_add(state, title, ["kgsmith19/x#1"],
                                          "", deps), CTX)
        item_id = state["items"][-1]["id"]
        if status == "active":
            state = _force(state, item_id, "active")
        elif status == "blocked":
            state, _ = core.seal(*core.op_transition(
                state, item_id, "block", "owner gated"), CTX)
        elif status == "done":
            state = _force(state, item_id, "active")
            state, _ = core.seal(*core.op_transition(
                state, item_id, "done", "PR #1 merged at abc1234"), CTX)
    return state


def _force(state, item_id, status):
    """Set a status directly (test setup only), keeping the state valid."""
    new = copy.deepcopy(state)
    core.find(new, item_id)["status"] = status
    core.validate(new)
    return new


def ids(state):
    return [item["id"] for item in state["items"]]


def run(state, op_result):
    """Seal an operation's result; return the new state and sealed events."""
    return core.seal(op_result[0], op_result[1], CTX)


class OrderAndNextTests(unittest.TestCase):
    """AC4 + order: next honours order and dependencies."""

    def test_next_is_first_pending_or_active_item(self):
        """Resume point: blocked items are skipped, active is resumed before later pending work."""
        state = build(("a", "blocked", []), ("b", "active", []),
                      ("c", "pending", []))
        self.assertEqual(core.next_item(state)["id"], "Q02")

    def test_next_skips_item_waiting_on_blocked_dependency(self):
        """AC4: an item whose dependency is blocked cannot run; next must not hand it out."""
        state = build(("dep", "blocked", []), ("needs dep", "pending", ["Q01"]),
                      ("free", "pending", []))
        self.assertEqual(core.next_item(state)["id"], "Q03")
        self.assertEqual(core.waiting_on(state, core.find(state, "Q02")),
                         ["Q01"])

    def test_archived_dependency_counts_as_met(self):
        """AC4+AC6: archiving a done item must not strand its dependents forever."""
        state = build(("dep", "done", []), ("needs dep", "pending", ["Q01"]))
        self.assertEqual(state["archived"], ["Q01"])
        self.assertEqual(core.next_item(state)["id"], "Q02")

    def test_next_none_when_all_blocked_or_waiting(self):
        """An exhausted queue must report empty instead of returning blocked work."""
        state = build(("a", "blocked", []), ("b", "pending", ["Q01"]))
        self.assertIsNone(core.next_item(state))


class TransitionTests(unittest.TestCase):
    """Order guard, dependency guard, and status transitions."""

    def test_start_refused_when_earlier_item_pending(self):
        """Order is binding: starting past a pending item is out-of-order work and must name it."""
        state = build(("a", "pending", []), ("b", "pending", []))
        with self.assertRaises(core.QueueError) as ctx:
            core.op_transition(state, "Q02", "start")
        self.assertIn("Q01", str(ctx.exception))

    def test_start_refused_when_earlier_item_active(self):
        """Two active items would mean two writers on the queue."""
        state = build(("a", "active", []), ("b", "pending", []))
        with self.assertRaises(core.QueueError):
            core.op_transition(state, "Q02", "start")

    def test_start_allowed_past_blocked_and_waiting_items(self):
        """Blocked items and items waiting on a blocked dependency are the only legitimate skips."""
        state = build(("a", "blocked", []), ("b", "pending", ["Q01"]),
                      ("c", "pending", []))
        new, events = run(state, core.op_transition(state, "Q03", "start"))
        self.assertEqual(core.find(new, "Q03")["status"], "active")
        self.assertEqual((events[0]["from"], events[0]["to"]),
                         ("pending", "active"))

    def test_start_refused_on_unmet_dependency(self):
        """AC4: start must refuse an item whose dependency is not done, naming the dependency."""
        state = build(("a", "blocked", []), ("b", "pending", ["Q01"]))
        with self.assertRaises(core.QueueError) as ctx:
            core.op_transition(state, "Q02", "start")
        self.assertIn("Q01", str(ctx.exception))

    def test_start_refused_on_already_active_or_blocked(self):
        """Restarting is a silent no-op or an unrecorded unblock; both must be explicit."""
        state = build(("a", "active", []), ("b", "blocked", []))
        for item_id in ("Q01", "Q02"):
            with self.assertRaises(core.QueueError):
                core.op_transition(state, item_id, "start")

    def test_block_requires_reason_and_records_it(self):
        """An unexplained block is an invisible skip; the reason is what makes it auditable."""
        state = build(("a", "pending", []))
        with self.assertRaises(core.QueueError):
            core.op_transition(state, "Q01", "block", "   ")
        new, events = run(state, core.op_transition(state, "Q01", "block",
                                                    "needs owner"))
        self.assertEqual(core.find(new, "Q01")["status"], "blocked")
        self.assertEqual(events[0]["reason"], "needs owner")

    def test_unblock_only_from_blocked(self):
        """Unblocking a pending item would hide a typo in the id."""
        state = build(("a", "pending", []), ("b", "blocked", []))
        with self.assertRaises(core.QueueError):
            core.op_transition(state, "Q01", "unblock")
        new, _ = run(state, core.op_transition(state, "Q02", "unblock"))
        self.assertEqual(core.find(new, "Q02")["status"], "pending")

    def test_done_requires_evidence_and_archives(self):
        """AC6: done without evidence is a confidence claim; done items leave live state but keep their id."""
        state = build(("a", "active", []), ("b", "pending", []))
        with self.assertRaises(core.QueueError):
            core.op_transition(state, "Q01", "done", "")
        new, events = run(state, core.op_transition(
            state, "Q01", "done", "PR #9 merged at abc1234"))
        self.assertEqual(ids(new), ["Q02"])
        self.assertEqual(new["archived"], ["Q01"])
        self.assertEqual([e["op"] for e in events], ["done", "archive"])
        self.assertEqual(events[0]["reason"], "PR #9 merged at abc1234")
        self.assertEqual(events[1]["from"]["title"], "a")

    def test_done_refused_on_pending_item(self):
        """Finishing work that was never started skips the claim step."""
        state = build(("a", "pending", []))
        with self.assertRaises(core.QueueError):
            core.op_transition(state, "Q01", "done", "evidence")

    def test_unknown_item_and_action_fail_loudly(self):
        """A typo must fail loudly instead of silently doing nothing."""
        state = build(("a", "pending", []))
        with self.assertRaises(core.QueueError):
            core.op_transition(state, "Q99", "start")
        with self.assertRaises(core.QueueError):
            core.op_transition(state, "Q01", "skip")

    def test_operations_do_not_mutate_input(self):
        """Pure core: mutating the read state would corrupt the compare-and-swap baseline."""
        state = build(("a", "pending", []), ("b", "pending", []))
        before = copy.deepcopy(state)
        core.op_add(state, "c", [], "", [])
        core.op_transition(state, "Q01", "start")
        core.op_move(state, "Q02", before="Q01", authorized_by="kgsmith19",
                     reason="owner said so")
        self.assertEqual(state, before)


class AddEditTests(unittest.TestCase):
    """Append-only add, position-preserving edit, dependency rules."""

    def test_add_appends_with_monotonic_id(self):
        """Interruptions append; ids are never reused even after archiving."""
        state = build(("a", "done", []), ("b", "pending", []))
        new, events = run(state, core.op_add(state, "c", [], "", []))
        self.assertEqual(ids(new), ["Q02", "Q03"])
        self.assertEqual(new["next_id"], 4)
        self.assertEqual(events[0]["op"], "add")
        self.assertEqual(events[0]["to"]["title"], "c")

    def test_dependency_must_be_earlier_or_archived(self):
        """AC4: a dependency on a later or unknown item would invert the binding order or deadlock."""
        state = build(("a", "pending", []), ("b", "pending", []))
        with self.assertRaises(core.QueueError):
            core.op_edit(state, "Q01", depends_on=["Q02"])
        with self.assertRaises(core.QueueError):
            core.op_add(state, "c", [], "", ["Q77"])
        with self.assertRaises(core.QueueError):
            core.op_edit(state, "Q01", depends_on=["Q01"])
        new, _ = run(state, core.op_edit(state, "Q02", depends_on=["Q01"]))
        self.assertEqual(core.find(new, "Q02")["depends_on"], ["Q01"])

    def test_edit_records_old_and_new_values(self):
        """AC5: history must hold from->to for edits, or replaced notes are lost."""
        state = build(("a", "pending", []))
        new, events = run(state, core.op_edit(state, "Q01", note="new note",
                                              title="renamed"))
        self.assertEqual(ids(new), ["Q01"])
        self.assertEqual(events[0]["from"], {"note": "", "title": "a"})
        self.assertEqual(events[0]["to"], {"note": "new note",
                                           "title": "renamed"})

    def test_noop_edit_refused(self):
        """An edit that changes nothing would add an empty history event."""
        state = build(("a", "pending", []))
        with self.assertRaises(core.QueueError):
            core.op_edit(state, "Q01", title="a")

    def test_length_caps(self):
        """AC6: notes concatenated without bound in v1; caps keep live state bounded."""
        state = build(("a", "pending", []))
        with self.assertRaises(core.QueueError):
            core.op_edit(state, "Q01", note="x" * (core.LIMITS["note"] + 1))
        with self.assertRaises(core.QueueError):
            core.op_add(state, "t" * (core.LIMITS["title"] + 1), [], "", [])
        with self.assertRaises(core.QueueError):
            core.op_add(state, "  ", [], "", [])


class MoveTests(unittest.TestCase):
    """AC3: move is the only reorder and needs owner authority + reason."""

    def setUp(self):
        self.state = build(("a", "pending", []), ("b", "pending", []),
                           ("c", "pending", []))

    def test_move_after_and_before(self):
        """AC3: the owner's reorder must land exactly where asked."""
        new, events = run(self.state, core.op_move(
            self.state, "Q03", after="Q01", authorized_by="kgsmith19",
            reason="owner 2026-10-26"))
        self.assertEqual(ids(new), ["Q01", "Q03", "Q02"])
        self.assertEqual(events[0]["op"], "move")
        self.assertEqual(events[0]["from"], {"after": "Q02"})
        self.assertEqual(events[0]["to"], {"after": "Q01",
                                           "authorized_by": "kgsmith19"})
        self.assertEqual(events[0]["reason"], "owner 2026-10-26")
        new, _ = run(self.state, core.op_move(
            self.state, "Q03", before="Q01", authorized_by="kgsmith19",
            reason="r"))
        self.assertEqual(ids(new), ["Q03", "Q01", "Q02"])

    def test_move_refused_without_owner_authority(self):
        """AC3: an agent cannot reorder on its own authority."""
        for who in ("", "claude", "KGSMITH19"):
            with self.assertRaises(core.QueueError):
                core.op_move(self.state, "Q03", after="Q01",
                             authorized_by=who, reason="r")

    def test_move_refused_without_reason(self):
        """AC3: an unexplained move is invisible drift."""
        with self.assertRaises(core.QueueError):
            core.op_move(self.state, "Q03", after="Q01",
                         authorized_by="kgsmith19", reason=" ")

    def test_move_needs_exactly_one_anchor_and_a_real_change(self):
        """A move with no anchor, two anchors, a self anchor or no effect must be refused."""
        bad = [dict(), dict(after="Q01", before="Q02"), dict(after="Q03"),
               dict(after="Q02"), dict(after="Q99")]
        for anchor in bad:
            with self.assertRaises(core.QueueError, msg=str(anchor)):
                core.op_move(self.state, "Q03", authorized_by="kgsmith19",
                             reason="r", **anchor)

    def test_move_never_places_item_before_its_dependency(self):
        """AC3+AC4: a dependent ahead of its dependency would make order and dependencies disagree."""
        state = build(("a", "pending", []), ("b", "pending", ["Q01"]))
        with self.assertRaises(core.QueueError):
            core.op_move(state, "Q02", before="Q01",
                         authorized_by="kgsmith19", reason="r")
        with self.assertRaises(core.QueueError):
            core.op_move(state, "Q01", after="Q02",
                         authorized_by="kgsmith19", reason="r")


class HistoryChainTests(unittest.TestCase):
    """AC5: append-only, hash-chained, who/when/harness/provider."""

    def _log(self):
        state, events = core.op_init("kgsmith19")
        state, log = core.seal(state, events, CTX)
        for title in ("a", "b"):
            state, sealed = core.seal(*core.op_add(state, title, [], "", []),
                                      CTX)
            log += sealed
        return state, log

    def test_events_carry_context_and_chain(self):
        """AC5: every event records who, when, harness and provider and links to its predecessor."""
        state, log = self._log()
        self.assertEqual([e["seq"] for e in log], [1, 2, 3])
        self.assertIsNone(log[0]["prev"])
        self.assertEqual(log[1]["prev"], log[0]["hash"])
        for key in ("actor", "harness", "provider", "at"):
            self.assertEqual(log[2][key], CTX[key])
        self.assertEqual(state["history"], {"seq": 3, "head": log[2]["hash"]})
        self.assertEqual(core.chain(log, state), log)

    def test_orphans_and_junk_are_ignored(self):
        """A write that lost its compare-and-swap leaves events no committed head points to; they must not count."""
        state, log = self._log()
        orphan_state, orphan = core.seal(*core.op_add(state, "lost", [], "", []),
                                         CTX)
        self.assertEqual(core.chain(log + orphan + [{"junk": 1}], state), log)

    def test_tampered_event_fails_closed(self):
        """AC5: rewriting history must be detected, never trusted."""
        state, log = self._log()
        forged = copy.deepcopy(log)
        forged[1]["to"]["title"] = "forged"
        with self.assertRaises(core.HistoryError):
            core.chain(forged, state)
        forged = copy.deepcopy(log)
        forged[1]["to"]["title"] = "forged"
        forged[1]["hash"] = core.event_hash(forged[1])
        with self.assertRaises(core.HistoryError):
            core.chain(forged, state)

    def test_missing_event_fails_closed(self):
        """A dropped event breaks the chain; history must fail closed rather than show a gap."""
        state, log = self._log()
        with self.assertRaises(core.HistoryError):
            core.chain([log[0], log[2]], state)

    def test_history_filters_by_item(self):
        """AC5: history ID shows only that item's events."""
        state, log = self._log()
        self.assertEqual([e["seq"] for e in core.history(log, "Q02")], [3])

    def test_bad_context_refused(self):
        """AC5: an event with no actor or a malformed time would be an anonymous history entry."""
        state, events = core.op_init("kgsmith19")
        for key, value in (("actor", ""), ("at", "yesterday"),
                           ("provider", None)):
            ctx = dict(CTX, **{key: value})
            with self.assertRaises(core.QueueError):
                core.seal(state, events, ctx)


class HandoffTests(unittest.TestCase):
    """AC7: handoff lives in history; state holds its digest."""

    def test_set_then_read_back(self):
        """AC7: the handoff a fresh session reads is exactly the last one written."""
        state, log = core.seal(*core.op_init("kgsmith19"), CTX)
        self.assertIsNone(core.handoff_text(state, log))
        for text in ("first", "second ✓\nline"):
            state, sealed = core.seal(*core.op_handoff(state, text), CTX)
            log += sealed
        self.assertEqual(core.handoff_text(state, core.chain(log, state)),
                         "second ✓\nline")
        self.assertEqual(state["handoff"]["seq"], 3)

    def test_handoff_digest_mismatch_fails_closed(self):
        """A handoff whose text does not match the committed digest must not be shown."""
        state, log = core.seal(*core.op_init("kgsmith19"), CTX)
        state, sealed = core.seal(*core.op_handoff(state, "real"), CTX)
        broken = copy.deepcopy(state)
        broken["handoff"]["sha256"] = "0" * 64
        with self.assertRaises(core.HistoryError):
            core.handoff_text(broken, log + sealed)

    def test_handoff_size_cap(self):
        """AC6: an unbounded handoff would exceed a backend's comment limit."""
        state, _ = core.seal(*core.op_init("kgsmith19"), CTX)
        with self.assertRaises(core.QueueError):
            core.op_handoff(state, "x" * (core.LIMITS["handoff"] + 1))
        with self.assertRaises(core.QueueError):
            core.op_handoff(state, "  ")


class BudgetAndSecretTests(unittest.TestCase):
    """AC6 bounded state; no secrets in state or history."""

    def test_write_over_budget_refused(self):
        """AC6: a write that would exceed the budget is refused, never truncated."""
        state = build()
        refs = ["kgsmith19/agent-engineering-standard#%d" % n for n in range(12)]
        with self.assertRaises(core.BudgetError):
            for n in range(400):
                state, _ = core.seal(*core.op_add(
                    state, "t" * core.LIMITS["title"], refs,
                    "n" * core.LIMITS["note"], []), CTX)
        self.assertLessEqual(core.size(state), core.STATE_BUDGET)

    def test_secret_shaped_text_refused(self):
        """No secrets: a token pasted into a note would be published in the Issue and history forever."""
        state = build(("a", "pending", []))
        for secret in ("ghp_" + "a" * 36, "github_pat_" + "b" * 30,
                       "sk-ant-" + "c" * 30, "AKIA" + "D" * 16,
                       "-----BEGIN RSA PRIVATE KEY-----"):
            with self.assertRaises(core.SecretError, msg=secret):
                core.seal(*core.op_edit(state, "Q01", note="x " + secret), CTX)
            with self.assertRaises(core.SecretError):
                core.seal(*core.op_handoff(state, secret), CTX)


class ValidateTests(unittest.TestCase):
    """Fail closed on malformed state."""

    def test_valid_states_pass(self):
        """The validator must accept every state the operations produce."""
        core.validate(build(("a", "done", []), ("b", "blocked", []),
                            ("c", "pending", ["Q02"])))

    def test_semantic_violations_rejected(self):
        """Rules the schema cannot express still fail closed."""
        state = build(("a", "pending", []), ("b", "pending", ["Q01"]))
        cases = []
        dup = copy.deepcopy(state)
        dup["items"][1]["id"] = "Q01"
        cases.append(dup)
        inverted = copy.deepcopy(state)
        inverted["items"].reverse()
        cases.append(inverted)
        future = copy.deepcopy(state)
        future["next_id"] = 2
        cases.append(future)
        overlap = copy.deepcopy(state)
        overlap["archived"] = ["Q01"]
        cases.append(overlap)
        headless = copy.deepcopy(state)
        headless["history"]["head"] = None
        cases.append(headless)
        for case in cases:
            with self.assertRaises(core.FormatError):
                core.validate(case)


def _schema_check(schema, value, root=None):
    """Tiny JSON Schema subset validator (the keywords the v2 schema uses)."""
    root = root or schema
    if "$ref" in schema:
        name = schema["$ref"].split("/")[-1]
        return _schema_check(root["$defs"][name], value, root)
    if "oneOf" in schema:
        return sum(_schema_check(s, value, root) for s in schema["oneOf"]) == 1
    kind = schema.get("type")
    kinds = {"object": dict, "array": list, "string": str, "null": type(None)}
    if kind == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            return False
        return value >= schema.get("minimum", value)
    if kind and not isinstance(value, kinds[kind]):
        return False
    if "const" in schema and value != schema["const"]:
        return False
    if "enum" in schema and value not in schema["enum"]:
        return False
    if isinstance(value, str):
        if len(value) > schema.get("maxLength", len(value)):
            return False
        if len(value) < schema.get("minLength", 0):
            return False
        if "pattern" in schema and not re.search(schema["pattern"], value):
            return False
    if isinstance(value, list):
        if len(value) > schema.get("maxItems", len(value)):
            return False
        if schema.get("uniqueItems") and len(set(map(json.dumps, value))) != len(value):
            return False
        return all(_schema_check(schema["items"], v, root) for v in value)
    if isinstance(value, dict):
        props = schema.get("properties", {})
        if set(schema.get("required", [])) - set(value):
            return False
        if schema.get("additionalProperties") is False and set(value) - set(props):
            return False
        return all(_schema_check(props[k], v, root)
                   for k, v in value.items() if k in props)
    return True


class SchemaAgreementTests(unittest.TestCase):
    """AC1: the published JSON Schema and the core validator agree."""

    @classmethod
    def setUpClass(cls):
        path = WORKTREE / "tools" / "queue_v2.schema.json"
        cls.schema = json.loads(path.read_text(encoding="utf-8"))

    def _corpus(self):
        good = build(("a", "done", []), ("b", "blocked", []),
                     ("c", "active", []), ("d", "pending", ["Q02"]))
        state, _ = core.seal(*core.op_handoff(good, "handoff"), CTX)
        yield "valid", state, True
        yield "empty", build(), True

        def mutate(name, fn):
            bad = copy.deepcopy(state)
            fn(bad)
            return name, bad, False

        yield mutate("version", lambda s: s.update(version=1))
        yield mutate("extra key", lambda s: s.update(extra=1))
        yield mutate("missing owner", lambda s: s.pop("owner"))
        yield mutate("empty owner", lambda s: s.update(owner=""))
        yield mutate("next_id bool", lambda s: s.update(next_id=True))
        yield mutate("next_id zero", lambda s: s.update(next_id=0))
        yield mutate("status done", lambda s: s["items"][0].update(status="done"))
        yield mutate("status unknown", lambda s: s["items"][0].update(status="x"))
        yield mutate("bad id", lambda s: s["items"][0].update(id="X1"))
        yield mutate("item extra", lambda s: s["items"][0].update(extra=1))
        yield mutate("refs str", lambda s: s["items"][0].update(refs="a"))
        yield mutate("refs too many", lambda s: s["items"][0].update(
            refs=["r%d" % n for n in range(core.LIMITS["refs"] + 1)]))
        yield mutate("ref too long", lambda s: s["items"][0].update(
            refs=["r" * (core.LIMITS["ref"] + 1)]))
        yield mutate("title long", lambda s: s["items"][0].update(
            title="t" * (core.LIMITS["title"] + 1)))
        yield mutate("title empty", lambda s: s["items"][0].update(title=""))
        yield mutate("note long", lambda s: s["items"][0].update(
            note="n" * (core.LIMITS["note"] + 1)))
        yield mutate("deps str", lambda s: s["items"][0].update(depends_on="Q1"))
        yield mutate("archived bad", lambda s: s.update(archived=["nope"]))
        yield mutate("history seq neg", lambda s: s["history"].update(seq=-1))
        yield mutate("history head bad", lambda s: s["history"].update(head="zz"))
        yield mutate("handoff bad", lambda s: s.update(handoff={"seq": 1}))
        yield mutate("items missing", lambda s: s.pop("items"))

    def test_schema_and_validator_agree_on_corpus(self):
        """AC1: a rule enforced by only one of schema and core means other tools validate a different queue."""
        for name, state, expected in self._corpus():
            schema_ok = _schema_check(self.schema, state)
            try:
                core.validate(state)
                core_ok = True
            except core.FormatError:
                core_ok = False
            self.assertEqual((schema_ok, core_ok), (expected, expected), name)

    def test_schema_constants_match_core(self):
        """AC1: limits and statuses are declared once in core and mirrored exactly by the schema."""
        item = self.schema["$defs"]["item"]["properties"]
        self.assertEqual(self.schema["properties"]["version"]["const"],
                         core.VERSION)
        self.assertEqual(tuple(item["status"]["enum"]), core.STATUSES)
        self.assertEqual(item["title"]["maxLength"], core.LIMITS["title"])
        self.assertEqual(item["note"]["maxLength"], core.LIMITS["note"])
        self.assertEqual(item["refs"]["maxItems"], core.LIMITS["refs"])
        self.assertEqual(self.schema["$id"].rsplit("/", 1)[-1],
                         "queue_v2.schema.json")


class RenderTests(unittest.TestCase):
    """The human checklist mirrors the queue."""

    def test_render_lists_order_next_deps_and_archive(self):
        """The owner must read the same queue agents execute: order, NEXT, dependencies and archived count."""
        state = build(("a", "done", []), ("b", "blocked", []),
                      ("c", "pending", ["Q02"]), ("d", "pending", []))
        body = core.render_markdown(state)
        self.assertLess(body.index("**Q02**"), body.index("**Q03**"))
        self.assertLess(body.index("**Q03**"), body.index("**Q04**"))
        q04 = [line for line in body.splitlines() if "**Q04**" in line][0]
        self.assertIn("NEXT", q04)
        self.assertIn("depends on Q02", body)
        self.assertIn("Q01", body.split(core.MARKER)[0])
        self.assertEqual(core.parse_block(body), state)

    def test_parse_block_fails_closed(self):
        """A body without a valid v2 block must never be treated as an empty queue."""
        for body in ("prose", core.MARKER + "\n```json\n{bad\n```\n"):
            with self.assertRaises(core.FormatError):
                core.parse_block(body)


if __name__ == "__main__":
    unittest.main()
