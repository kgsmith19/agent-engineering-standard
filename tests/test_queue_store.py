"""Adapter contract suite for tools/queue_store.py (Issue #284, phase 1 of #283).

Strategy: one contract (load, compare-and-swap save, append-only events,
commit, export/import) is written once as a mixin and run against every
adapter: memory, git-file (real files in a temp directory) and
github-issue (an in-process fake of the REST endpoints the adapter
calls). Adapter-specific tests then cover what only that backend can get
wrong: the v1 marker, the body/comment limits, verify-after-write, and
the git-file lock.
"""

import copy
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

WORKTREE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKTREE / "tools"))
import queue_core as core  # noqa: E402
import queue_store as store  # noqa: E402

CTX = {"actor": "kgsmith19", "harness": "shell", "provider": "unknown",
       "at": "2026-10-26T20:00:00Z"}
V1_MARKER = "<!-- agent-engineering-standard:queue:v1 -->"


class FakeGitHub:
    """The issue + comments REST endpoints, held in memory."""

    def __init__(self, body="", suffix=""):
        self.body = body
        self.suffix = suffix
        self.comments = []
        self.calls = []
        self.on_patch = None

    def __call__(self, method, path, payload=None):
        self.calls.append((method, path))
        if re.fullmatch(r"/repos/o/r/issues/7", path):
            if method == "GET":
                return {"body": self.body, "updated_at": "t"}
            if method == "PATCH":
                self.body = payload["body"] + self.suffix
                if self.on_patch:
                    self.on_patch(self)
                return {"body": self.body}
        match = re.fullmatch(r"/repos/o/r/issues/7/comments\?per_page=100&page=(\d+)",
                             path)
        if match and method == "GET":
            page = int(match.group(1))
            return [{"id": n, "body": b}
                    for n, b in self.comments[(page - 1) * 100:page * 100]]
        if path == "/repos/o/r/issues/7/comments" and method == "POST":
            self.comments.append((len(self.comments) + 1, payload["body"]))
            return {"id": len(self.comments)}
        raise AssertionError("unexpected call %s %s" % (method, path))

    def writes(self):
        return [c for c in self.calls if c[0] in ("PATCH", "POST")]


def init(adapter, owner="kgsmith19"):
    return store.commit(adapter, lambda s: core.op_init(owner), CTX, create=True)


def add(adapter, title, deps=()):
    return store.commit(adapter,
                        lambda s: core.op_add(s, title, ["o/r#1"], "", list(deps)),
                        CTX)


