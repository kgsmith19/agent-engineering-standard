"""Defect-sensitive tests for tools/work_queue.py (Issue #276).

Strategy: the queue's pure core (parse/render/next_item/append/edit/
transition) is exercised on plain data; the CLI is exercised through an
injected fake transport that records every PATCH, so each test can assert
not only the result but also that a refused or failed command wrote
nothing.
"""

import contextlib
import importlib.util
import io
import json
import unittest
from pathlib import Path

WORKTREE = Path(__file__).resolve().parent.parent

_SPEC = importlib.util.spec_from_file_location(
    "queue_tool", WORKTREE / "tools" / "work_queue.py"
)
queue_tool = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(queue_tool)


def _state(*statuses):
    """A queue whose items carry the given statuses, in order."""
    items = []
    for index, status in enumerate(statuses, start=1):
        item = {
            "id": "Q%02d" % index,
            "title": "item %d" % index,
            "refs": ["kgsmith19/example#%d" % index],
            "status": status,
            "note": "",
        }
        if status == "blocked":
            item["note"] = "waiting on owner"
        items.append(item)
    return {"version": 1, "next_id": len(items) + 1, "items": items}


class FakeTransport:
    """In-memory Issue store; optionally mutates between read and write."""

    def __init__(self, body, race=False):
        self.body = body
        self.updated_at = "2026-10-26T00:00:00Z"
        self.reads = 0
        self.patches = []
        self.race = race

    def get_issue(self, number):
        self.reads += 1
        if self.race and self.reads == 2:
            self.updated_at = "2026-10-26T00:00:09Z"
        return self.body, self.updated_at

    def patch_issue(self, number, body):
        self.patches.append(body)
        self.body = body
        self.updated_at = "2026-10-26T00:01:00Z"


