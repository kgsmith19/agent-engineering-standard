"""Tests for the queue guard (Issue #287, phase 4 of #283).

Strategy: the rules are pure (``queue_core.guard_claim`` / ``guard_pr`` /
``closing_refs`` / ``owner_label_authorized``) and tested on plain data;
label provenance is checked for agreement with the existing
``standardctl.owner_label_authorized`` on one corpus, so the two can never
drift. The CLI (``work_queue.py guard``) is driven end to end through the
fake GitHub REST layer and must never write. A structural test pins the
guard step into the PR Gate, so it cannot be silently dropped.
"""

import contextlib
import copy
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

WORKTREE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKTREE / "tools"))
sys.path.insert(0, str(WORKTREE / "tests"))
import queue_core as core  # noqa: E402
import queue_store as store  # noqa: E402
import work_queue as cli  # noqa: E402
from test_queue_store import FakeGitHub  # noqa: E402

_SPEC = importlib.util.spec_from_file_location("standardctl_for_guard",
                                               WORKTREE / "tools" / "standardctl.py")
standardctl = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(standardctl)

CTX = {"actor": "kgsmith19", "harness": "shell", "provider": "unknown",
       "at": "2026-10-26T21:00:00Z"}


def queue(*specs):
    """A queue from (refs, status) specs; statuses pending/active/blocked."""
    state, _ = core.seal(*core.op_init("kgsmith19"), CTX)
    for refs, status in specs:
        state, _ = core.seal(*core.op_add(state, "t", refs, "", []), CTX)
        item = state["items"][-1]
        if status == "active":
            state = copy.deepcopy(state)
            core.find(state, item["id"])["status"] = "active"
        elif status == "blocked":
            state, _ = core.seal(*core.op_transition(state, item["id"], "block",
                                                     "owner"), CTX)
    return state


class RefTests(unittest.TestCase):
    """Reference parsing shared by both guard modes."""

    def test_normalize_ref(self):
        """Refs compare case-insensitively on owner/repo and accept a short #N in a known repo."""
        self.assertEqual(core.normalize_ref("#5", "O/R"), "o/r#5")
        self.assertEqual(core.normalize_ref("KGSmith19/Repo#12"), "kgsmith19/repo#12")
        for bad in ("foo", "o/r#", "#5", "o/r#x", "o#5", "o/r#5 extra"):
            with self.assertRaises(core.QueueError, msg=bad):
                core.normalize_ref(bad)

    def test_closing_refs_matches_github_closing_keywords(self):
        """Only GitHub's closing keywords count; 'Related to' never makes a PR belong to an item."""
        body = ("## Related\nCloses #12\nfixes kgsmith19/agent-extensions#3\n"
                "RESOLVED #4\nRelated to #391\nclose #12\n`Closes #99` in prose")
        self.assertEqual(core.closing_refs(body, "kgsmith19/x"),
                         ["kgsmith19/x#12", "kgsmith19/agent-extensions#3",
                          "kgsmith19/x#4", "kgsmith19/x#99"])
        self.assertEqual(core.closing_refs("Related to #391", "o/r"), [])
        self.assertEqual(core.closing_refs(None, "o/r"), [])


class GuardClaimTests(unittest.TestCase):
    """AC1: claiming an Issue not on the active or next item is refused."""

    def test_claim_on_active_item_ok(self):
        """The active item's Issues are the work in hand."""
        state = queue((["o/r#1"], "blocked"), (["o/r#2", "o/x#7"], "active"),
                      (["o/r#3"], "pending"))
        self.assertIn("Q02", core.guard_claim(state, "O/X#7"))

    def test_claim_on_next_item_ok_when_nothing_active(self):
        """With nothing active, the next item is the one to claim."""
        state = queue((["o/r#1"], "blocked"), (["o/r#2"], "pending"), (["o/r#3"], "pending"))
        self.assertIn("Q02", core.guard_claim(state, "o/r#2"))

    def test_claim_out_of_order_refused_naming_the_right_item(self):
        """Claiming later work is drift; the refusal must say what to work on instead."""
        state = queue((["o/r#2"], "active"), (["o/r#3"], "pending"))
        with self.assertRaises(core.QueueError) as ctx:
            core.guard_claim(state, "o/r#3")
        self.assertIn("Q01", str(ctx.exception))
        state = queue((["o/r#2"], "pending"), (["o/r#3"], "pending"))
        with self.assertRaises(core.QueueError):
            core.guard_claim(state, "o/r#3")
        with self.assertRaises(core.QueueError):
            core.guard_claim(state, "o/r#404")

    def test_claim_on_empty_queue_refused(self):
        """No queue item means no queue-backed work to claim."""
        with self.assertRaises(core.QueueError):
            core.guard_claim(queue(), "o/r#1")