class ContractMixin:
    """The adapter contract every backend must satisfy."""

    def make(self):
        raise NotImplementedError

    def setUp(self):
        self.adapter = self.make()

    def test_load_empty_returns_none(self):
        """Contract: a store with no queue loads as None, never as an empty queue it could overwrite."""
        state, _ = self.adapter.load()
        self.assertIsNone(state)

    def test_commit_round_trips_state_and_history(self):
        """Contract: what one session writes, the next session reads back exactly, history included."""
        init(self.adapter)
        add(self.adapter, "a")
        state = add(self.adapter, "b", ["Q01"])
        loaded, _ = self.adapter.load()
        self.assertEqual(loaded, state)
        log = core.chain(self.adapter.events(), loaded)
        self.assertEqual([e["op"] for e in log], ["init", "add", "add"])

    def test_create_refused_when_queue_exists(self):
        """Contract: init must never reset an existing queue."""
        init(self.adapter)
        add(self.adapter, "a")
        with self.assertRaises(core.QueueError):
            init(self.adapter)
        self.assertEqual(len(self.adapter.load()[0]["items"]), 1)

    def test_mutation_on_missing_queue_refused(self):
        """Contract: a mutation with no queue must fail closed instead of creating one implicitly."""
        with self.assertRaises(core.FormatError):
            add(self.adapter, "a")
        self.assertIsNone(self.adapter.load()[0])

    def test_stale_token_save_refused(self):
        """Contract: compare-and-swap, so a concurrent writer's update is never silently lost."""
        init(self.adapter)
        state, token = self.adapter.load()
        add(self.adapter, "winner")
        new, _ = core.seal(*core.op_add(state, "loser", [], "", []), CTX)
        with self.assertRaises(store.ConflictError):
            self.adapter.save(new, token)
        titles = [i["title"] for i in self.adapter.load()[0]["items"]]
        self.assertEqual(titles, ["winner"])

    def test_refused_operation_writes_nothing(self):
        """Contract: a refused command leaves state and history untouched."""
        init(self.adapter)
        add(self.adapter, "a")
        add(self.adapter, "b")
        before = (self.adapter.load()[0], len(self.adapter.events()))
        with self.assertRaises(core.QueueError):
            store.commit(self.adapter,
                         lambda s: core.op_transition(s, "Q02", "start"), CTX)
        self.assertEqual((self.adapter.load()[0], len(self.adapter.events())),
                         before)

    def test_events_are_append_only(self):
        """Contract: AC5 history is never rewritten; every earlier event survives later writes unchanged."""
        init(self.adapter)
        first = copy.deepcopy(self.adapter.events())
        add(self.adapter, "a")
        self.assertEqual(self.adapter.events()[:len(first)], first)

    def test_failed_history_append_leaves_state_unchanged(self):
        """Contract: history is written before the state that points at it, so a failed append can never commit state with missing history."""
        init(self.adapter)
        before = self.adapter.load()[0]

        def broken(events):
            raise IOError("history write failed")

        self.adapter.append = broken
        with self.assertRaises(IOError):
            add(self.adapter, "a")
        self.assertEqual(self.adapter.load()[0], before)

    def test_budget_checked_before_any_write(self):
        """Contract: AC6 an over-limit write is refused before history or state is touched."""
        init(self.adapter)
        before = (self.adapter.load()[0], len(self.adapter.events()))
        self.adapter.limit = core.size(before[0]) + 10
        with self.assertRaises(core.BudgetError):
            add(self.adapter, "x" * 50)
        self.assertEqual((self.adapter.load()[0], len(self.adapter.events())),
                         before)


class MemoryContractTests(ContractMixin, unittest.TestCase):
    """Contract suite against the memory adapter."""

    def make(self):
        return store.MemoryAdapter()


