"""Tests for the PR Gate required-job aggregation (Issue #314).

The behavior tests run the gate job's own inline script, extracted from the
real ``pr-gate.yml`` together with its REQUIRED_JOBS and OPTIONAL_JOBS, so
they fail if the workflow drifts from the standard (AGENTS.md, PR Gate:
every applicable job is required unless the owner records an override).
"""

import json
import os
import re
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

WORKTREE = Path(__file__).resolve().parent.parent
WORKFLOW = WORKTREE / ".github" / "workflows" / "pr-gate.yml"
ALL_JOBS = ("setup", "policy", "lint", "security", "tests", "evidence")
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
    return set(matches[0].strip("\"'").split())


def required_jobs():
    return _env_jobs("REQUIRED_JOBS")


def optional_jobs():
    return _env_jobs("OPTIONAL_JOBS")


def _gate_script():
    """Return the gate job's inline ``python3 - <<'GATE'`` script."""
    match = re.search(r"python3 - <<'GATE'\n(.*?)\n[ \t]*GATE\n",
                      _gate_job_text(), re.S)
    if not match:
        raise AssertionError("gate job has no inline GATE script")
    return textwrap.dedent(match.group(1))


def run_gate(needs):
    """Run the gate script on ``needs``; return (exit code, ERROR, WARNING lines)."""
    env = dict(os.environ,
               NEEDS=json.dumps(needs),
               REQUIRED_JOBS=" ".join(sorted(required_jobs())),
               OPTIONAL_JOBS=" ".join(sorted(optional_jobs())))
    proc = subprocess.run([sys.executable, "-c", _gate_script()], env=env,
                          capture_output=True, text=True, check=False)
    lines = proc.stdout.splitlines()
    problems = [l for l in lines if l.startswith("ERROR:")]
    warnings = [l for l in lines if l.startswith("WARNING:")]
    return proc.returncode, problems, warnings


def _needs(overrides=None, builder="anthropic", reviewer="openai"):
    """Build a ``needs`` mapping: every job succeeded, then apply overrides.

    An override value of ``None`` removes the job (a missing job). ``setup``
    carries the provider outputs the real job publishes (Issue #319).
    """
    needs = {job: {"result": "success"} for job in ALL_JOBS}
    for job, result in (overrides or {}).items():
        if result is None:
            needs.pop(job)
        else:
            needs[job] = {"result": result}
    if "setup" in needs:
        needs["setup"]["outputs"] = {"builder_provider": builder,
                                     "reviewer_provider": reviewer}
    return needs


class RequiredJobBehaviourTests(unittest.TestCase):
    def evaluate(self, overrides=None):
        code, problems, warnings = run_gate(_needs(overrides))
        # The exit code must agree with the reported problems.
        self.assertEqual(1 if problems else 0, code)
        return problems, warnings

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

    def test_no_optional_jobs_remain(self):
        """Oracle change (#329): the optional llm_review lane was removed by
        owner decision, so every gated job is required and none may only
        warn. Catches a lane re-added as a silent optional warning."""
        self.assertEqual(set(), optional_jobs())
        problems, warnings = self.evaluate({"lint": "failure"})
        self.assertTrue(problems)
        self.assertEqual([], warnings)


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


if __name__ == "__main__":
    unittest.main()
