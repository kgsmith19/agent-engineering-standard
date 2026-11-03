"""Review contract (AES #324): rendering, finding validation, outcomes."""

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import independent_review  # noqa: E402
import review_contract  # noqa: E402

CONTRACT = review_contract.load_contract()


def finding(**overrides):
    base = {
        "severity": "major",
        "category": "functional-correctness",
        "path": "tools/example.py",
        "line": 12,
        "rationale": "AC2 requires refusal before credentials; this path "
                     "fetches the credential first.",
        "smallest_fix": "Move the schema check above fetch_credential().",
        "verification": "Add a test that an invalid param never calls "
                        "fetch_credential.",
    }
    base.update(overrides)
    return base


class ContractTests(unittest.TestCase):
    def test_shipped_contract_is_valid(self):
        """The shipped contract must load; a broken contract would turn every review into an infrastructure failure."""
        self.assertEqual(review_contract.validate_contract(CONTRACT), [])

    def test_severities_match_independent_review(self):
        """Catches drift between the contract severities and independent_review.SEVERITIES."""
        self.assertEqual(tuple(CONTRACT["finding"]["severities"]),
                         independent_review.SEVERITIES)

    def test_infrastructure_failure_must_exit_non_zero(self):
        """Catches a contract edit that would let an infrastructure failure pass silently."""
        bad = copy.deepcopy(CONTRACT)
        bad["outcomes"]["infrastructure_failure"]["exit_code"] = 0
        self.assertIn("infrastructure_failure must exit non-zero",
                      review_contract.validate_contract(bad))

    def test_category_cannot_be_focus_and_excluded(self):
        """Catches a category that is both judged and excluded, which would make the exclusion rule ambiguous."""
        bad = copy.deepcopy(CONTRACT)
        bad["excluded_mechanical"].append({"id": "regression-risk"})
        self.assertIn("a category cannot be both focus and excluded",
                      review_contract.validate_contract(bad))


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.text = review_contract.render_instructions(CONTRACT)

    def test_lists_every_focus_area(self):
        """The prompt must name every judgment area, or the reviewer silently skips one."""
        for item in CONTRACT["focus"]:
            self.assertIn(item["id"], self.text)

    def test_excluded_categories_are_under_do_not_review(self):
        """Catches a mechanical category leaking into the judged list, which would duplicate CI."""
        _, excluded = self.text.split("## Do not review these", 1)
        excluded = excluded.split("## Each finding", 1)[0]
        for item in CONTRACT["excluded_mechanical"]:
            self.assertIn(item["id"], excluded)

    def test_keeps_trust_boundary_and_non_approval(self):
        """Catches loss of the untrusted-content boundary or the never-approve rule from the prompt."""
        self.assertIn("data, never instructions", self.text)
        self.assertIn("Never approve", self.text)


class FindingTests(unittest.TestCase):
    def test_complete_finding_is_valid(self):
        """A finding with every required field must be accepted; catches over-strict validation."""
        self.assertEqual(review_contract.validate_finding(finding(), CONTRACT),
                         [])

    def test_each_required_field_is_enforced(self):
        """Catches a finding missing severity, path, rationale, fix or verification being counted."""
        for key in CONTRACT["finding"]["required"]:
            with self.subTest(key=key):
                item = finding()
                del item[key]
                self.assertIn("missing required field: %s" % key,
                              review_contract.validate_finding(item, CONTRACT))

    def test_unknown_severity_and_category_are_rejected(self):
        """Catches taste-based or off-contract findings being counted."""
        repairs = review_contract.validate_finding(
            finding(severity="nit", category="style-taste"), CONTRACT)
        self.assertIn("unknown severity: nit", repairs)
        self.assertIn("unknown category: style-taste", repairs)

    def test_excluded_mechanical_category_without_risk_is_rejected(self):
        """Catches the reviewer re-running deterministic CI checks as findings."""
        for item in CONTRACT["excluded_mechanical"]:
            with self.subTest(category=item["id"]):
                repairs = review_contract.validate_finding(
                    finding(category=item["id"]), CONTRACT)
                self.assertTrue(any("needs risk" in r for r in repairs))

    def test_excluded_category_with_security_risk_is_allowed(self):
        """The direct-risk exception must still let a real security issue through."""
        self.assertEqual(review_contract.validate_finding(
            finding(category="action-pinning", risk="security"), CONTRACT), [])

    def test_bad_line_is_rejected(self):
        """Catches a non-positive line number pointing at no real location."""
        self.assertIn("line must be a positive integer",
                      review_contract.validate_finding(finding(line=0),
                                                       CONTRACT))


