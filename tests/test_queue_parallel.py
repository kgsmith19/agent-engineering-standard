"""Parallel active items under an owner-set cap (Issue #302).

The owner authorized parallel PRs, up to five at once (2026-10-27). The cap
lives in queue state as ``max_active`` (absent means 1, so every queue
written before #302 behaves exactly as before). Only the owner changes it,
through a reasoned, hash-chained ``limit`` event. Claims stay in queue
order: a later item never starts ahead of an earlier pending one.
"""

import copy
import json
import sys
import unittest
from pathlib import Path

WORKTREE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKTREE / "tools"))
sys.path.insert(0, str(WORKTREE / "tests"))
import queue_core as core  # noqa: E402
from test_queue_core import CTX, _schema_check, build, run  # noqa: E402
from test_work_queue_v2 import run as cli_run, seeded  # noqa: E402
import work_queue as cli  # noqa: E402


def limited(state, n):
    new, _ = run(state, core.op_limit(state, n, "kgsmith19", "owner authorized parallel PRs"))
    return new


def start(state, item_id):
    new, _ = run(state, core.op_transition(state, item_id, "start"))
    return new


class CapStateTests(unittest.TestCase):
    """AC1: an optional max_active, 1-5, absent means 1."""

    def test_absent_cap_is_one_and_legacy_states_stay_valid(self):
        """AC1: queues written before #302 carry no max_active and must still load and mean a cap of 1."""
        state = build(("a", "pending", []))
        self.assertNotIn("max_active", state)
        core.validate(state)
        self.assertEqual(core.max_active(state), 1)

    def test_cap_bounds_are_validated(self):
        """AC1: a stored cap outside 1-5 (or not an integer) is malformed state and fails closed."""
        state = build(("a", "pending", []))
        for good in (1, 3, core.MAX_PARALLEL):
            ok = copy.deepcopy(state)
            ok["max_active"] = good
            core.validate(ok)
        for bad in (0, -1, core.MAX_PARALLEL + 1, True, "5", 2.0, None):
            broken = copy.deepcopy(state)
            broken["max_active"] = bad
            with self.assertRaises(core.FormatError, msg=repr(bad)):
                core.validate(broken)

    def test_max_parallel_is_five(self):
        """AC1: the owner's ceiling is five; a larger constant would let an agent raise it past the authorization."""
        self.assertEqual(core.MAX_PARALLEL, 5)

    def test_other_extra_keys_still_fail_closed(self):
        """AC1: allowing max_active must not open the state to arbitrary keys."""
        state = build(("a", "pending", []))
        state["max_parallel"] = 5
        with self.assertRaises(core.FormatError):
            core.validate(state)


class LimitOpTests(unittest.TestCase):
    """AC2: only the owner sets the cap, with a reason, and it is logged."""

    def test_owner_sets_cap_and_history_records_it(self):
        """AC2: the limit event names from, to, the authorizer and the reason, chained like every other event."""
        state = build(("a", "pending", []))
        new, events = run(state, core.op_limit(state, 5, "kgsmith19", "parallel PRs"))
        self.assertEqual(new["max_active"], 5)
        self.assertEqual(events[0]["op"], "limit")
        self.assertEqual(events[0]["from"], 1)
        self.assertEqual(events[0]["to"], {"max_active": 5, "authorized_by": "kgsmith19"})
        self.assertEqual(events[0]["reason"], "parallel PRs")
        core.validate(new)

    def test_non_owner_cannot_set_cap(self):
        """AC2: an agent raising its own concurrency is exactly what the owner gate prevents."""
        state = build(("a", "pending", []))
        for who in ("someone", "", "KGSMITH19"):
            with self.assertRaises(core.QueueError):
                core.op_limit(state, 5, who, "reason")

    def test_reason_required(self):
        """AC2: an unexplained cap change is unauditable."""
        state = build(("a", "pending", []))
        with self.assertRaises(core.QueueError):
            core.op_limit(state, 5, "kgsmith19", "  ")

    def test_out_of_range_refused(self):
        """AC2: the owner authorized up to five; zero would freeze the queue."""
        state = build(("a", "pending", []))
        for bad in (0, 6, -1, True, "3"):
            with self.assertRaises(core.QueueError, msg=repr(bad)):
                core.op_limit(state, bad, "kgsmith19", "r")

    def test_no_op_refused(self):
        """AC2: a limit that changes nothing would pad history with noise."""
        state = build(("a", "pending", []))
        with self.assertRaises(core.QueueError):
            core.op_limit(state, 1, "kgsmith19", "r")

    def test_lowering_below_active_count_refused(self):
        """AC2: lowering under the number already active would leave the queue over its own cap."""
        state = limited(build(("a", "pending", []), ("b", "pending", []),
                              ("c", "pending", [])), 3)
        for item in ("Q01", "Q02", "Q03"):
            state = start(state, item)
        with self.assertRaises(core.QueueError) as ctx:
            core.op_limit(state, 2, "kgsmith19", "r")
        self.assertIn("3", str(ctx.exception))
        lowered, _ = run(state, core.op_limit(state, 4, "kgsmith19", "r"))
        self.assertEqual(lowered["max_active"], 4)


