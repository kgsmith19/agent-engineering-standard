"""Tests for tools/conventions.py (#333): conventions are generated and
repaired automatically, and a PR fails only when no Issue can be found."""

import contextlib
import io
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

WORKTREE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKTREE / "tools"))
import conventions  # noqa: E402

PR_TEMPLATE = (WORKTREE / ".github" / "PULL_REQUEST_TEMPLATE.md").read_text(encoding="utf-8")
ISSUE_TEMPLATE = (WORKTREE / ".github" / "ISSUE_TEMPLATE" / "work-item.md").read_text(encoding="utf-8")


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = conventions.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class NamingTests(unittest.TestCase):
    def test_branch_name_is_issue_number_and_slug(self):
        """The generated branch always matches the convention the gate recognises."""
        name = conventions.branch_name(331, "Queue: the order is a working plan, not a lock!")
        self.assertEqual(name, "issue/331-queue-the-order-is-a-working-plan-not-a-lock")
        self.assertTrue(conventions.branch_follows_convention(name))
        self.assertEqual(conventions.branch_name(5, "???"), "issue/5-work")

    def test_slug_is_bounded_on_a_word(self):
        """Long titles never produce a slug past the limit or a dangling hyphen."""
        slug = conventions.slugify("word " * 40)
        self.assertLessEqual(len(slug), conventions.SLUG_LIMIT)
        self.assertFalse(slug.endswith("-"))


class DeriveTests(unittest.TestCase):
    def test_body_then_branch_then_title(self):
        """The body's Closes line wins; then an issue/<n>- branch; then a (#N) title."""
        self.assertEqual(conventions.derive_issue("Closes #7", "issue/9-x", "t (#3)"), (7, "body"))
        self.assertEqual(conventions.derive_issue("", "issue/9-x", "t (#3)"), (9, "branch"))
        self.assertEqual(conventions.derive_issue("", "ccr-abc", "t (#3)"), (3, "title"))
        self.assertEqual(conventions.derive_issue("Related to #4", "ccr-abc", "t"), (None, None))

    def test_closes_line_must_be_its_own_line(self):
        """Prose mentioning 'closes #5' mid-sentence is not a closing line."""
        self.assertIsNone(conventions.closing_issue("this never closes #5 here"))
        self.assertEqual(conventions.closing_issue("x\n  Fixes #12\n"), 12)


class CheckPrTests(unittest.TestCase):
    def test_any_branch_passes_when_the_issue_is_known(self):
        """#333: a harness branch name is not a failure; it is advice."""
        ok, messages = conventions.check_pr("Closes #12", "ccr-a3588a7e-gkdp4s", "t")
        self.assertTrue(ok)
        self.assertTrue(any("note:" in m for m in messages))

    def test_derived_issue_passes_and_says_where_it_came_from(self):
        """A branch-derived Issue passes and names its source, so the autofix is explained."""
        ok, messages = conventions.check_pr("", "issue/12-x", "")
        self.assertTrue(ok)
        self.assertIn("from the branch", messages[0])

    def test_no_issue_fails_with_the_fix(self):
        """With no Issue anywhere the check fails, and the message gives the one command that fixes it."""
        ok, messages = conventions.check_pr("no link", "ccr-x", "t")
        self.assertFalse(ok)
        self.assertIn("pr-body --issue N", messages[0])

    def test_cli_reads_the_event_file(self):
        """The CLI reads the real event payload; an unreadable one fails closed (exit 2), never passes."""
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump({"pull_request": {"body": "", "title": "x",
                                    "head": {"ref": "ccr-x"}}}, handle)
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        self.assertEqual(run("check-pr", "--event", handle.name)[0], 1)
        self.assertEqual(run("check-pr", "--body-file", handle.name, "--head-ref",
                             "issue/4-x")[0], 0)
        self.assertEqual(run("check-pr", "--event", "/nonexistent")[0], 2)


class RepairTests(unittest.TestCase):
    def test_adds_closes_under_related_and_missing_sections(self):
        """The repair inserts, never rewrites, and is idempotent."""
        body = "## Summary\n\nDid a thing.\n\n## Related work\n\nMilestone: x\n"
        fixed = conventions.repair_pr_body(body, PR_TEMPLATE, 12)
        self.assertIn("## Related work\n\nCloses #12", fixed)
        self.assertIn("Did a thing.", fixed)
        self.assertEqual(conventions.missing_headings(fixed, PR_TEMPLATE), [])
        self.assertEqual(conventions.repair_pr_body(fixed, PR_TEMPLATE, 12), fixed)

    def test_existing_closes_line_is_kept(self):
        """An existing Closes line is never replaced by a derived one."""
        fixed = conventions.repair_pr_body("Closes #3", "", 12)
        self.assertIn("Closes #3", fixed)
        self.assertNotIn("#12", fixed)


class GenerateTests(unittest.TestCase):
    def test_pr_body_is_complete_and_passes_the_check(self):
        """A generated body has every template section and closes its Issue."""
        body = conventions.pr_body(PR_TEMPLATE, 42, summary="Adds X.")
        self.assertEqual(conventions.missing_headings(body, PR_TEMPLATE), [])
        self.assertEqual(conventions.closing_issue(body), 42)
        self.assertIn("Adds X.", body)
        self.assertTrue(conventions.check_pr(body, "anything", "")[0])

    def test_issue_body_has_every_section_and_no_front_matter(self):
        """A generated Issue body has every template section and no YAML front matter leaking in."""
        body = conventions.issue_body(ISSUE_TEMPLATE, outcome="Users can X.")
        self.assertNotIn("about:", body)
        self.assertIn("Users can X.", body)
        self.assertEqual(conventions.missing_headings(body, ISSUE_TEMPLATE), [])

    def test_cli_generators(self):
        """The generator commands print exactly what agents paste: a branch name and a closing body."""
        code, out, _ = run("branch", "--issue", "7", "--title", "Fix it")
        self.assertEqual((code, out.strip()), (0, "issue/7-fix-it"))
        code, out, _ = run("pr-body", "--issue", "7")
        self.assertEqual(code, 0)
        self.assertIn("Closes #7", out)


class WiringTests(unittest.TestCase):
    def test_pr_gate_uses_the_tool_and_no_branch_regex(self):
        """The gate calls the shared tool; the old hard branch regex cannot creep back in."""
        text = (WORKTREE / ".github" / "workflows" / "pr-gate.yml").read_text(encoding="utf-8")
        self.assertIn('python3 tools/conventions.py check-pr --event "$GITHUB_EVENT_PATH"', text)
        self.assertNotIn("does not match issue/", text)

    def test_merge_policy_autofix_patterns_match_python(self):
        """The workflow's JavaScript and conventions.py must recognise the same text."""
        text = (WORKTREE / ".github" / "workflows" / "merge-policy.yml").read_text(encoding="utf-8")
        found = dict(re.findall(r"const (CLOSES|BRANCH|TITLE_REF) = /(.+)/[a-z]*;", text))
        self.assertEqual(set(found), {"CLOSES", "BRANCH", "TITLE_REF"})
        self.assertEqual(found["BRANCH"].replace("\\/", "/"), conventions._BRANCH.pattern)
        self.assertEqual(found["TITLE_REF"], conventions._TITLE_REF.pattern)
        self.assertEqual("(?im)" + found["CLOSES"], conventions._CLOSES.pattern)
        self.assertNotIn("actions/checkout", text)


if __name__ == "__main__":
    unittest.main()
