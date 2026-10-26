"""Tests for the v1 -> v2 queue migration (Issue #285, phase 2 of #283).

Strategy: build a v1 Issue body with the v1 renderer (the exact format
live on #277), migrate it through the fake GitHub REST layer, and assert
the result three ways: the v2 state mirrors every v1 item, the history
reconstructs the v1 state byte-for-byte, and a dry run writes nothing.
The handoff comment is migrated only when unambiguous and owner-authored.
"""

import copy
import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

WORKTREE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKTREE / "tools"))
sys.path.insert(0, str(WORKTREE / "tests"))
import queue_core as core  # noqa: E402
import queue_store as store  # noqa: E402
import work_queue as cli  # noqa: E402
from test_queue_store import FakeGitHub  # noqa: E402

CTX = {"actor": "kgsmith19", "harness": "shell", "provider": "unknown",
       "at": "2026-10-26T20:00:00Z"}
HANDOFF_MARKER = "<!-- agent-engineering-standard:handoff:v1 -->"


def v1_state():
    return {"version": 1, "next_id": 6, "items": [
        {"id": "Q01", "title": "done first", "refs": ["o/r#1"], "status": "done",
         "note": "PR #9 merged at abc1234"},
        {"id": "Q02", "title": "owner gated", "refs": ["o/r#2"],
         "status": "blocked", "note": "waits on owner"},
        {"id": "Q05", "title": "moved earlier", "refs": [], "status": "active",
         "note": ""},
        {"id": "Q03", "title": "done later ✓", "refs": ["o/r#3", "o/r#4"],
         "status": "done", "note": "PR #10 merged"},
        {"id": "Q04", "title": "pending", "refs": ["o/r#5"], "status": "pending",
         "note": "n"},
    ]}


def github_v1(handoff="## 🧭 Session handoff\nstep 1\n"):
    github = FakeGitHub(cli.render(v1_state()))
    github.comments.append((11, "unrelated comment"))
    if handoff is not None:
        github.comments.append((12, HANDOFF_MARKER + "\n" + handoff))
    return github


def migrate(github, dry_run=False, owner="kgsmith19"):
    adapter = store.GitHubIssueAdapter("o/r", 7, http=github)
    return store.migrate_issue(adapter, cli.parse, owner, CTX, dry_run=dry_run,
                               handoff_marker=HANDOFF_MARKER)


class OpMigrateTests(unittest.TestCase):
    """AC1: the pure mapping is lossless."""

    def test_live_items_keep_order_and_fields(self):
        """Every unfinished v1 item keeps id, title, refs, status, note and relative order."""
        state, _ = core.op_migrate(v1_state(), "kgsmith19")
        self.assertEqual([i["id"] for i in state["items"]], ["Q02", "Q05", "Q04"])
        for item in state["items"]:
            v1 = [i for i in v1_state()["items"] if i["id"] == item["id"]][0]
            self.assertEqual({k: item[k] for k in v1}, v1)
            self.assertEqual(item["depends_on"], [])
        self.assertEqual(state["next_id"], 6)
        self.assertEqual(state["owner"], "kgsmith19")

    def test_done_items_archived_with_their_records(self):
        """Done items leave live state but keep id and evidence in history."""
        state, events = core.op_migrate(v1_state(), "kgsmith19")
        self.assertEqual(state["archived"], ["Q01", "Q03"])
        archive = [e for e in events if e["op"] == "archive"]
        self.assertEqual([e["item"] for e in archive], ["Q01", "Q03"])
        self.assertEqual(archive[1]["from"]["note"], "PR #10 merged")

    def test_history_reconstructs_v1_exactly(self):
        """AC1: the migrate event holds the v1 state verbatim, so nothing is ever lost."""
        state, events = core.seal(*core.op_migrate(v1_state(), "kgsmith19"), CTX)
        self.assertEqual(core.v1_from_history(core.chain(events, state)), v1_state())
        core.check_migration(v1_state(), state, events)

    def test_check_migration_detects_any_loss(self):
        """A migration that drops, reorders or alters an item must fail closed before writing."""
        state, events = core.seal(*core.op_migrate(v1_state(), "kgsmith19"), CTX)
        breakers = [
            lambda s: s["items"].pop(0),
            lambda s: s["items"].reverse(),
            lambda s: s["items"][0].update(note="changed"),
            lambda s: s["archived"].pop(),
            lambda s: s.update(next_id=7),
        ]
        for breaker in breakers:
            bad = copy.deepcopy(state)
            breaker(bad)
            with self.assertRaises(core.FormatError):
                core.check_migration(v1_state(), bad, events)

    def test_item_over_v2_limits_refused_not_truncated(self):
        """AC1: a v1 note longer than the v2 cap is refused, never silently truncated."""
        v1 = v1_state()
        v1["items"][1]["note"] = "x" * (core.LIMITS["note"] + 1)
        with self.assertRaises(core.QueueError) as ctx:
            core.op_migrate(v1, "kgsmith19")
        self.assertIn("Q02", str(ctx.exception))