class ParallelStartTests(unittest.TestCase):
    """AC3: start honors the cap and keeps claims in queue order."""

    def test_cap_one_keeps_the_old_rule(self):
        """AC3: without a raised cap, a second active item is refused exactly as before #302."""
        state = start(build(("a", "pending", []), ("b", "pending", [])), "Q01")
        with self.assertRaises(core.QueueError) as ctx:
            core.op_transition(state, "Q02", "start")
        self.assertIn("Q01", str(ctx.exception))

    def test_up_to_cap_items_start_in_order(self):
        """AC3: with a cap of five, five items run at once; the sixth waits for one to finish."""
        state = limited(build(*[(t, "pending", []) for t in "abcdef"]), 5)
        for item in ("Q01", "Q02", "Q03", "Q04", "Q05"):
            state = start(state, item)
        self.assertEqual([i["status"] for i in state["items"]],
                         ["active"] * 5 + ["pending"])
        with self.assertRaises(core.QueueError) as ctx:
            core.op_transition(state, "Q06", "start")
        self.assertIn("5", str(ctx.exception))
        state, _ = run(state, core.op_transition(state, "Q02", "done", "PR #2 merged at abc"))
        state = start(state, "Q06")
        self.assertEqual(core.find(state, "Q06")["status"], "active")

    def test_cap_counts_active_items_not_position(self):
        """AC3: a cap of two means two active, even when the active ones are not adjacent."""
        state = limited(build(("a", "blocked", []), ("b", "pending", []),
                              ("c", "pending", []), ("d", "pending", [])), 2)
        state = start(start(state, "Q02"), "Q03")
        with self.assertRaises(core.QueueError):
            core.op_transition(state, "Q04", "start")

    def test_later_item_never_starts_ahead_of_an_earlier_pending_one(self):
        """AC3: parallelism is not reordering; skipping a pending earlier item stays out-of-order work."""
        state = limited(build(("a", "pending", []), ("b", "pending", [])), 5)
        with self.assertRaises(core.QueueError) as ctx:
            core.op_transition(state, "Q02", "start")
        self.assertIn("Q01", str(ctx.exception))

    def test_blocked_and_waiting_items_are_still_skippable(self):
        """AC3: the existing legitimate skips keep working alongside active items."""
        state = limited(build(("a", "pending", []), ("b", "blocked", []),
                              ("c", "pending", ["Q02"]), ("d", "pending", [])), 3)
        state = start(state, "Q01")
        state = start(state, "Q04")
        self.assertEqual(core.find(state, "Q04")["status"], "active")

    def test_dependency_still_refused_under_a_raised_cap(self):
        """AC3: a raised cap never lets an item start before what it depends on is done."""
        state = limited(build(("a", "pending", []), ("b", "pending", ["Q01"])), 5)
        state = start(state, "Q01")
        with self.assertRaises(core.QueueError) as ctx:
            core.op_transition(state, "Q02", "start")
        self.assertIn("depends on Q01", str(ctx.exception))


class GuardTests(unittest.TestCase):
    """AC4: claims and PRs match any active item."""

    def _three_active(self):
        state = build(("a", "pending", []), ("b", "pending", []),
                      ("c", "pending", []), ("d", "pending", []))
        for item, ref in zip(state["items"], ("o/r#1", "o/r#2", "o/r#3", "o/r#4")):
            item["refs"] = [ref]
        state = limited(state, 3)
        for item_id in ("Q01", "Q02", "Q03"):
            state = start(state, item_id)
        return state

    def test_pr_guard_accepts_any_active_item(self):
        """AC4: three parallel PRs, each closing its own active item's Issue, all pass."""
        state = self._three_active()
        for ref in ("o/r#1", "o/r#2", "o/r#3"):
            self.assertIn("ok", core.guard_pr(state, [ref], False))
        self.assertIn("ok", core.guard_pr(state, ["o/r#1", "o/r#3"], False))

    def test_pr_guard_still_refuses_non_active_refs(self):
        """AC4: the pending fourth item's Issue is not claimable through a PR yet."""
        with self.assertRaises(core.QueueError):
            core.guard_pr(self._three_active(), ["o/r#4"], False)

    def test_claim_guard_allows_active_and_next(self):
        """AC4: a claim matches any active item, or the next startable one."""
        state = self._three_active()
        for ref in ("o/r#1", "o/r#2", "o/r#3", "o/r#4"):
            self.assertIn("ok", core.guard_claim(state, ref))
        with self.assertRaises(core.QueueError):
            core.guard_claim(state, "o/r#9")

    def test_claim_guard_next_skips_active_items(self):
        """AC4: with items already active, NEXT is the first item that can still be started, not an active one."""
        state = self._three_active()
        self.assertEqual(core.next_startable(state)["id"], "Q04")
        self.assertEqual(core.next_item(state)["id"], "Q01")