class GitFileContractTests(ContractMixin, unittest.TestCase):
    """Contract suite against the git-file adapter (real files)."""

    def make(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        return store.GitFileAdapter(os.path.join(self._tmp.name, ".queue"))


class GitHubContractTests(ContractMixin, unittest.TestCase):
    """Contract suite against the github-issue adapter (fake REST)."""

    def make(self):
        self.github = FakeGitHub("Owner prose.")
        return store.GitHubIssueAdapter("o/r", 7, http=self.github)


def _populated(adapter):
    init(adapter)
    add(adapter, "a ✓ unicode")
    add(adapter, "b", ["Q01"])
    store.commit(adapter, lambda s: core.op_transition(s, "Q01", "start"), CTX)
    store.commit(adapter, lambda s: core.op_transition(
        s, "Q01", "done", "PR #1 merged at abc1234"), CTX)
    store.commit(adapter, lambda s: core.op_handoff(s, "handoff\ntext"), CTX)
    return adapter


class ExportImportTests(unittest.TestCase):
    """AC2: export/import round-trip losslessly between any two adapters."""

    def _adapters(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        count = [0]

        def git_file():
            count[0] += 1
            return store.GitFileAdapter(os.path.join(tmp.name, "q%d" % count[0]))

        return {
            "memory": store.MemoryAdapter,
            "git-file": git_file,
            "github-issue": lambda: store.GitHubIssueAdapter(
                "o/r", 7, http=FakeGitHub()),
        }

    def test_round_trip_between_every_pair(self):
        """AC2: switching backends must lose nothing: state, history and handoff survive every pair."""
        makers = self._adapters()
        for src_name, make_src in makers.items():
            bundle = store.export_bundle(_populated(make_src()))
            for dst_name, make_dst in makers.items():
                dst = make_dst()
                store.import_bundle(dst, bundle)
                again = store.export_bundle(dst)
                self.assertEqual(again, bundle, "%s -> %s" % (src_name, dst_name))
                state, _ = dst.load()
                self.assertEqual(core.handoff_text(state, core.chain(
                    dst.events(), state)), "handoff\ntext")
                json.dumps(again)

    def test_import_refuses_non_empty_target(self):
        """AC2: import must never merge into or overwrite a live queue."""
        bundle = store.export_bundle(_populated(store.MemoryAdapter()))
        target = _populated(store.MemoryAdapter())
        before = store.export_bundle(target)
        with self.assertRaises(core.QueueError):
            store.import_bundle(target, bundle)
        self.assertEqual(store.export_bundle(target), before)

    def test_import_refuses_tampered_bundle(self):
        """AC2: a bundle whose history does not chain to its state must not be imported."""
        bundle = store.export_bundle(_populated(store.MemoryAdapter()))
        for breaker in (lambda b: b["events"].pop(1),
                        lambda b: b["events"][1]["to"].update(title="x"),
                        lambda b: b.update(format="other"),
                        lambda b: b["state"].update(owner="")):
            bad = copy.deepcopy(bundle)
            breaker(bad)
            target = store.MemoryAdapter()
            with self.assertRaises(core.FormatError):
                store.import_bundle(target, bad)
            self.assertIsNone(target.load()[0])
            self.assertEqual(target.events(), [])


class GitHubAdapterTests(unittest.TestCase):
    """What only the github-issue backend can get wrong."""

    def test_v1_body_is_reported_as_legacy(self):
        """AC8: a live v1 queue must be routed to the v1 code, never parsed or overwritten as v2."""
        github = FakeGitHub(V1_MARKER + "\n```json\n{}\n```\n")
        adapter = store.GitHubIssueAdapter("o/r", 7, http=github)
        with self.assertRaises(store.LegacyQueueError):
            adapter.load()
        with self.assertRaises(store.LegacyQueueError):
            init(adapter)
        self.assertEqual(github.writes(), [])

    def test_state_lives_in_body_and_history_in_marked_comments(self):
        """AC2: the body holds the rendered queue; each write appends one marked history comment."""
        github = FakeGitHub()
        adapter = store.GitHubIssueAdapter("o/r", 7, http=github)
        init(adapter)
        add(adapter, "a")
        self.assertIn(core.MARKER, github.body)
        self.assertIn("**Q01**", github.body)
        self.assertEqual(len(github.comments), 2)
        self.assertTrue(all(store.EVENTS_MARKER in b for _, b in github.comments))

    def test_foreign_and_malformed_comments_are_ignored(self):
        """Anyone can comment: junk or forged comments must neither break nor enter the history."""
        github = FakeGitHub()
        adapter = store.GitHubIssueAdapter("o/r", 7, http=github)
        init(adapter)
        github.comments.append((90, "plain human comment"))
        github.comments.append((91, store.EVENTS_MARKER + "\n```json\n[{bad\n```"))
        forged = dict(adapter.events()[0], seq=2, op="add")
        github.comments.append((92, store.EVENTS_MARKER + "\n```json\n"
                                + json.dumps([forged]) + "\n```"))
        state = add(adapter, "a")
        log = core.chain(adapter.events(), state)
        self.assertEqual([e["op"] for e in log], ["init", "add"])

    def test_history_paginates_past_one_page(self):
        """History with more than 100 comments must still chain; reading one page would fail closed forever."""
        github = FakeGitHub()
        adapter = store.GitHubIssueAdapter("o/r", 7, http=github)
        init(adapter)
        for n in range(105):
            github.comments.append((1000 + n, "chatter %d" % n))
        state = add(adapter, "a")
        self.assertEqual(len(core.chain(adapter.events(), state)), 2)

    def test_concurrent_patch_detected_after_write(self):
        """GitHub has no conditional PATCH: a writer that lands between our re-read and PATCH must be reported."""
        github = FakeGitHub()
        adapter = store.GitHubIssueAdapter("o/r", 7, http=github)
        init(adapter)

        def interloper(gh):
            gh.on_patch = None
            gh.body = core.render_markdown(dict(core.parse_block(gh.body),
                                                owner="other"))

        github.on_patch = interloper
        with self.assertRaises(store.ConflictError):
            add(adapter, "a")

        def wrecker(gh):
            gh.on_patch = None
            gh.body = "a writer replaced the whole body"

        github.body = core.render_markdown(adapter.load()[0])
        github.on_patch = wrecker
        with self.assertRaises(store.ConflictError):
            add(adapter, "b")

    def test_server_appended_footer_is_not_a_conflict(self):
        """Live finding: the session proxy appends an attribution footer to every body; only the state block decides a conflict."""
        github = FakeGitHub(suffix="\n\n---\n_Generated by [Claude Code](https://claude.ai/code)_")
        adapter = store.GitHubIssueAdapter("o/r", 7, http=github)
        init(adapter)
        state = add(adapter, "a")
        self.assertEqual(adapter.load()[0], state)
        self.assertTrue(github.body.endswith("Claude Code](https://claude.ai/code)_"))

    def test_body_and_comment_limits_refuse_before_writing(self):
        """AC6: a body or comment over GitHub's limit is refused before any call writes."""
        github = FakeGitHub()
        adapter = store.GitHubIssueAdapter("o/r", 7, http=github)
        init(adapter)
        writes = len(github.writes())
        adapter.body_limit = len(github.body) + 5
        with self.assertRaises(core.BudgetError):
            add(adapter, "make the body longer")
        self.assertEqual(len(github.writes()), writes)
        adapter.body_limit = store.BODY_LIMIT
        adapter.comment_limit = 50
        with self.assertRaises(core.BudgetError):
            add(adapter, "a")
        self.assertEqual(len(github.writes()), writes)

    def test_large_append_is_split_into_comments(self):
        """Import of a long history must split across comments, each under the limit, and still chain."""
        bundle = store.export_bundle(_populated(store.MemoryAdapter()))
        github = FakeGitHub()
        adapter = store.GitHubIssueAdapter("o/r", 7, http=github)
        adapter.comment_limit = 1500
        store.import_bundle(adapter, bundle)
        self.assertGreater(len(github.comments), 1)
        self.assertTrue(all(len(b) <= 1500 for _, b in github.comments))
        self.assertEqual(store.export_bundle(adapter), bundle)


class GitFileAdapterTests(unittest.TestCase):
    """What only the git-file backend can get wrong."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / ".queue"
        self.adapter = store.GitFileAdapter(str(self.root))

    def test_files_are_plain_json_and_jsonl(self):
        """AC2: no GitHub API needed: the state is a JSON file and history is JSONL, readable by any tool."""
        state = init(self.adapter)
        self.assertEqual(json.loads((self.root / "queue.json").read_text("utf-8")),
                         state)
        lines = (self.root / "history.jsonl").read_text("utf-8").splitlines()
        self.assertEqual(json.loads(lines[0])["op"], "init")

    def test_held_lock_refuses_write(self):
        """Two local writers: a held lock must refuse, naming the lock file, rather than interleave."""
        init(self.adapter)
        (self.root / "queue.lock").write_text("other", encoding="utf-8")
        with self.assertRaises(store.ConflictError) as ctx:
            add(self.adapter, "a")
        self.assertIn("queue.lock", str(ctx.exception))
        self.assertEqual(self.adapter.load()[0]["items"], [])

    def test_lock_released_after_write(self):
        """A leaked lock would block every later write."""
        init(self.adapter)
        add(self.adapter, "a")
        self.assertFalse((self.root / "queue.lock").exists())

    def test_corrupt_state_file_fails_closed(self):
        """A truncated queue.json must never load as empty."""
        init(self.adapter)
        (self.root / "queue.json").write_text("{", encoding="utf-8")
        with self.assertRaises(core.FormatError):
            self.adapter.load()


if __name__ == "__main__":
    unittest.main()