class MigrateIssueTests(unittest.TestCase):
    """AC1-AC3 through the github-issue adapter."""

    def test_dry_run_writes_nothing(self):
        """AC1: the dry run must leave the Issue and its comments untouched."""
        github = github_v1()
        before = (github.body, list(github.comments))
        plan = migrate(github, dry_run=True)
        self.assertEqual((github.body, github.comments), before)
        self.assertEqual(github.writes(), [])
        self.assertEqual(plan["state"]["archived"], ["Q01", "Q03"])
        self.assertEqual(plan["handoff_text"], HANDOFF_MARKER + "\n## 🧭 Session handoff\nstep 1\n")

    def test_dry_run_plan_is_what_gets_written(self):
        """AC1: the reviewed dry-run state must be exactly the state migrate writes."""
        plan = migrate(github_v1(), dry_run=True)
        github = github_v1()
        written = migrate(github)
        self.assertEqual(written["state"], plan["state"])
        self.assertEqual(core.parse_block(github.body), plan["state"])

    def test_migrate_writes_v2_with_history_and_handoff(self):
        """AC2/AC3: after migrate, v2 reads back with the same next item and the handoff."""
        github = github_v1()
        migrate(github)
        adapter = store.GitHubIssueAdapter("o/r", 7, http=github)
        state, _ = adapter.load()
        log = core.chain(adapter.events(), state)
        self.assertEqual([e["op"] for e in log][:1], ["migrate"])
        self.assertEqual(core.next_item(state)["id"], "Q05")
        self.assertEqual(core.handoff_text(state, log),
                         HANDOFF_MARKER + "\n## 🧭 Session handoff\nstep 1\n")
        self.assertEqual(core.v1_from_history(log), v1_state())

    def test_v1_handoff_comment_marked_superseded_but_kept(self):
        """AC3: the v1 comment is visibly superseded and its original text survives."""
        github = github_v1()
        migrate(github)
        body = dict(github.comments)[12]
        self.assertTrue(body.startswith(store.SUPERSEDED_BANNER))
        self.assertIn("step 1", body)
        self.assertEqual(dict(github.comments)[11], "unrelated comment")

    def test_refuses_already_v2(self):
        """AC2: migrating twice must be refused instead of rewriting history."""
        github = github_v1()
        migrate(github)
        body = github.body
        with self.assertRaises(core.QueueError):
            migrate(github)
        self.assertEqual(github.body, body)

    def test_refuses_on_concurrent_change(self):
        """AC2: compare-and-swap: a v1 write landing during migration aborts it."""
        github = github_v1()
        original = github.__call__

        class Racing:
            def __init__(self):
                self.raced = False

            def __call__(self, method, path, payload=None):
                if method == "POST" and not self.raced:
                    self.raced = True
                    github.body = github.body.replace("pending", "pending ")
                return original(method, path, payload)

        adapter = store.GitHubIssueAdapter("o/r", 7, http=Racing())
        with self.assertRaises(store.ConflictError):
            store.migrate_issue(adapter, cli.parse, "kgsmith19", CTX,
                                handoff_marker=HANDOFF_MARKER)
        self.assertNotIn(core.MARKER, github.body)

    def test_ambiguous_or_foreign_handoff_refused(self):
        """AC3: two handoff comments, or one not by the owner, must not be guessed between."""
        github = github_v1()
        github.comments.append((13, HANDOFF_MARKER + "\nsecond"))
        with self.assertRaises(core.QueueError):
            migrate(github, dry_run=True)
        github = github_v1()
        github.authors[12] = "someone-else"
        plan = migrate(github, dry_run=True)
        self.assertIsNone(plan["handoff_text"])

    def test_no_handoff_comment_is_fine(self):
        """A queue Issue without a handoff migrates with no handoff set."""
        github = github_v1(handoff=None)
        plan = migrate(github)
        self.assertIsNone(plan["state"]["handoff"])

    def test_malformed_v1_refused(self):
        """A corrupt v1 body must fail closed, never be migrated as empty."""
        github = FakeGitHub("<!-- agent-engineering-standard:queue:v1 -->\n```json\n{bad\n```")
        with self.assertRaises(core.FormatError):
            migrate(github, dry_run=True)
        self.assertEqual(github.writes(), [])


class MigrateCliTests(unittest.TestCase):
    """The CLI surface for the migration."""

    def _run(self, github, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["--repo", "o/r", "--issue", "7", "migrate", *argv],
                            http=github, env={"AES_QUEUE_ACTOR": "kgsmith19"},
                            now="2026-10-26T21:00:00Z")
        return code, out.getvalue(), err.getvalue()

    def test_dry_run_prints_plan_and_writes_nothing(self):
        """AC1: the dry run prints every item's disposition, the v2 state and the handoff."""
        github = github_v1()
        code, out, _ = self._run(github, "--dry-run")
        self.assertEqual(code, 0)
        self.assertEqual(github.writes(), [])
        for line in ("Q01 done -> archived", "Q02 blocked -> live #1",
                     "Q05 active -> live #2", "Q04 pending -> live #3",
                     "lossless: v1 state reconstructs exactly"):
            self.assertIn(line, out)
        state_json = out.split("--- v2 state ---\n")[1].split("\n--- ")[0]
        self.assertEqual(json.loads(state_json)["archived"], ["Q01", "Q03"])
        self.assertIn("step 1", out.split("--- handoff")[1])

    def test_migrate_then_next_reads_v2(self):
        """AC2/AC4: after migrate the same CLI serves the Issue as v2 with the same next item."""
        github = github_v1()
        self.assertEqual(self._run(github)[0], 0)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(["--repo", "o/r", "--issue", "7", "next"], http=github,
                            env={}, now="2026-10-26T21:00:00Z")
        self.assertEqual((code, out.getvalue().splitlines()[0]),
                         (0, "Q05 [active] moved earlier — no refs"))
        self.assertEqual(self._run(github)[0], cli.EXIT_REFUSED)

    def test_migrate_needs_github_issue_backend(self):
        """v1 queues only ever lived in an Issue; migrate on git-file is a usage error."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["--backend", "git-file", "--path", "/nonexistent",
                             "migrate", "--dry-run"], env={}, now="2026-10-26T21:00:00Z")
        self.assertEqual(code, cli.EXIT_REFUSED)
        self.assertIn("github-issue", err.getvalue())


if __name__ == "__main__":
    unittest.main()
