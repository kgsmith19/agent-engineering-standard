"""CLI tests for the v2 queue in tools/work_queue.py (Issue #284, phase 1 of #283).

Strategy: drive ``main`` end to end. A v2 adapter is injected, or a fake
GitHub REST layer, or real files through the git-file backend selected
by one environment value. Each test asserts the exit code and what was
written, including that a refused command wrote nothing. The context
(actor, harness, provider) comes from an explicit env mapping, so
detection is tested without touching the process environment.
"""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

WORKTREE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKTREE / "tools"))
import queue_core as core  # noqa: E402
import queue_store as store  # noqa: E402
import work_queue as cli  # noqa: E402
from test_queue_store import FakeGitHub, V1_MARKER  # noqa: E402

NOW = "2026-10-26T21:00:00Z"
ENV = {"AES_QUEUE_ACTOR": "kgsmith19"}


def run(*argv, adapter=None, http=None, env=None, stdin=""):
    out, err = io.StringIO(), io.StringIO()
    old_stdin = sys.stdin
    sys.stdin = io.StringIO(stdin)
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(argv), adapter=adapter, http=http,
                            env=dict(ENV if env is None else env), now=NOW)
    finally:
        sys.stdin = old_stdin
    return code, out.getvalue(), err.getvalue()


def seeded(*titles):
    adapter = store.MemoryAdapter()
    assert run("init", "--owner", "kgsmith19", adapter=adapter)[0] == 0
    for title in titles:
        assert run("add", "--title", title, "--ref", "o/r#1",
                   adapter=adapter)[0] == 0
    return adapter


class V1SubcommandsOnV2Tests(unittest.TestCase):
    """AC8: v1 subcommand names and flags keep working on v2 state."""

    def test_v1_flow_end_to_end(self):
        """AC8: add/next/start/block/unblock/edit/done must behave on v2 the way sessions already use them."""
        adapter = seeded("a", "b")
        code, out, _ = run("next", adapter=adapter)
        self.assertEqual((code, out.splitlines()[0]),
                         (0, "Q01 [pending] a — o/r#1"))
        self.assertEqual(run("start", "Q01", adapter=adapter)[0], 0)
        self.assertEqual(run("block", "Q01", "--reason", "owner", adapter=adapter)[0], 0)
        self.assertEqual(run("unblock", "Q01", adapter=adapter)[0], 0)
        self.assertEqual(run("edit", "Q01", "--note", "n", adapter=adapter)[0], 0)
        self.assertEqual(run("start", "Q01", adapter=adapter)[0], 0)
        self.assertEqual(run("done", "Q01", "--evidence", "PR #1 at abc",
                             adapter=adapter)[0], 0)
        code, out, _ = run("show", adapter=adapter)
        self.assertEqual(code, 0)
        self.assertIn("Q02 [pending] b", out)
        self.assertIn("archived: Q01", out)

    def test_next_on_exhausted_queue_exits_3(self):
        """Harnesses branch on exit 3; zero on empty would loop them on nothing."""
        code, out, _ = run("next", adapter=seeded())
        self.assertEqual((code, out.strip()), (cli.EXIT_EMPTY, "QUEUE EMPTY"))

    def test_refused_start_exits_1_and_writes_nothing(self):
        """Order guard via the CLI: refused, names the blocker, nothing written."""
        adapter = seeded("a", "b")
        before = store.export_bundle(adapter)
        code, _, err = run("start", "Q02", adapter=adapter)
        self.assertEqual(code, cli.EXIT_REFUSED)
        self.assertIn("Q01", err)
        self.assertEqual(store.export_bundle(adapter), before)