def _run(transport, *argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = queue_tool.main(["--issue", "1", *argv], transport=transport)
    return code, out.getvalue(), err.getvalue()


class RoundTripTests(unittest.TestCase):
    def test_render_then_parse_is_identity(self):
        """The JSON block is the source of truth; a lossy render would silently corrupt the queue on the next write."""
        state = _state("done", "active", "blocked", "pending")
        self.assertEqual(queue_tool.parse(queue_tool.render(state)), state)

    def test_render_shows_human_checklist_in_queue_order(self):
        """The human checklist must mirror queue order and done state, or the owner reads a different queue than agents execute."""
        body = queue_tool.render(_state("done", "pending"))
        first = body.index("**Q01**")
        second = body.index("**Q02**")
        self.assertLess(first, second)
        self.assertIn("- [x] **Q01**", body)
        self.assertIn("- [ ] **Q02**", body)


class NextItemTests(unittest.TestCase):
    """AC1: next = first item neither done nor blocked."""

    def test_next_skips_done_and_blocked(self):
        """AC1: resuming at a done or blocked item would redo finished work or stall on an owner-gated item."""
        state = _state("done", "blocked", "pending", "pending")
        self.assertEqual(queue_tool.next_item(state)["id"], "Q03")

    def test_next_returns_active_item_before_later_pending(self):
        """AC1: an interrupted active item must be resumed first; skipping it would abandon in-flight work."""
        state = _state("done", "active", "pending")
        self.assertEqual(queue_tool.next_item(state)["id"], "Q02")

    def test_next_is_none_when_everything_done_or_blocked(self):
        """AC1: an exhausted queue must be reported as empty rather than returning a blocked item as work."""
        self.assertIsNone(queue_tool.next_item(_state("done", "blocked")))

    def test_cli_next_prints_item_and_refs(self):
        """AC1: a fresh session needs the item id and its Issue refs to resume without re-deriving context."""
        transport = FakeTransport(queue_tool.render(_state("done", "pending")))
        code, out, _ = _run(transport, "next")
        self.assertEqual(code, 0)
        self.assertIn("Q02", out)
        self.assertIn("kgsmith19/example#2", out)

    def test_cli_next_on_exhausted_queue_exits_3(self):
        """AC1: harnesses branch on exit 3; a zero exit on empty would loop them on nothing."""
        transport = FakeTransport(queue_tool.render(_state("done")))
        code, out, _ = _run(transport, "next")
        self.assertEqual(code, queue_tool.EXIT_EMPTY)
        self.assertEqual(queue_tool.EXIT_EMPTY, 3)
        self.assertIn("QUEUE EMPTY", out)


class AppendOnlyTests(unittest.TestCase):
    """AC2: add appends; ids are monotonic and never reused; no reorder."""

    def test_add_appends_at_end_with_next_id(self):
        """AC2: interruptions append to the end; inserting earlier would silently reorder binding work."""
        state = _state("pending", "pending")
        new = queue_tool.append(state, "late", ["kgsmith19/x#9"], "")
        self.assertEqual([i["id"] for i in new["items"]], ["Q01", "Q02", "Q03"])
        self.assertEqual(new["items"][-1]["title"], "late")
        self.assertEqual(new["items"][-1]["status"], "pending")
        self.assertEqual(new["next_id"], 4)

    def test_ids_are_never_reused_even_if_items_vanish(self):
        """AC2: reused ids would make old evidence notes and Work State links point at the wrong item."""
        state = _state("pending")
        state["next_id"] = 7
        new = queue_tool.append(state, "t", [], "")
        self.assertEqual(new["items"][-1]["id"], "Q07")

    def test_append_does_not_mutate_input(self):
        """Pure core: mutating the read state would make the concurrency re-read compare against altered data."""
        state = _state("pending")
        queue_tool.append(state, "t", [], "")
        self.assertEqual(len(state["items"]), 1)

    def test_edit_changes_details_but_never_position(self):
        """AC2: editing details is allowed; any position change through edit would break the binding order."""
        state = _state("pending", "pending", "pending")
        new = queue_tool.edit(state, "Q02", title="renamed", note="n",
                              refs=["kgsmith19/y#1"])
        self.assertEqual([i["id"] for i in new["items"]], ["Q01", "Q02", "Q03"])
        self.assertEqual(new["items"][1]["title"], "renamed")
        self.assertEqual(new["items"][1]["refs"], ["kgsmith19/y#1"])

    def test_cli_exposes_no_reorder_or_delete_command(self):
        """AC2: the absence of a reorder/delete entry point is the structural guarantee that the queue is respected."""
        commands = set(queue_tool.build_parser()._subparsers._group_actions[0].choices)
        self.assertFalse(commands & {"move", "reorder", "insert", "delete",
                                     "remove", "swap", "prioritize"})
        self.assertIn("add", commands)

    def test_cli_add_writes_once_and_appends(self):
        """AC2: add must produce exactly one write that lands the new item at the end."""
        transport = FakeTransport(queue_tool.render(_state("pending")))
        code, _, _ = _run(transport, "add", "--title", "new work",
                          "--ref", "kgsmith19/z#5")
        self.assertEqual(code, 0)
        self.assertEqual(len(transport.patches), 1)
        items = queue_tool.parse(transport.body)["items"]
        self.assertEqual(items[-1]["title"], "new work")
        self.assertEqual(items[-1]["refs"], ["kgsmith19/z#5"])


class OrderGuardTests(unittest.TestCase):
    """AC3: start refuses out-of-order work unless earlier items are
    done, or blocked with a recorded reason."""

    def test_start_refused_when_earlier_item_pending(self):
        """AC3: starting a later item while an earlier one is pending is out-of-order work and must name the blocker."""
        with self.assertRaises(queue_tool.QueueError) as ctx:
            queue_tool.transition(_state("pending", "pending"), "Q02", "start")
        self.assertIn("Q01", str(ctx.exception))

    def test_start_refused_when_earlier_item_active(self):
        """AC3: an earlier active item is unfinished; starting past it would leave two writers on the queue."""
        with self.assertRaises(queue_tool.QueueError):
            queue_tool.transition(_state("active", "pending"), "Q02", "start")

    def test_start_allowed_past_done_and_reasoned_block(self):
        """AC3: done and reason-blocked items are the only legitimate skips; refusing them would deadlock owner-gated queues."""
        new = queue_tool.transition(_state("done", "blocked", "pending"),
                                    "Q03", "start")
        self.assertEqual(new["items"][2]["status"], "active")

    def test_block_requires_reason(self):
        """AC3: an unexplained block is an invisible skip; the reason is what makes skipping auditable."""
        with self.assertRaises(queue_tool.QueueError):
            queue_tool.transition(_state("pending"), "Q01", "block", reason="  ")

    def test_block_records_reason(self):
        """AC3: the recorded reason tells the owner exactly what unblocks the item."""
        new = queue_tool.transition(_state("pending"), "Q01", "block",
                                    reason="needs TAILSCALE_AUTHKEY")
        self.assertEqual(new["items"][0]["status"], "blocked")
        self.assertIn("TAILSCALE_AUTHKEY", new["items"][0]["note"])

    def test_done_records_evidence(self):
        """Completion standard: done without evidence (PR, exact head) would be a confidence-based completion claim."""
        new = queue_tool.transition(_state("active"), "Q01", "done",
                                    reason="PR #9 merged at abc1234")
        self.assertEqual(new["items"][0]["status"], "done")
        self.assertIn("abc1234", new["items"][0]["note"])

    def test_unknown_item_is_an_error(self):
        """A typo in an id must fail loudly instead of silently doing nothing."""
        with self.assertRaises(queue_tool.QueueError):
            queue_tool.transition(_state("pending"), "Q99", "start")

    def test_cli_refused_start_writes_nothing(self):
        """AC3: a refused command must leave the Issue byte-identical."""
        transport = FakeTransport(queue_tool.render(_state("pending", "pending")))
        code, _, err = _run(transport, "start", "Q02")
        self.assertEqual(code, queue_tool.EXIT_REFUSED)
        self.assertIn("Q01", err)
        self.assertEqual(transport.patches, [])


class ConcurrencyTests(unittest.TestCase):
    """AC4: re-read before PATCH; abort on concurrent change."""

    def test_concurrent_change_aborts_without_writing(self):
        """AC4: two sessions writing concurrently must not lose an update; the second aborts with zero PATCH."""
        transport = FakeTransport(queue_tool.render(_state("pending")), race=True)
        code, _, err = _run(transport, "add", "--title", "x")
        self.assertEqual(code, queue_tool.EXIT_CONFLICT)
        self.assertIn("changed", err)
        self.assertEqual(transport.patches, [])

    def test_write_rereads_before_patching(self):
        """AC4: the race check only works if the Issue is re-read immediately before the single PATCH."""
        transport = FakeTransport(queue_tool.render(_state("pending")))
        _run(transport, "start", "Q01")
        self.assertEqual(transport.reads, 2)
        self.assertEqual(len(transport.patches), 1)


class FailClosedTests(unittest.TestCase):
    """AC5: malformed or missing block fails closed, never writes."""

    def test_missing_marker_raises(self):
        """AC5: a body without the marker must never be treated as an empty queue."""
        with self.assertRaises(queue_tool.QueueFormatError):
            queue_tool.parse("just prose, no queue here")

    def test_bad_json_raises(self):
        """AC5: malformed JSON must fail closed; defaulting to empty would let the next write erase the queue."""
        body = queue_tool.MARKER + "\n```json\n{not json\n```\n"
        with self.assertRaises(queue_tool.QueueFormatError):
            queue_tool.parse(body)

    def test_invalid_status_raises(self):
        """AC5: an unknown status would make next_item and the order guard misjudge an item."""
        state = _state("pending")
        state["items"][0]["status"] = "maybe"
        body = queue_tool.MARKER + "\n```json\n" + json.dumps(state) + "\n```\n"
        with self.assertRaises(queue_tool.QueueFormatError):
            queue_tool.parse(body)

    def test_duplicate_ids_raise(self):
        """AC5: duplicate ids make transitions ambiguous and could mark the wrong item done."""
        state = _state("pending", "pending")
        state["items"][1]["id"] = "Q01"
        body = queue_tool.MARKER + "\n```json\n" + json.dumps(state) + "\n```\n"
        with self.assertRaises(queue_tool.QueueFormatError):
            queue_tool.parse(body)

    def test_cli_next_on_garbage_exits_2_and_writes_nothing(self):
        """AC5: format errors exit 2, distinct from empty (3), and never write."""
        transport = FakeTransport("garbage")
        code, out, err = _run(transport, "next")
        self.assertEqual(code, queue_tool.EXIT_FORMAT)
        self.assertEqual(queue_tool.EXIT_FORMAT, 2)
        self.assertNotIn("QUEUE EMPTY", out)
        self.assertEqual(transport.patches, [])

    def test_cli_mutation_on_garbage_writes_nothing(self):
        """AC5: a mutation against a corrupt body must not overwrite it with a fresh queue."""
        transport = FakeTransport("garbage")
        code, _, _ = _run(transport, "add", "--title", "x")
        self.assertEqual(code, queue_tool.EXIT_FORMAT)
        self.assertEqual(transport.patches, [])


class InitTests(unittest.TestCase):
    def test_init_seeds_empty_queue_on_marker_free_issue(self):
        """Bootstrap: a new queue Issue can be seeded without hand-writing JSON."""
        transport = FakeTransport("Owner prose.")
        code, _, _ = _run(transport, "init")
        self.assertEqual(code, 0)
        state = queue_tool.parse(transport.body)
        self.assertEqual(state["items"], [])
        self.assertEqual(state["next_id"], 1)

    def test_init_refuses_to_overwrite_existing_queue(self):
        """init must never reset an existing queue, which would erase its order and history."""
        transport = FakeTransport(queue_tool.render(_state("pending")))
        code, _, _ = _run(transport, "init")
        self.assertEqual(code, queue_tool.EXIT_REFUSED)
        self.assertEqual(transport.patches, [])


if __name__ == "__main__":
    unittest.main()
