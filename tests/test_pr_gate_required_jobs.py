"""Tests for the PR Gate required-job aggregation (Issue #314).

The decision is the pure function ``pr_gate_check.evaluate``. The behavior
tests take their required and optional sets from the real ``pr-gate.yml``,
so they fail if the workflow configuration drifts from the standard
(AGENTS.md, PR Gate: every applicable job is required unless the owner
records an override).
"""

import io
import re
import sys
import unittest
from pathlib import Path

WORKTREE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKTREE / "tools"))
import pr_gate_check as gate  # noqa: E402

WORKFLOW = WORKTREE / ".github" / "workflows" / "pr-gate.yml"
ALL_JOBS = ("setup", "policy", "lint", "security", "tests", "evidence", "llm_review")
STRONG_JOBS = ("tests", "security", "evidence")
FAILING_RESULTS = ("failure", "cancelled", "skipped", "neutral")


def _workflow_text():
    return WORKFLOW.read_text(encoding="utf-8")


def _gate_job_text():
    text = _workflow_text()
    return text.split("\n  gate:\n", 1)[1]


def _env_jobs(key):
    """Return the job set from the single ``<key>: ...`` line in the gate job."""
    matches = re.findall(r"^\s+%s:[ \t]*(.*?)[ \t]*$" % key, _gate_job_text(), re.M)
    if len(matches) != 1:
        raise AssertionError("expected exactly one %s line in the gate job" % key)
    return set(matches[0].split())


def required_jobs():
    return _env_jobs("REQUIRED_JOBS")


def optional_jobs():
    return _env_jobs("OPTIONAL_JOBS")


def _needs(overrides=None):
    """Build a ``needs`` mapping: every job succeeded, then apply overrides.

    An override value of ``None`` removes the job (a missing job).
    """
    needs = {job: {"result": "success"} for job in ALL_JOBS}
    for job, result in (overrides or {}).items():
        if result is None:
            needs.pop(job)
        else:
            needs[job] = {"result": result}
    return needs


class RequiredJobBehaviourTests(unittest.TestCase):
    def evaluate(self, overrides=None):
        return gate.evaluate(_needs(overrides), required_jobs(), optional_jobs())

    def test_all_success_passes(self):
        problems, warnings = self.evaluate()
        self.assertEqual([], problems)
        self.assertEqual([], warnings)

    def test_failed_strong_job_blocks_the_gate(self):
        for job in STRONG_JOBS:
            with self.subTest(job=job):
                problems, _ = self.evaluate({job: "failure"})
                self.assertTrue(
                    any(job in p for p in problems),
                    "a failing %s job must block the gate, got problems=%r"
                    % (job, problems))

    def test_non_success_required_job_blocks_the_gate(self):
        for job in ("setup", "policy", "lint") + STRONG_JOBS:
            for result in FAILING_RESULTS:
                with self.subTest(job=job, result=result):
                    problems, _ = self.evaluate({job: result})
                    self.assertTrue(
                        any(job in p for p in problems),
                        "%s concluded %r must block the gate, got problems=%r"
                        % (job, result, problems))

    def test_skipped_strong_job_blocks_the_gate(self):
        # No strong job has a job-level if: that can skip it on push or
        # pull_request, so skipped is never a documented applicability rule.
        for job in STRONG_JOBS:
            with self.subTest(job=job):
                problems, _ = self.evaluate({job: "skipped"})
                self.assertTrue(
                    any(job in p for p in problems),
                    "a skipped %s job must block the gate, got problems=%r"
                    % (job, problems))

    def test_missing_gated_job_blocks_the_gate(self):
        for job in ("setup", "policy", "lint") + STRONG_JOBS:
            with self.subTest(job=job):
                problems, _ = self.evaluate({job: None})
                self.assertTrue(
                    any(job in p for p in problems),
                    "a missing %s job must block the gate, got problems=%r"
                    % (job, problems))

    def test_llm_review_failure_is_a_warning_not_a_block(self):
        # Kept as found: llm_review is optional and bypassable by the owner
        # (AGENTS/boundaries.md#independent-llm-review).
        for result in FAILING_RESULTS:
            with self.subTest(result=result):
                problems, warnings = self.evaluate({"llm_review": result})
                self.assertEqual([], problems)
                self.assertTrue(any("llm_review" in w for w in warnings))

    def test_missing_llm_review_still_blocks_as_unexpected_set(self):
        problems, _ = self.evaluate({"llm_review": None})
        self.assertTrue(any("llm_review" in p for p in problems))


class WorkflowPinTests(unittest.TestCase):
    def test_required_jobs_pins_setup_policy_lint_security_tests_evidence(self):
        required = required_jobs()
        for job in ("setup", "policy", "lint", "security", "tests", "evidence"):
            self.assertIn(job, required,
                          "REQUIRED_JOBS must include %r (Issue #314 AC1)" % job)

    def test_required_and_optional_partition_the_gated_jobs(self):
        needs_line = re.search(r"^    needs: \[(.*)\]$", _gate_job_text(), re.M)
        self.assertIsNotNone(needs_line)
        gated = set(x.strip() for x in needs_line.group(1).split(","))
        self.assertEqual(gated, required_jobs() | optional_jobs())
        self.assertEqual(set(), required_jobs() & optional_jobs())

    def test_gate_step_delegates_to_the_extracted_check(self):
        gate_job = _gate_job_text()
        self.assertIn("python3 tools/pr_gate_check.py", gate_job)
        self.assertNotIn("python3 - <<'GATE'", gate_job)


class ExtractedCheckMainTests(unittest.TestCase):
    def test_main_fails_on_required_failure(self):
        import json
        out = io.StringIO()
        env = {"NEEDS": json.dumps(_needs({"tests": "failure"})),
               "REQUIRED_JOBS": "setup policy lint tests",
               "OPTIONAL_JOBS": "security evidence llm_review"}
        self.assertEqual(1, gate.main(env, out))
        self.assertIn("Gate FAILED", out.getvalue())


if __name__ == "__main__":
    unittest.main()