class NewSubcommandTests(unittest.TestCase):
    """AC3/AC4/AC5/AC7 surfaced through the CLI."""

    def test_depends_on_flag(self):
        """AC4: dependencies set from the CLI gate start and show up in next."""
        adapter = seeded("a")
        self.assertEqual(run("add", "--title", "b", "--depends-on", "Q01",
                             adapter=adapter)[0], 0)
        run("block", "Q01", "--reason", "owner", adapter=adapter)
        code, _, err = run("start", "Q02", adapter=adapter)
        self.assertEqual(code, cli.EXIT_REFUSED)
        self.assertIn("Q01", err)
        self.assertEqual(run("next", adapter=adapter)[0], cli.EXIT_EMPTY)

    def test_move_requires_owner_and_is_logged(self):
        """AC3: only an owner-authorized, reasoned move reorders, and history shows it."""
        adapter = seeded("a", "b", "c")
        code, _, _ = run("move", "Q03", "--after", "Q01", "--authorized-by",
                         "someone", "--reason", "r", adapter=adapter)
        self.assertEqual(code, cli.EXIT_REFUSED)
        code, _, _ = run("move", "Q03", "--after", "Q01", "--authorized-by",
                         "kgsmith19", "--reason", "owner said", adapter=adapter)
        self.assertEqual(code, 0)
        _, out, _ = run("show", adapter=adapter)
        order = [line.split()[0] for line in out.splitlines() if line.startswith("Q")]
        self.assertEqual(order, ["Q01", "Q03", "Q02"])
        _, out, _ = run("history", "Q03", adapter=adapter)
        self.assertIn("move", out)
        self.assertIn("owner said", out)

    def test_history_records_context(self):
        """AC5: history shows who, when, harness and provider for each event."""
        env = {"AES_QUEUE_ACTOR": "kgsmith19", "CLAUDECODE": "1"}
        adapter = store.MemoryAdapter()
        run("init", "--owner", "kgsmith19", adapter=adapter, env=env)
        run("add", "--title", "a", adapter=adapter, env=env)
        code, out, _ = run("history", adapter=adapter)
        self.assertEqual(code, 0)
        line = out.splitlines()[-1]
        for part in ("2", NOW, "kgsmith19", "claude-code/anthropic", "add", "Q01"):
            self.assertIn(part, line)

    def test_handoff_set_and_show(self):
        """AC7: the handoff a session writes is printed verbatim to the next one."""
        adapter = seeded()
        code, out, _ = run("handoff", "show", adapter=adapter)
        self.assertEqual((code, out.strip()), (cli.EXIT_EMPTY, "NO HANDOFF"))
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False,
                                         encoding="utf-8") as handle:
            handle.write("## Handoff\n- step ✓\n")
        self.addCleanup(os.unlink, handle.name)
        self.assertEqual(run("handoff", "set", "--file", handle.name,
                             adapter=adapter)[0], 0)
        self.assertEqual(run("handoff", "show", adapter=adapter)[1],
                         "## Handoff\n- step ✓\n")
        self.assertEqual(run("handoff", "set", "--file", "-", adapter=adapter,
                             stdin="from stdin")[0], 0)
        self.assertEqual(run("handoff", "show", adapter=adapter)[1], "from stdin")

    def test_export_import_via_files(self):
        """AC2: export to a file and import into an empty backend reproduces the queue."""
        source = seeded("a", "b")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bundle.json")
            self.assertEqual(run("export", "--out", path, adapter=source)[0], 0)
            target = store.MemoryAdapter()
            self.assertEqual(run("import", "--file", path, adapter=target)[0], 0)
            self.assertEqual(store.export_bundle(target), store.export_bundle(source))
            self.assertEqual(run("import", "--file", path, adapter=target)[0],
                             cli.EXIT_REFUSED)

    def test_secret_in_note_refused(self):
        """No secrets: a token in a note is refused and nothing is written."""
        adapter = seeded("a")
        before = store.export_bundle(adapter)
        code, _, err = run("edit", "Q01", "--note", "ghp_" + "x" * 36,
                           adapter=adapter)
        self.assertEqual(code, cli.EXIT_REFUSED)
        self.assertNotIn("x" * 36, err)
        self.assertEqual(store.export_bundle(adapter), before)