class GuardPrTests(unittest.TestCase):
    """AC2: a PR's closing Issues must belong to an active item."""

    def setUp(self):
        self.state = queue((["o/r#1"], "blocked"), (["o/r#2", "o/x#7"], "active"),
                           (["o/r#3"], "pending"))

    def test_pr_closing_active_issue_ok(self):
        """Every closing Issue on the active item: the PR is queue work."""
        self.assertIn("Q02", core.guard_pr(self.state, ["o/r#2", "o/x#7"], exempt=False))

    def test_pr_closing_nothing_refused(self):
        """A PR that closes no Issue cannot be matched to the queue."""
        with self.assertRaises(core.QueueError):
            core.guard_pr(self.state, [], exempt=False)

    def test_pr_closing_any_off_queue_issue_refused(self):
        """One off-queue closing Issue is enough to refuse: it would land unqueued work."""
        for refs in (["o/r#3"], ["o/r#2", "o/r#3"], ["o/r#1"], ["o/r#99"]):
            with self.assertRaises(core.QueueError, msg=str(refs)):
                core.guard_pr(self.state, refs, exempt=False)

    def test_next_but_not_active_refused(self):
        """A PR needs a claimed (active) item; pending work has not been started through the queue."""
        state = queue((["o/r#2"], "pending"))
        with self.assertRaises(core.QueueError):
            core.guard_pr(state, ["o/r#2"], exempt=False)

    def test_owner_exemption_passes(self):
        """The owner's exemption label is the one escape hatch, and it is reported as such."""
        self.assertIn("exempt", core.guard_pr(self.state, ["o/r#99"], exempt=True))


class LabelProvenanceTests(unittest.TestCase):
    """The exemption counts only when the owner applied the label."""

    def _events(self, *pairs):
        return [{"event": kind, "label": {"name": label}, "actor": {"login": actor}}
                for kind, label, actor in pairs]

    def test_agrees_with_standardctl_on_corpus(self):
        """One provenance rule for the whole standard: queue guard and merge policy must agree."""
        L, O = core.EXEMPT_LABEL, "kgsmith19"
        corpus = [
            [], self._events(("labeled", L, O)), self._events(("labeled", L, "bot")),
            self._events(("labeled", L, O), ("unlabeled", L, O)),
            self._events(("labeled", L, "bot"), ("labeled", L, O)),
            self._events(("labeled", L, O), ("labeled", L, "bot")),
            self._events(("labeled", "other", O)),
            [{"event": "labeled", "label_name": L, "actor_login": O}],
            [{"event": "commented", "actor": {"login": O}}],
        ]
        for events in corpus:
            self.assertEqual(core.owner_label_authorized(events, L, O),
                             standardctl.owner_label_authorized(events, L, O), events)
        self.assertTrue(core.owner_label_authorized(self._events(("labeled", L, O)), L, O))
        self.assertFalse(core.owner_label_authorized(self._events(("labeled", L, "x")), L, O))


def _event_file(test, body, labels=(), number=5, repo="o/r"):
    handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump({"number": number, "pull_request": {"number": number, "body": body,
                                                  "labels": [{"name": n} for n in labels]},
               "repository": {"full_name": repo}}, handle)
    handle.close()
    test.addCleanup(os.unlink, handle.name)
    return handle.name


