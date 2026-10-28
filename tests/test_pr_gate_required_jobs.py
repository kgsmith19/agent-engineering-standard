"""Tests for the PR Gate required-job aggregation (Issue #314).

The decision is the pure function ``pr_gate_check.evaluate``. The behavior
tests take their required and optional sets from the real ``pr-gate.yml``,
so they fail if the workflow configuration drifts from the standard
(AGENTS.md, PR Gate: every applicable job is required unless the owner
records an override).
"""

import io
import json
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
    return _workflow_text().split("\n  gate:\n", 1)[1]


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
        """A gate with every job concluded success passes with no warnings.

        Protects the happy path; catches a check that blocks green runs.
        """
        problems, warnings = self.evaluate()
        self.assertEqual([], problems)
        self.assertEqual([], warnings)

    def test_failed_strong_job_blocks_the_gate(self):
        """A failing tests, security or evidence job must block the gate.

        Catches the Issue #314 defect where these were optional and a red
        run could still merge.
        """
        for job in STRONG_JOBS:
            with self.subTest(job=job):
                problems, _ = self.evaluate({job: "failure"})
                self.assertTrue(
                    any(job in p for p in problems),
                    "a failing %s job must block the gate, got problems=%r"
                    % (job, problems))

    def test_non_success_required_job_blocks_the_gate(self):
        """Every required job must block on any non-success conclusion.

        Covers failure, cancelled, skipped and neutral, as AGENTS.md lists
        them. Catches a gate that only rejects failure.
        """
        for job in ("setup", "policy", "lint") + STRONG_JOBS:
            for result in FAILING_RESULTS:
                with self.subTest(job=job, result=result):
                    problems, _ = self.evaluate({job: result})
                    self.assertTrue(
                        any(job in p for p in problems),
                        "%s concluded %r must block the gate, got problems=%r"
                        % (job, result, problems))

    def test_skipped_strong_job_blocks_the_gate(self):
        """A skipped tests, security or evidence job must block the gate.

        None of these jobs has a job-level if:, so skipped is never a
        documented applicability rule. Catches treating skipped as success.
        """
        for job in STRONG_JOBS:
            with self.subTest(job=job):
                problems, _ = self.evaluate({job: "skipped"})
                self.assertTrue(
                    any(job in p for p in problems),
                    "a skipped %s job must block the gate, got problems=%r"
                    % (job, problems))

    def test_missing_gated_job_blocks_the_gate(self):
        """A required job absent from needs must block the gate.

        Catches a gate that silently ignores a job that never reported.
        """
        for job in ("setup", "policy", "lint") + STRONG_JOBS:
            with self.subTest(job=job):
                problems, _ = self.evaluate({job: None})
                self.assertTrue(
                    any(job in p for p in problems),
                    "a missing %s job must block the gate, got problems=%r"
                    % (job, problems))

    def test_llm_review_failure_is_a_warning_not_a_block(self):
        """llm_review failure is reported as a warning and never blocks.

        Kept as found: llm_review is optional and the owner can bypass it
        (AGENTS/boundaries.md#independent-llm-review). Catches promoting it
        to required without an owner decision.
        """
        for result in FAILING_RESULTS:
            with self.subTest(result=result):
                problems, warnings = self.evaluate({"llm_review": result})
                self.assertEqual([], problems)
                self.assertTrue(any("llm_review" in w for w in warnings))

    def test_missing_llm_review_still_blocks_as_unexpected_set(self):
        """A missing llm_review job is an unexpected gated set and blocks.

        Catches a workflow that drops a gated job from needs, since the
        expected set still includes it.
        """
        problems, _ = self.evaluate({"llm_review": None})
        self.assertTrue(any("llm_review" in p for p in problems))


class WorkflowPinTests(unittest.TestCase):
    def test_required_jobs_pins_setup_policy_lint_security_tests_evidence(self):
        """REQUIRED_JOBS in pr-gate.yml names the six required gate jobs.

        Issue #314 AC1. Catches a regression that drops tests, security or
        evidence from the required set.
        """
        required = required_jobs()
        for job in ("setup", "policy", "lint", "security", "tests", "evidence"):
            self.assertIn(job, required,
                          "REQUIRED_JOBS must include %r (Issue #314 AC1)" % job)

    def test_required_and_optional_partition_the_gated_jobs(self):
        """REQUIRED_JOBS and OPTIONAL_JOBS partition the gate's needs list.

        Catches a job that is gated but unclassified, or classified in both
        sets.
        """
        needs_line = re.search(r"^    needs: \[(.*)\]$", _gate_job_text(), re.M)
        self.assertIsNotNone(needs_line)
        gated = set(x.strip() for x in needs_line.group(1).split(","))
        self.assertEqual(gated, required_jobs() | optional_jobs())
        self.assertEqual(set(), required_jobs() & optional_jobs())

    def test_gate_step_delegates_to_the_extracted_check(self):
        """The gate step is a thin call to tools/pr_gate_check.py.

        Catches the inline heredoc being restored, which would leave the
        extracted check untested and unused.
        """
        gate_job = _gate_job_text()
        self.assertIn("python3 tools/pr_gate_check.py", gate_job)
        self.assertNotIn("python3 - <<'GATE'", gate_job)

    def test_gate_step_pins_the_strict_conclusion(self):
        """The gate step sets REQUIRED_RESULT to the literal 'success'.

        The standard's structural check requires the strict pattern in the
        gate job. Catches a gate whose required conclusion is weakened.
        """
        self.assertIn("REQUIRED_RESULT: 'success'", _gate_job_text())


class ExtractedCheckMainTests(unittest.TestCase):
    def test_main_fails_on_required_failure(self):
        """main exits 1 and names the failing required job.

        Catches the entry point swallowing a red required result.
        """
        out = io.StringIO()
        env = {"NEEDS": json.dumps(_needs({"tests": "failure"})),
               "REQUIRED_JOBS": "setup policy lint tests",
               "OPTIONAL_JOBS": "security evidence llm_review",
               "REQUIRED_RESULT": "success"}
        self.assertEqual(1, gate.main(env, out))
        self.assertIn("Gate FAILED", out.getvalue())

    def test_main_fails_closed_unless_required_result_is_success(self):
        """main refuses to pass unless REQUIRED_RESULT is exactly 'success'.

        Catches a gate whose required conclusion is weakened through the
        environment, and a missing REQUIRED_RESULT being treated as a pass.
        """
        for value in (None, "skipped", "neutral", ""):
            with self.subTest(REQUIRED_RESULT=value):
                env = {"NEEDS": json.dumps(_needs()),
                       "REQUIRED_JOBS": "setup policy lint security tests evidence",
                       "OPTIONAL_JOBS": "llm_review"}
                if value is not None:
                    env["REQUIRED_RESULT"] = value
                self.assertEqual(1, gate.main(env, io.StringIO()))


if __name__ == "__main__":
    unittest.main()