class BackendSelectionTests(unittest.TestCase):
    """AC2: switching backend is one config value."""

    def test_git_file_backend_from_env(self):
        """AC2: AES_QUEUE_BACKEND=git-file stores the queue in plain files with no GitHub call."""
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(ENV, AES_QUEUE_BACKEND="git-file",
                       AES_QUEUE_PATH=os.path.join(tmp, "q"))
            self.assertEqual(run("init", "--owner", "kgsmith19", env=env)[0], 0)
            self.assertEqual(run("add", "--title", "a", env=env)[0], 0)
            self.assertTrue(os.path.exists(os.path.join(tmp, "q", "queue.json")))
            self.assertIn("Q01", run("next", env=env)[1])

    def test_unknown_backend_refused(self):
        """A typo in the backend must fail loudly instead of falling back to GitHub."""
        code, _, err = run("next", env=dict(ENV, AES_QUEUE_BACKEND="s3"))
        self.assertEqual(code, cli.EXIT_REFUSED)
        self.assertIn("s3", err)

    def test_github_backend_uses_injected_http(self):
        """The github-issue backend routes through the one HTTP seam."""
        github = FakeGitHub()
        self.assertEqual(run("--repo", "o/r", "--issue", "7", "init", http=github)[0], 0)
        self.assertIn(core.MARKER, github.body)
        state = core.parse_block(github.body)
        self.assertEqual(state["owner"], "o")


class LegacyRoutingTests(unittest.TestCase):
    """AC8: a live v1 Issue keeps v1 behaviour exactly."""

    def _v1(self):
        state = {"version": 1, "next_id": 3, "items": [
            {"id": "Q01", "title": "a", "refs": [], "status": "done", "note": "x"},
            {"id": "Q02", "title": "b", "refs": ["o/r#2"], "status": "pending",
             "note": ""}]}
        return FakeGitHub(cli.render(state))

    def test_v1_issue_served_by_v1_code(self):
        """AC8: next/start on a v1 Issue behave as v1 and write a v1 body."""
        github = self._v1()
        code, out, _ = run("--repo", "o/r", "--issue", "7", "next", http=github)
        self.assertEqual((code, out.splitlines()[0]), (0, "Q02 [pending] b — o/r#2"))
        self.assertEqual(run("--repo", "o/r", "--issue", "7", "start", "Q02",
                             http=github)[0], 0)
        self.assertIn(V1_MARKER, github.body)
        self.assertEqual(cli.parse(github.body)["items"][1]["status"], "active")
        self.assertNotIn(core.MARKER, github.body)

    def test_v2_only_commands_refused_on_v1(self):
        """AC8: v2-only commands on a v1 Issue are refused with the migration pointer, writing nothing."""
        for argv in (("move", "Q02", "--after", "Q01", "--authorized-by", "o",
                      "--reason", "r"), ("history",), ("handoff", "show"),
                     ("export",)):
            github = self._v1()
            body = github.body
            code, _, err = run("--repo", "o/r", "--issue", "7", *argv, http=github)
            self.assertEqual(code, cli.EXIT_REFUSED, argv)
            self.assertIn("migrat", err)
            self.assertEqual(github.body, body)


class ContextDetectionTests(unittest.TestCase):
    """AC5/AC11: harness and provider recorded without harness-specific code in core."""

    def test_detection_and_overrides(self):
        """History must say which harness/provider acted; explicit settings win over detection."""
        cases = [
            ({"CLAUDECODE": "1"}, ("claude-code", "anthropic")),
            ({"GEMINI_CLI": "1"}, ("gemini-cli", "gemini")),
            ({"CODEX_SANDBOX": "seatbelt"}, ("codex", "openai")),
            ({}, ("shell", "unknown")),
            ({"CLAUDECODE": "1", "AES_QUEUE_HARNESS": "kilo",
              "AES_QUEUE_PROVIDER": "openrouter"}, ("kilo", "openrouter")),
        ]
        for env, (harness, provider) in cases:
            ctx = cli.detect_context(dict(env, USER="u"), NOW)
            self.assertEqual((ctx["harness"], ctx["provider"]), (harness, provider), env)
            self.assertEqual(ctx["actor"], "u")
        ctx = cli.detect_context({"AES_QUEUE_ACTOR": "a", "GITHUB_ACTOR": "g"}, NOW)
        self.assertEqual(ctx["actor"], "a")
        self.assertEqual(cli.detect_context({}, NOW)["actor"], "unknown")


if __name__ == "__main__":
    unittest.main()