class GuardCliTests(unittest.TestCase):
    """`work_queue.py guard` end to end; it is read-only."""

    def setUp(self):
        self.github = FakeGitHub()
        adapter = store.GitHubIssueAdapter("o/r", 7, http=self.github)
        store.commit(adapter, lambda s: core.op_init("kgsmith19"), CTX, create=True)
        store.commit(adapter, lambda s: core.op_add(s, "a", ["o/r#2"], "", []), CTX)
        store.commit(adapter, lambda s: core.op_transition(s, "Q01", "start"), CTX)
        store.commit(adapter, lambda s: core.op_add(s, "b", ["o/r#3"], "", []), CTX)
        self.writes = len(self.github.writes())

    def run_guard(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["--repo", "o/r", "--issue", "7", "guard", *argv],
                            http=self.github, env={}, now="2026-10-26T21:00:00Z")
        self.assertEqual(len(self.github.writes()), self.writes, "guard wrote")
        return code, out.getvalue(), err.getvalue()

    def test_claim_modes(self):
        """AC1 via the CLI: exit 0 on queue work, exit 1 naming the active item otherwise."""
        self.assertEqual(self.run_guard("--claim", "o/r#2")[0], 0)
        code, _, err = self.run_guard("--claim", "o/r#3")
        self.assertEqual(code, cli.EXIT_REFUSED)
        self.assertIn("Q01", err)

    def test_pr_event_modes(self):
        """AC2 via the CLI: the PR body's closing Issue decides, from the event payload."""
        self.assertEqual(self.run_guard("--pr-event", _event_file(self, "Closes #2"))[0], 0)
        code, _, err = self.run_guard("--pr-event", _event_file(self, "Closes #3"))
        self.assertEqual(code, cli.EXIT_REFUSED)
        self.assertIn("o/r#3", err)

    def test_exemption_needs_owner_provenance(self):
        """AC2: the exemption label passes only when the owner applied it, per the PR timeline."""
        self.github.timeline = {5: [{"event": "labeled", "label": {"name": core.EXEMPT_LABEL},
                                     "actor": {"login": "someone"}}]}
        path = _event_file(self, "Closes #3", labels=[core.EXEMPT_LABEL])
        code, _, err = self.run_guard("--pr-event", path)
        self.assertEqual(code, cli.EXIT_REFUSED)
        self.assertIn("not applied by the owner", err)
        self.github.timeline = {5: [{"event": "labeled", "label": {"name": core.EXEMPT_LABEL},
                                     "actor": {"login": "kgsmith19"}}]}
        code, out, _ = self.run_guard("--pr-event", path)
        self.assertEqual(code, 0)
        self.assertIn("exempt", out)

    def test_guard_fails_closed_without_a_queue(self):
        """No readable queue means the guard cannot vouch for the work: exit 2, never 0."""
        github = FakeGitHub("no queue here")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["--repo", "o/r", "--issue", "7", "guard", "--claim", "o/r#2"],
                            http=github, env={}, now="2026-10-26T21:00:00Z")
        self.assertEqual(code, cli.EXIT_FORMAT)

    def test_bad_event_file_fails_closed(self):
        """An unreadable event payload must not pass the gate."""
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        handle.write("{not json")
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        self.assertEqual(self.run_guard("--pr-event", handle.name)[0], cli.EXIT_FORMAT)


class GateWiringTests(unittest.TestCase):
    """AC3: the guard runs in this repo's PR Gate, inside a required job."""

    def test_policy_job_runs_the_guard_on_pull_requests(self):
        """Removing the step would silently disable the enforcement; pin it in a required job."""
        text = (WORKTREE / ".github" / "workflows" / "pr-gate.yml").read_text(encoding="utf-8")
        policy = text.split("\n  policy:\n", 1)[1].split("\n  lint:\n", 1)[0]
        self.assertIn('python3 tools/work_queue.py guard --pr-event "$GITHUB_EVENT_PATH"', policy)
        step = policy.split("Policy · Work matches the execution queue", 1)[1]
        self.assertIn("if: github.event_name == 'pull_request'", step.split("run:", 1)[0])
        required = text.split("REQUIRED_JOBS:", 1)[1].split("\n", 1)[0]
        self.assertIn("policy", required.split())


if __name__ == "__main__":
    unittest.main()