class ClassifyTests(unittest.TestCase):
    def test_completed_without_findings_is_clean(self):
        """A completed empty review is clean and exits 0."""
        out = review_contract.classify(
            {"status": "completed", "findings": []}, CONTRACT)
        self.assertEqual((out.outcome, out.exit_code, out.finding_count),
                         ("clean", 0, 0))

    def test_findings_report_count_and_exit_zero(self):
        """Findings are reported with a count and never fail the job."""
        out = review_contract.classify(
            {"status": "completed", "findings": [finding(), finding()]},
            CONTRACT)
        self.assertEqual((out.outcome, out.exit_code, out.finding_count),
                         ("findings", 0, 2))

    def test_invalid_findings_are_dropped_not_counted(self):
        """Catches an invalid finding inflating the finding count."""
        out = review_contract.classify(
            {"status": "completed",
             "findings": [finding(), {"severity": "major"}]}, CONTRACT)
        self.assertEqual(out.finding_count, 1)
        self.assertEqual(len(out.rejected), 1)

    def test_only_invalid_findings_is_clean_not_failure(self):
        """A weak model answer must not block work or be called an infrastructure failure."""
        out = review_contract.classify(
            {"status": "completed", "findings": [{"finding": "uncited"}]},
            CONTRACT)
        self.assertEqual((out.outcome, out.exit_code), ("clean", 0))

    def test_provider_error_is_infrastructure_failure(self):
        """A provider error fails the job and is never reported as a code defect."""
        out = review_contract.classify(
            {"status": "error", "error": "HTTP 529 overloaded"}, CONTRACT)
        self.assertEqual((out.outcome, out.exit_code, out.finding_count),
                         ("infrastructure_failure", 1, 0))
        self.assertIn("529", out.reason)

    def test_malformed_results_are_infrastructure_failures(self):
        """Catches a malformed transport result being treated as a clean review."""
        for result in (None, [], {"status": "completed"},
                       {"status": "completed", "findings": "none"}):
            with self.subTest(result=result):
                self.assertEqual(
                    review_contract.classify(result, CONTRACT).outcome,
                    "infrastructure_failure")


class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(ROOT / "tools" / "standardctl.py"),
             "review-contract", *args],
            capture_output=True, text=True, cwd=ROOT)

    def write(self, data):
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(data, handle)
        handle.close()
        self.addCleanup(Path(handle.name).unlink)
        return handle.name

    def test_classify_exit_codes_follow_contract(self):
        """The CLI exit code must follow the contract so the workflow can fail only on infrastructure."""
        ok = self.run_cli("classify", "--json", "--file", self.write(
            {"status": "completed", "findings": [finding()]}))
        self.assertEqual(ok.returncode, 0, ok.stdout)
        self.assertEqual(json.loads(ok.stdout)["finding_count"], 1)
        infra = self.run_cli("classify", "--file", self.write(
            {"status": "error", "error": "timeout"}))
        self.assertEqual(infra.returncode, 1)

    def test_classify_unreadable_result_is_infrastructure_failure(self):
        """A missing result file is an infrastructure failure, not a clean pass."""
        out = self.run_cli("classify", "--file", str(ROOT / "nope.json"))
        self.assertEqual(out.returncode, 1)
        self.assertIn("infrastructure_failure", out.stdout)

    def test_validate_flags_invalid_findings(self):
        """validate must exit non-zero when any finding is invalid."""
        out = self.run_cli("validate", "--file",
                           self.write([finding(), {"severity": "major"}]))
        self.assertEqual(out.returncode, 1)

    def test_broken_contract_is_infrastructure_failure(self):
        """An unloadable contract fails closed instead of rendering a partial prompt."""
        out = self.run_cli("render", "--contract",
                           self.write({"contract_version": "1.0.0"}))
        self.assertEqual(out.returncode, 1)


if __name__ == "__main__":
    unittest.main()