class SchemaAndRenderTests(unittest.TestCase):
    """AC5: the schema and the rendered checklist show the cap."""

    @classmethod
    def setUpClass(cls):
        path = WORKTREE / "tools" / "queue_v2.schema.json"
        cls.schema = json.loads(path.read_text(encoding="utf-8"))

    def test_schema_agrees_with_core_on_the_cap(self):
        """AC5: schema and validator must accept and reject the same caps."""
        base = build(("a", "pending", []))
        cases = [(None, True)] + [(n, True) for n in (1, 5)] + [
            (n, False) for n in (0, 6, True, "5")]
        for value, expected in cases:
            state = copy.deepcopy(base)
            if value is not None:
                state["max_active"] = value
            try:
                core.validate(state)
                core_ok = True
            except core.FormatError:
                core_ok = False
            self.assertEqual((_schema_check(self.schema, state), core_ok),
                             (expected, expected), repr(value))
        prop = self.schema["properties"]["max_active"]
        self.assertEqual((prop["minimum"], prop["maximum"]), (1, core.MAX_PARALLEL))
        self.assertNotIn("max_active", self.schema["required"])

    def test_render_shows_cap_and_every_active_item(self):
        """AC5: the owner reads how many may run at once and which are running."""
        state = limited(build(("a", "pending", []), ("b", "pending", []),
                              ("c", "pending", [])), 3)
        state = start(start(state, "Q01"), "Q02")
        body = core.render_markdown(state)
        self.assertIn("Parallel: up to 3 active (2 active now)", body)
        q03 = [line for line in body.splitlines() if "**Q03**" in line][0]
        self.assertIn("NEXT", q03)
        self.assertEqual(core.parse_block(body), state)

    def test_render_without_cap_has_no_parallel_line(self):
        """AC5: legacy queues render exactly as before."""
        body = core.render_markdown(build(("a", "pending", [])))
        self.assertNotIn("Parallel:", body)


class CliTests(unittest.TestCase):
    """AC2/AC5 through work_queue.py."""

    def test_limit_command_owner_only_and_logged(self):
        """AC2: `limit` refuses a non-owner, records the owner's change, and start then honors it."""
        adapter = seeded("a", "b", "c")
        code, _, _ = cli_run("limit", "3", "--authorized-by", "someone",
                             "--reason", "r", adapter=adapter)
        self.assertEqual(code, cli.EXIT_REFUSED)
        code, out, _ = cli_run("limit", "3", "--authorized-by", "kgsmith19",
                               "--reason", "owner authorized parallel PRs", adapter=adapter)
        self.assertEqual(code, 0, out)
        for item in ("Q01", "Q02", "Q03"):
            self.assertEqual(cli_run("start", item, adapter=adapter)[0], 0)
        _, out, _ = cli_run("history", adapter=adapter)
        self.assertIn("limit", out)
        self.assertIn("owner authorized parallel PRs", out)

    def test_show_reports_cap_and_next_skips_active(self):
        """AC5: `show` states the cap; `next` names the next item to start, not one already running."""
        adapter = seeded("a", "b", "c")
        cli_run("limit", "2", "--authorized-by", "kgsmith19", "--reason", "r", adapter=adapter)
        cli_run("start", "Q01", adapter=adapter)
        _, out, _ = cli_run("show", adapter=adapter)
        self.assertIn("parallel: up to 2 active (1 active now)", out)
        _, out, _ = cli_run("next", adapter=adapter)
        self.assertTrue(out.startswith("Q02"), out)

    def test_next_at_cap_one_is_unchanged(self):
        """AC5: legacy single-active queues keep printing the active item as next."""
        adapter = seeded("a", "b")
        cli_run("start", "Q01", adapter=adapter)
        _, out, _ = cli_run("next", adapter=adapter)
        self.assertTrue(out.startswith("Q01"), out)
        _, out, _ = cli_run("show", adapter=adapter)
        self.assertNotIn("parallel:", out)


if __name__ == "__main__":
    unittest.main()
