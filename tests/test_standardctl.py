"""Defect-sensitive tests for tools/standardctl.py.

Strategy: build a valid fixture (a committed copy of this repository, or
a consuming repository produced by ``standardctl init --apply``), apply
exactly one mutation per test, run the specific check or subcommand, and
assert the specific stable check_id appears. Positive acceptance tests
prove the unmutated fixtures verify cleanly, so each rejection test's
finding is attributable to its mutation alone.
"""

import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

WORKTREE = Path(__file__).resolve().parent.parent

_SPEC = importlib.util.spec_from_file_location(
    "standardctl", WORKTREE / "tools" / "standardctl.py"
)
standardctl = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(standardctl)

GIT_ENV = dict(
    os.environ,
    GIT_CONFIG_GLOBAL="/dev/null",
    GIT_CONFIG_SYSTEM="/dev/null",
    GIT_AUTHOR_NAME="Fixture",
    GIT_AUTHOR_EMAIL="fixture@example.com",
    GIT_COMMITTER_NAME="Fixture",
    GIT_COMMITTER_EMAIL="fixture@example.com",
    GIT_AUTHOR_DATE="2026-01-01T00:00:00 +0000",
    GIT_COMMITTER_DATE="2026-01-01T00:00:00 +0000",
)

MODULE_TMP = None
STANDARD_FIXTURE = None

HEAD_A = "a" * 40
HEAD_B = "b" * 40

FIXTURE_SET_ARGS = [
    "--set", "__APP_DISPLAY_NAME__=Fixture App",
    "--set", "__APP_SLUG__=fixture-app",
    "--set", "__REPOSITORY__=fixture-owner/fixture-app",
    "--set", "__OWNER_LOGIN__=fixture-owner",
    "--set", "__DEFAULT_BRANCH__=main",
]


def _git(root, *args):
    proc = subprocess.run(
        ["git", "-C", str(root)] + list(args),
        env=GIT_ENV,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise AssertionError(
            "git %s failed in %s: %s" % (" ".join(args), root, proc.stderr)
        )
    return proc.stdout


def _git_init(root):
    proc = subprocess.run(
        ["git", "-c", "init.defaultBranch=main", "-C", str(root), "init"],
        env=GIT_ENV,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise AssertionError("git init failed: %s" % proc.stderr)


def _copy_worktree(dst):
    shutil.copytree(
        WORKTREE,
        dst,
        ignore=shutil.ignore_patterns(
            ".git",
            ".worktrees",
            ".agent-runtime",
            ".superpowers",
            ".evidence",
            "__pycache__",
        ),
    )


def setUpModule():
    """Build the shared committed standard-repository fixture once."""
    global MODULE_TMP, STANDARD_FIXTURE
    MODULE_TMP = tempfile.mkdtemp(prefix="standardctl-tests-")
    STANDARD_FIXTURE = Path(MODULE_TMP) / "standard-fixture"
    _copy_worktree(STANDARD_FIXTURE)
    _git_init(STANDARD_FIXTURE)
    _git(STANDARD_FIXTURE, "add", "-A")
    _git(STANDARD_FIXTURE, "commit", "-m", "standard fixture")


def tearDownModule():
    if MODULE_TMP:
        shutil.rmtree(MODULE_TMP, ignore_errors=True)


def run_cli(args):
    """Run standardctl.main with captured stdout; return (rc, output)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = standardctl.main(args)
    return rc, buf.getvalue()


def check_ids(findings):
    return {f.check_id for f in findings}


def build_valid_repo(target):
    """git-init *target*, populate it via ``init --apply`` from this
    worktree with fixed token values, and commit once."""
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    _git_init(target)
    rc, out = run_cli(
        ["--root", str(WORKTREE), "init", "--target", str(target),
         "--standard-ref", "HEAD", "--apply"] + FIXTURE_SET_ARGS
    )
    if rc != 0:
        raise AssertionError("fixture init failed:\n" + out)
    _git(target, "add", "-A")
    _git(target, "commit", "-m", "consuming fixture")
    return target


class FixtureCase(unittest.TestCase):
    """Shared helpers: per-test fixture copies and evidence builders."""

    def tmpdir(self):
        return Path(tempfile.mkdtemp(dir=MODULE_TMP))

    def std_fixture(self):
        dst = self.tmpdir() / "std"
        shutil.copytree(STANDARD_FIXTURE, dst)
        return dst

    def model(self, root):
        return standardctl.RepoModel(Path(root))

    def write_workflow(self, root, name, content):
        wf_dir = Path(root) / ".github" / "workflows"
        wf_dir.mkdir(parents=True, exist_ok=True)
        (wf_dir / name).write_text(content, encoding="utf-8")

    def make_evidence_dir(self, **overrides):
        """A complete, internally consistent evidence bundle; overrides
        apply single mutations to the manifest."""
        evidence_dir = self.tmpdir() / "evidence"
        evidence_dir.mkdir()
        (evidence_dir / "report.txt").write_bytes(b"evidence output\n")
        digest = standardctl.sha256_file(evidence_dir / "report.txt")
        manifest = {
            "schema_version": 1,
            "repository": "fixture-owner/fixture-app",
            "head_sha": HEAD_A,
            "files": [
                {"path": "report.txt", "type": "report", "sha256": digest}
            ],
            "claims": [
                {"id": "AC1", "result": "pass", "evidence": ["report.txt"]}
            ],
            "oracle_changes": "None.",
        }
        manifest.update(overrides)
        (evidence_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        return evidence_dir, manifest


STRICT_AGGREGATOR_STEPS = """\
      - name: Enforce strict success
        env:
          NEEDS_JSON: ${{ toJSON(needs) }}
        run: |
          python3 -c "import json,os,sys; \\
            needs=json.loads(os.environ['NEEDS_JSON']); \\
            sys.exit(0 if needs and all(v.get('result')=='success' \\
            for v in needs.values()) else 1)"
"""


class StandardRepoRejections(FixtureCase):
    """Each test mutates a valid standard-repository fixture in exactly
    one way and asserts the specific check_id fires."""

    def test_verify_rejects_mismatched_pull_request_template_pair(self):
        """Protects the byte-identity of TEMPLATES/PULL_REQUEST.md and
        .github/PULL_REQUEST_TEMPLATE.md; catches an edit to the active
        copy that silently diverges from the canonical template."""
        root = self.std_fixture()
        active = root / ".github" / "PULL_REQUEST_TEMPLATE.md"
        active.write_text(
            active.read_text(encoding="utf-8") + "\nextra drift line\n",
            encoding="utf-8",
        )
        findings = standardctl.check_template_pairs(self.model(root))
        self.assertIn("template-pair-mismatch", check_ids(findings))

    def test_verify_rejects_mismatched_issue_template_pair(self):
        """Protects the byte-identity of TEMPLATES/ISSUE.md and
        .github/ISSUE_TEMPLATE/work-item.md; catches drift introduced by
        editing only the GitHub-active work-item copy."""
        root = self.std_fixture()
        active = root / ".github" / "ISSUE_TEMPLATE" / "work-item.md"
        active.write_text(
            active.read_text(encoding="utf-8").replace(
                "## Outcome", "## Goal"
            ),
            encoding="utf-8",
        )
        findings = standardctl.check_template_pairs(self.model(root))
        self.assertIn("template-pair-mismatch", check_ids(findings))

    def test_verify_rejects_mismatched_issue_config(self):
        """Protects the byte-identity of TEMPLATES/ISSUE_CONFIG.yml and
        .github/ISSUE_TEMPLATE/config.yml; catches a config edit that
        bypasses the canonical source."""
        root = self.std_fixture()
        active = root / ".github" / "ISSUE_TEMPLATE" / "config.yml"
        active.write_text("blank_issues_enabled: true\n", encoding="utf-8")
        findings = standardctl.check_issue_config(self.model(root))
        self.assertIn("issue-config-mismatch", check_ids(findings))

    def test_verify_rejects_missing_provider_adapter(self):
        """Protects the presence of both provider adapters; catches an
        accidental deletion of GEMINI.md that would strand one provider
        family without the policy import."""
        root = self.std_fixture()
        (root / "GEMINI.md").unlink()
        findings = standardctl.check_adapters(self.model(root))
        self.assertIn("adapter-missing", check_ids(findings))

    def test_verify_rejects_policy_duplicated_into_adapter(self):
        """Protects the import-only adapter contract; catches policy text
        pasted into CLAUDE.md, which would fork the single source of
        truth in AGENTS.md."""
        root = self.std_fixture()
        adapter = root / "CLAUDE.md"
        adapter.write_text(
            adapter.read_text(encoding="utf-8")
            + "\nAlways merge without review.\n",
            encoding="utf-8",
        )
        findings = standardctl.check_adapters(self.model(root))
        self.assertIn("adapter-policy-duplication", check_ids(findings))

    def test_verify_rejects_root_self_lock_in_standard_repo(self):
        """Protects the standard repository from pinning itself; catches
        an init run mistakenly executed against the standard repo, which
        would leave a root standard.lock."""
        root = self.std_fixture()
        (root / "standard.lock").write_text(
            "schema_version: 1\n", encoding="utf-8"
        )
        findings = standardctl.check_root_self_lock(self.model(root))
        self.assertIn("root-self-lock", check_ids(findings))

    def test_verify_rejects_unknown_rendering_token(self):
        """Protects the closed token vocabulary; catches a typo'd or
        invented __BAD_TOKEN__ in a template that init could never
        resolve, which would ship unrendered."""
        root = self.std_fixture()
        template = root / "TEMPLATES" / "project.yaml"
        template.write_text(
            template.read_text(encoding="utf-8") + "\n# marker __BAD_TOKEN__\n",
            encoding="utf-8",
        )
        findings = standardctl.check_unknown_tokens(self.model(root))
        self.assertIn("unknown-token", check_ids(findings))

    def test_verify_rejects_forbidden_test_ledger(self):
        """Protects the no-duplicate-status-database rule; catches a
        committed TEST_LEDGER.md, the exact artifact this standard's
        history deliberately removed."""
        root = self.std_fixture()
        (root / "TEST_LEDGER.md").write_text("| test | ok |\n", encoding="utf-8")
        findings = standardctl.check_forbidden_artifacts(self.model(root))
        self.assertIn("forbidden-artifact", check_ids(findings))

    def test_verify_rejects_committed_implementation_plan(self):
        """Protects the gitignored-scratchpad rule; catches a local plan
        document leaking into the tracked tree instead of staying in the
        agent workspace."""
        root = self.std_fixture()
        (root / "docs").mkdir()
        (root / "docs" / "implementation-plan.md").write_text(
            "step 1\n", encoding="utf-8"
        )
        findings = standardctl.check_forbidden_artifacts(self.model(root))
        self.assertIn("forbidden-artifact", check_ids(findings))

    def test_verify_rejects_unauthorized_extra_workflow(self):
        """Protects the closed workflow set (gate + merge policy, with
        transitional ci.yml); catches a stray automation workflow that
        would widen the control plane unnoticed."""
        root = self.std_fixture()
        self.write_workflow(
            root, "extra.yml", "name: Extra\non:\n  push:\njobs: {}\n"
        )
        findings = standardctl.check_unauthorized_workflows(self.model(root))
        self.assertIn("unauthorized-workflow", check_ids(findings))

    def test_verify_rejects_floating_action_reference(self):
        """Protects SHA-pinning of every action; catches a mutable tag
        reference (actions/checkout@v4) that an upstream tag move could
        silently repoint at different code."""
        root = self.std_fixture()
        self.write_workflow(
            root,
            "pr-gate.yml",
            "name: Fixture App PR Gate\n"
            "on:\n"
            "  pull_request:\n"
            "permissions:\n"
            "  contents: read\n"
            "jobs:\n"
            "  build:\n"
            "    name: Fixture Build\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - uses: actions/checkout@v4\n"
            "      - run: echo test\n",
        )
        findings = standardctl.check_action_pinning(self.model(root))
        self.assertIn("floating-action-ref", check_ids(findings))

    def test_verify_rejects_privileged_workflow_executing_pr_code(self):
        """Protects the privilege boundary; catches a pull_request_target
        workflow with write permissions that checks out PR-controlled
        code — the classic pwn-request injection shape."""
        root = self.std_fixture()
        self.write_workflow(
            root,
            "merge-policy.yml",
            "name: Privileged Fixture\n"
            "on:\n"
            "  pull_request_target:\n"
            "permissions:\n"
            "  contents: write\n"
            "jobs:\n"
            "  handle:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - name: Check out PR code\n"
            "        uses: actions/checkout@"
            "3d3c42e5aac5ba805825da76410c181273ba90b1 # v4.1.1\n"
            "      - run: make\n",
        )
        findings = standardctl.check_privileged_pr_checkout(self.model(root))
        self.assertIn("privileged-pr-checkout", check_ids(findings))

    def test_verify_rejects_missing_owner_authority_language(self):
        """Protects the owner-authority contract in AGENTS/governance.md;
        catches an edit that drops the mandatory waiver-reporting phrase
        and would erode the override protocol (routed-modules
        architecture)."""
        root = self.std_fixture()
        governance = root / "AGENTS" / "governance.md"
        governance.write_text(
            governance.read_text(encoding="utf-8").replace(
                "Not run by owner instruction.", "waived"
            ),
            encoding="utf-8",
        )
        findings = standardctl.check_agents_authority(self.model(root))
        self.assertIn("missing-authority-language", check_ids(findings))

    def test_verify_rejects_generic_gate_job_name(self):
        """Protects the application-specific required-check context;
        catches a final gate job named plain 'PR Gate', which another
        repository's identically named check could satisfy."""
        root = self.std_fixture()
        self.write_workflow(
            root,
            "pr-gate.yml",
            "name: Fixture App PR Gate\n"
            "on:\n"
            "  pull_request:\n"
            "permissions:\n"
            "  contents: read\n"
            "jobs:\n"
            "  tests:\n"
            "    name: Fixture Tests\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - run: echo test\n"
            "  gate:\n"
            "    name: PR Gate\n"
            "    runs-on: ubuntu-latest\n"
            "    needs: [tests]\n"
            "    if: always()\n"
            "    steps:\n" + STRICT_AGGREGATOR_STEPS,
        )
        findings = standardctl.check_gate_names(self.model(root))
        self.assertIn("generic-gate-name", check_ids(findings))

    def test_verify_rejects_aggregator_accepting_skipped_dependencies(self):
        """Protects the fail-closed aggregator; catches a final job whose
        enforcement step lacks the strict every-result-success pattern,
        so skipped or cancelled stages would pass as green."""
        root = self.std_fixture()
        self.write_workflow(
            root,
            "pr-gate.yml",
            "name: Fixture App PR Gate\n"
            "on:\n"
            "  pull_request:\n"
            "permissions:\n"
            "  contents: read\n"
            "jobs:\n"
            "  tests:\n"
            "    name: Fixture Tests\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - run: echo test\n"
            "  gate:\n"
            "    name: Fixture App PR Gate\n"
            "    runs-on: ubuntu-latest\n"
            "    needs: [tests]\n"
            "    if: always()\n"
            "    steps:\n"
            "      - run: echo all good\n",
        )
        findings = standardctl.check_gate_aggregator(self.model(root))
        self.assertIn("aggregator-accepts-skipped", check_ids(findings))

    def test_verify_rejects_aggregator_with_incomplete_needs(self):
        """Protects the aggregator's complete dependency set; catches a
        new gate job left out of the final job's needs list, which would
        let its failure escape the required check."""
        root = self.std_fixture()
        self.write_workflow(
            root,
            "pr-gate.yml",
            "name: Fixture App PR Gate\n"
            "on:\n"
            "  pull_request:\n"
            "permissions:\n"
            "  contents: read\n"
            "jobs:\n"
            "  tests:\n"
            "    name: Fixture Tests\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - run: echo test\n"
            "  lint:\n"
            "    name: Fixture Lint\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - run: echo lint\n"
            "  gate:\n"
            "    name: Fixture App PR Gate\n"
            "    runs-on: ubuntu-latest\n"
            "    needs: [tests]\n"
            "    if: always()\n"
            "    steps:\n" + STRICT_AGGREGATOR_STEPS,
        )
        findings = standardctl.check_gate_aggregator(self.model(root))
        self.assertIn("aggregator-needs-incomplete", check_ids(findings))

    def test_verify_rejects_path_filtered_gate_workflow(self):
        """Protects the always-reporting required check; catches a paths
        filter on the gate workflow, which would make the required
        context silently never report for out-of-path PRs."""
        root = self.std_fixture()
        self.write_workflow(
            root,
            "pr-gate.yml",
            "name: Fixture App PR Gate\n"
            "on:\n"
            "  pull_request:\n"
            "    paths:\n"
            "      - \"src/**\"\n"
            "permissions:\n"
            "  contents: read\n"
            "jobs:\n"
            "  gate:\n"
            "    name: Fixture App PR Gate\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - run: echo test\n",
        )
        findings = standardctl.check_gate_path_filters(self.model(root))
        self.assertIn("required-workflow-path-filter", check_ids(findings))

    def test_verify_rejects_noop_gate_stage(self):
        """Protects against empty-success stages; catches a gate job
        whose only step is checkout, which verifies nothing yet reports
        success to the aggregator."""
        root = self.std_fixture()
        self.write_workflow(
            root,
            "pr-gate.yml",
            "name: Fixture App PR Gate\n"
            "on:\n"
            "  pull_request:\n"
            "permissions:\n"
            "  contents: read\n"
            "jobs:\n"
            "  hollow:\n"
            "    name: Fixture Hollow\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - name: Check out repository\n"
            "        uses: actions/checkout@"
            "3d3c42e5aac5ba805825da76410c181273ba90b1 # v4.1.1\n",
        )
        findings = standardctl.check_gate_noop_stages(self.model(root))
        self.assertIn("noop-stage", check_ids(findings))

    def test_verify_rejects_unresolved_token_outside_templates(self):
        """Protects rendered trees from unresolved placeholders; catches
        an __APP_SLUG__ token leaking into README.md where no renderer
        will ever visit again."""
        root = self.std_fixture()
        readme = root / "README.md"
        readme.write_text(
            readme.read_text(encoding="utf-8") + "\nSlug: __APP_SLUG__\n",
            encoding="utf-8",
        )
        findings = standardctl.check_unresolved_tokens(self.model(root))
        self.assertIn("unresolved-token", check_ids(findings))

    def test_verify_rejects_test_method_without_justification_docstring(self):
        """Protects the test-justification rule; catches a docstring-less
        def test_, which hides what behavior the test protects and what
        defect it would catch."""
        root = self.std_fixture()
        (root / "tests" / "test_bad.py").write_text(
            "import unittest\n"
            "\n"
            "\n"
            "class Bad(unittest.TestCase):\n"
            "    def test_without_docstring(self):\n"
            "        pass\n",
            encoding="utf-8",
        )
        findings = standardctl.check_test_justifications(self.model(root))
        self.assertIn("missing-test-justification", check_ids(findings))

    def test_verify_accepts_llm_review_workflow_filename(self):
        """Protects the widened closed workflow set (gate + merge policy +
        llm-review, with transitional ci.yml); catches a regression that
        forgets to allow the new Independent LLM Review template's
        rendered filename, which would block every adopter that installs
        it."""
        root = self.std_fixture()
        self.write_workflow(
            root,
            "llm-review.yml",
            "name: Fixture App · Independent LLM Review\n"
            "on:\n"
            "  workflow_call:\n"
            "permissions:\n"
            "  contents: read\n"
            "jobs:\n"
            "  review:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - run: echo review\n",
        )
        findings = standardctl.check_unauthorized_workflows(self.model(root))
        self.assertNotIn("unauthorized-workflow", check_ids(findings))

    def test_verify_rejects_floating_action_reference_in_llm_review_workflow(self):
        """Protects SHA-pinning on the Independent LLM Review workflow the
        same as the gate and merge-policy workflows; catches a mutable
        tag reference that an upstream tag move could silently repoint at
        different code inside the review job."""
        root = self.std_fixture()
        self.write_workflow(
            root,
            "llm-review.yml",
            "name: Fixture App · Independent LLM Review\n"
            "on:\n"
            "  workflow_call:\n"
            "permissions:\n"
            "  contents: read\n"
            "jobs:\n"
            "  review:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - uses: actions/checkout@v4\n"
            "      - run: echo review\n",
        )
        findings = standardctl.check_action_pinning(self.model(root))
        self.assertIn("floating-action-ref", check_ids(findings))

    def test_verify_rejects_llm_review_workflow_without_permissions_block(self):
        """Protects the explicit-permissions requirement on the
        Independent LLM Review workflow; catches a missing top-level
        permissions block, which would leave the job running with the
        repository's ambient (potentially write) default token scope."""
        root = self.std_fixture()
        self.write_workflow(
            root,
            "llm-review.yml",
            "name: Fixture App · Independent LLM Review\n"
            "on:\n"
            "  workflow_call:\n"
            "jobs:\n"
            "  review:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - run: echo review\n",
        )
        findings = standardctl.check_workflow_permissions(self.model(root))
        self.assertIn("workflow-permissions", check_ids(findings))

    def test_verify_accepts_reusable_workflow_call_job_as_non_noop(self):
        """Protects a same-repo reusable-workflow-call job (uses: ./...,
        no steps) from being misclassified as an empty-success stage;
        catches a regression in the noop-stage heuristic that would block
        every adopter wiring Independent LLM Review into the gate via
        job-level 'uses'."""
        root = self.std_fixture()
        self.write_workflow(
            root,
            "pr-gate.yml",
            "name: Fixture App PR Gate\n"
            "on:\n"
            "  pull_request:\n"
            "permissions:\n"
            "  contents: read\n"
            "jobs:\n"
            "  llm_review:\n"
            "    name: Fixture LLM Review\n"
            "    uses: ./.github/workflows/llm-review.yml\n"
            "  gate:\n"
            "    name: Fixture App PR Gate\n"
            "    runs-on: ubuntu-latest\n"
            "    needs: [llm_review]\n"
            "    if: always()\n"
            "    steps:\n" + STRICT_AGGREGATOR_STEPS,
        )
        findings = standardctl.check_gate_noop_stages(self.model(root))
        self.assertNotIn("noop-stage", check_ids(findings))

    def test_verify_accepts_unpinned_local_reusable_workflow_call(self):
        """Protects same-repo reusable-workflow calls (uses: ./...) from
        the SHA-pinning requirement meant for third-party actions; catches
        a regression that would demand an impossible commit-SHA pin on a
        same-repo relative path, blocking every adopter that wires
        Independent LLM Review into the gate this way."""
        root = self.std_fixture()
        self.write_workflow(
            root,
            "pr-gate.yml",
            "name: Fixture App PR Gate\n"
            "on:\n"
            "  pull_request:\n"
            "permissions:\n"
            "  contents: read\n"
            "jobs:\n"
            "  llm_review:\n"
            "    name: Fixture LLM Review\n"
            "    uses: ./.github/workflows/llm-review.yml\n",
        )
        findings = standardctl.check_action_pinning(self.model(root))
        self.assertNotIn("floating-action-ref", check_ids(findings))

    def test_verify_rejects_code_owner_review_required_in_ruleset(self):
        """Protects the forbidden-outcomes rule against GitHub-native
        approving reviews; catches a regression to
        require_code_owner_review: true in the main-protection ruleset
        template, the exact live-config form of the code-owner-review
        gating this standard retired in favor of Independent LLM Review."""
        root = self.std_fixture()
        ruleset = root / "TEMPLATES" / "main-protection.ruleset.json"
        ruleset.write_text(
            ruleset.read_text(encoding="utf-8").replace(
                '"require_code_owner_review": false',
                '"require_code_owner_review": true',
            ),
            encoding="utf-8",
        )
        findings = standardctl.check_no_native_review_gating(self.model(root))
        self.assertIn("native-review-gating", check_ids(findings))

    def test_verify_rejects_nonzero_approving_review_count_in_ruleset(self):
        """Protects the forbidden-outcomes rule against GitHub-native
        approving reviews; catches a regression to a nonzero
        required_approving_review_count in the main-protection ruleset
        template, which would silently reintroduce GitHub-native review
        gating this standard forbids."""
        root = self.std_fixture()
        ruleset = root / "TEMPLATES" / "main-protection.ruleset.json"
        ruleset.write_text(
            ruleset.read_text(encoding="utf-8").replace(
                '"required_approving_review_count": 0',
                '"required_approving_review_count": 2',
            ),
            encoding="utf-8",
        )
        findings = standardctl.check_no_native_review_gating(self.model(root))
        self.assertIn("native-review-gating", check_ids(findings))


class Acceptance(FixtureCase):
    """The unmutated trees must verify cleanly, anchoring every
    rejection test to its single mutation."""

    def test_verify_accepts_this_repository(self):
        """Protects the staged transitional state of this repository
        (ci.yml present, pr-gate.yml absent); catches any check that
        would false-positive on the real tree and block every PR."""
        report = standardctl.run_checks(standardctl.RepoModel(WORKTREE))
        errors = [f for f in report.findings if f.severity == "error"]
        self.assertEqual(
            [], errors,
            "verify must pass on this worktree; got:\n%s"
            % "\n".join("%s %s: %s" % (f.check_id, f.path, f.message)
                        for f in errors),
        )

    def test_verify_accepts_initialized_consuming_repository(self):
        """Protects init's output contract; catches a renderer or
        manifest defect that would produce a consuming repository whose
        own verify immediately fails."""
        target = build_valid_repo(self.tmpdir() / "consuming")
        report = standardctl.run_checks(standardctl.RepoModel(target))
        errors = [f for f in report.findings if f.severity == "error"]
        self.assertEqual(
            [], errors,
            "verify must pass on an initialized consuming repo; got:\n%s"
            % "\n".join("%s %s: %s" % (f.check_id, f.path, f.message)
                        for f in errors),
        )
        self.assertTrue((target / "standard.lock").is_file())
        lock_text = (target / "standard.lock").read_text(encoding="utf-8")
        self.assertNotIn("__STANDARD_COMMIT__", lock_text)


class InitUpdate(FixtureCase):
    """Rendering, lock ordering, and update fail-closed behavior."""

    def test_init_dry_run_writes_nothing(self):
        """Protects the dry-run-by-default contract; catches an init that
        mutates the target without --apply."""
        target = self.tmpdir() / "dry"
        target.mkdir()
        rc, out = run_cli(
            ["--root", str(WORKTREE), "init", "--target", str(target),
             "--standard-ref", "HEAD"] + FIXTURE_SET_ARGS
        )
        self.assertEqual(0, rc, out)
        self.assertEqual([], list(target.iterdir()))
        self.assertIn("DRY RUN", out)

    def test_init_render_failure_writes_no_lock(self):
        """Protects write-lock-last ordering; catches an init that
        records a lock even though rendering left unresolved tokens (here
        the display name and its derived tokens are never supplied)."""
        target = self.tmpdir() / "broken"
        target.mkdir()
        rc, out = run_cli(
            ["--root", str(WORKTREE), "init", "--target", str(target),
             "--standard-ref", "HEAD", "--apply",
             "--set", "__APP_SLUG__=fixture-app",
             "--set", "__REPOSITORY__=fixture-owner/fixture-app",
             "--set", "__OWNER_LOGIN__=fixture-owner",
             "--set", "__DEFAULT_BRANCH__=main"]
        )
        self.assertNotEqual(0, rc, out)
        self.assertFalse((target / "standard.lock").exists())
        self.assertIn("unresolved tokens", out)

    def test_update_failure_leaves_lock_bytes_unchanged(self):
        """Protects update's fail-closed lock handling; catches an update
        that advances (or corrupts) standard.lock although applying the
        plan failed midway on an unwritable destination."""
        target = self.tmpdir() / "consuming"
        target.mkdir(parents=True)
        _git_init(target)
        rc, out = run_cli(
            ["--root", str(STANDARD_FIXTURE), "init", "--target", str(target),
             "--standard-ref", "HEAD", "--apply"] + FIXTURE_SET_ARGS
        )
        self.assertEqual(0, rc, out)
        lock_path = target / "standard.lock"
        original_lock = lock_path.read_bytes()
        blocker = target / ".github" / "PULL_REQUEST_TEMPLATE.md"
        blocker.unlink()
        blocker.mkdir()  # dest-is-directory collision breaks the copy
        rc, out = run_cli(
            ["--root", str(STANDARD_FIXTURE), "update", "--target",
             str(target), "--standard-ref", "HEAD", "--apply"]
        )
        self.assertNotEqual(0, rc, out)
        self.assertEqual(original_lock, lock_path.read_bytes())

    def test_update_applies_retirements_and_advances_lock(self):
        """Protects the update contract end to end: retired files are
        deleted, adapt-mode files survive, and the lock advances; catches
        an update that skips retirement cleanup or loses local AGENTS.md
        ownership."""
        target = self.tmpdir() / "consuming"
        target.mkdir(parents=True)
        _git_init(target)
        rc, out = run_cli(
            ["--root", str(STANDARD_FIXTURE), "init", "--target", str(target),
             "--standard-ref", "HEAD", "--apply"] + FIXTURE_SET_ARGS
        )
        self.assertEqual(0, rc, out)
        (target / "TEST_LEDGER.md").write_text("| stale |\n", encoding="utf-8")
        agents = target / "AGENTS.md"
        adapted = agents.read_text(encoding="utf-8") + "\nLocal note.\n"
        agents.write_text(adapted, encoding="utf-8")
        rc, out = run_cli(
            ["--root", str(STANDARD_FIXTURE), "update", "--target",
             str(target), "--standard-ref", "HEAD", "--apply"]
        )
        self.assertEqual(0, rc, out)
        self.assertFalse((target / "TEST_LEDGER.md").exists())
        self.assertEqual(adapted, agents.read_text(encoding="utf-8"))
        head = _git(STANDARD_FIXTURE, "rev-parse", "HEAD").strip()
        self.assertIn(head, (target / "standard.lock").read_text("utf-8"))


class DoctorLive(FixtureCase):
    """Pure doctor --live helpers: drift fixtures fail, in-sync fixtures pass.

    These tests pin the characterization fixtures Stage 3a requires (one
    per drift mode in the Issue's proof strategy) against the pure
    comparison functions -- no network, no live API. Each test names the
    drift mode it characterizes; the empty-diff test is the positive
    control proving the comparators accept honest in-sync state.
    """

    def test_doctor_settings_diff_flags_wrong_merge_mode(self):
        """Drift mode: merge mode allows merge-commit/rebase (want squash
        only); catches a comparator that silently accepts the drift."""
        diffs = standardctl.diff_repository_settings(
            {"allow_squash_merge": True, "allow_merge_commit": False,
             "allow_rebase_merge": False},
            {"allow_squash_merge": True, "allow_merge_commit": True,
             "allow_rebase_merge": True},
        )
        keys = {key for key, _, _ in diffs}
        self.assertEqual({"allow_merge_commit", "allow_rebase_merge"}, keys)

    def test_doctor_settings_diff_flags_squash_title_message_drift(self):
        """Drift mode: squash title/message not per template; catches a
        comparator blind to squash-commit-shape drift."""
        diffs = standardctl.diff_repository_settings(
            {"squash_merge_commit_title": "PR_TITLE",
             "squash_merge_commit_message": "PR_BODY"},
            {"squash_merge_commit_title": "COMMIT_OR_PR_TITLE",
             "squash_merge_commit_message": "COMMIT_MESSAGES"},
        )
        keys = {key for key, _, _ in diffs}
        self.assertEqual(
            {"squash_merge_commit_title", "squash_merge_commit_message"},
            keys,
        )

    def test_doctor_settings_diff_accepts_in_sync_state(self):
        """Positive control: identical desired/actual diffs to nothing;
        catches an over-strict comparator that would flag honest state."""
        self.assertEqual(
            [],
            standardctl.diff_repository_settings(
                {"allow_squash_merge": True, "allow_merge_commit": False},
                {"allow_squash_merge": True, "allow_merge_commit": False,
                 "extra_live_key": True},
            ),
        )

    def test_doctor_missing_labels_flags_absent_owner_labels(self):
        """Drift mode: missing/stale owner labels; catches a label check
        that silently accepts the drift."""
        missing = standardctl.missing_label_names(
            ["status:ready", "owner:allow-draft", "owner:hold-merge"],
            ["status:ready", "owner:hold-merge"],
        )
        self.assertEqual(["owner:allow-draft"], missing)

    def test_doctor_missing_labels_is_case_insensitive(self):
        """Positive control: differently-cased live labels still match;
        catches a case-sensitive comparison that would recreate labels."""
        self.assertEqual(
            [],
            standardctl.missing_label_names(
                ["owner:allow-draft"], ["Owner:Allow-Draft"]
            ),
        )

    def test_doctor_ruleset_render_substitutes_tokens(self):
        """Supports the safe-change path: rendered template parses as JSON
        once tokens are supplied; catches a renderer that leaves tokens."""
        import re

        text = (
            Path(WORKTREE) / "TEMPLATES" / "main-protection.ruleset.json"
        ).read_text(encoding="utf-8")
        rendered = standardctl.render_ruleset_template(
            text,
            {"__MAIN_RULESET_NAME__": "Fixture App Main Protection",
             "__PR_GATE_CHECK__": "Fixture App PR Gate",
             "__OWNER_BYPASS_ACTOR_ID__": "123",
             "__CHECK_INTEGRATION_ID__": "456"},
        )
        self.assertFalse(
            re.search(r"__[A-Z_]+__", rendered),
            "unresolved tokens remain: %s" % rendered[:200],
        )
        parsed = json.loads(rendered)
        self.assertEqual(
            "Fixture App Main Protection", parsed["name"]
        )


class EvidenceValidation(FixtureCase):
    """Evidence manifest schema enforcement (module-docstring schema)."""

    def test_evidence_accepts_complete_manifest(self):
        """Protects the baseline: a complete, consistent bundle validates
        cleanly; catches an over-strict rule that would reject honest
        evidence and train agents to bypass validation."""
        evidence_dir, manifest = self.make_evidence_dir()
        findings = standardctl.validate_evidence(
            manifest, evidence_dir, HEAD_A
        )
        self.assertEqual([], findings)

    def test_evidence_rejects_undisclosed_oracle_weakening(self):
        """Protects the oracle-change firewall; catches a bundle that
        modified tests while claiming 'None.' oracle changes — the
        silent-weakening pattern the standard forbids."""
        evidence_dir, manifest = self.make_evidence_dir(tests_modified=True)
        findings = standardctl.validate_evidence(
            manifest, evidence_dir, HEAD_A
        )
        self.assertIn(
            "evidence-undisclosed-oracle-change", check_ids(findings)
        )

    def test_evidence_requires_exact_head_verifier_for_high_risk_claims(self):
        """Protects independent exact-head verification for R2/R3;
        catches a high-risk claim shipped without any verifier object."""
        evidence_dir, manifest = self.make_evidence_dir(
            claims=[{"id": "AC1", "result": "pass", "risk": "R3",
                     "evidence": ["report.txt"]}]
        )
        findings = standardctl.validate_evidence(
            manifest, evidence_dir, HEAD_A
        )
        self.assertIn("evidence-missing-verifier", check_ids(findings))

    def test_evidence_rejects_ui_claim_without_screenshot(self):
        """Protects the UI-claims-need-screenshots rule; catches a visual
        behavior claim backed only by a text report."""
        evidence_dir, manifest = self.make_evidence_dir(
            claims=[{"id": "AC1", "result": "pass", "ui": True,
                     "evidence": ["report.txt"]}]
        )
        findings = standardctl.validate_evidence(
            manifest, evidence_dir, HEAD_A
        )
        self.assertIn("evidence-ui-claim-no-screenshot", check_ids(findings))

    def test_evidence_rejects_digest_mismatch(self):
        """Protects artifact integrity; catches a listed evidence file
        whose bytes were altered after the manifest digested it."""
        evidence_dir, manifest = self.make_evidence_dir()
        (evidence_dir / "report.txt").write_bytes(b"tampered\n")
        findings = standardctl.validate_evidence(
            manifest, evidence_dir, HEAD_A
        )
        self.assertIn("evidence-digest-mismatch", check_ids(findings))

    def test_evidence_rejects_head_mismatch(self):
        """Protects exact-head evidence binding; catches a bundle whose
        recorded head_sha is not the head being validated (stale evidence
        presented for a newer commit)."""
        evidence_dir, manifest = self.make_evidence_dir()
        findings = standardctl.validate_evidence(
            manifest, evidence_dir, HEAD_B
        )
        self.assertIn("evidence-head-mismatch", check_ids(findings))

    def test_evidence_generate_round_trips_through_validate(self):
        """Protects the CI evidence path: a bundle generated by
        'evidence generate' must validate cleanly at the same head;
        catches a generator whose digests, claims, or oracle_changes
        default do not satisfy the validator (a gate that can never be
        green, or one green by schema accident)."""
        evidence_dir = self.tmpdir() / "evidence"
        (evidence_dir / "transcripts").mkdir(parents=True)
        transcript = evidence_dir / "transcripts" / "verify.txt"
        transcript.write_text("verify: OK\n", encoding="utf-8")
        rc, out = run_cli(
            ["evidence", "generate", str(evidence_dir), "--head", HEAD_A,
             "--claim", "verify:pass:transcripts/verify.txt",
             "--command", "0:python3 tools/standardctl.py verify"]
        )
        self.assertEqual(0, rc, out)
        rc, out = run_cli(
            ["evidence", "validate", str(evidence_dir), "--head", HEAD_A]
        )
        self.assertEqual(0, rc, out)
        manifest = json.loads(
            (evidence_dir / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual("None.", manifest["oracle_changes"])
        self.assertFalse(manifest["tests_modified"])
        self.assertEqual(
            "verify:pass",
            "%s:%s" % (
                manifest["claims"][0]["id"], manifest["claims"][0]["result"]
            ),
        )

    def test_evidence_generate_discloses_modified_tests(self):
        """Protects the oracle-change firewall in CI: when tests/ changed
        relative to the diff base, the generated manifest must record
        tests_modified=true with a disclosure pointer, not 'None.';
        catches a generator that silently launders test modifications
        into a 'no oracle change' bundle."""
        repo = self.tmpdir() / "repo"
        repo.mkdir()
        _git_init(repo)
        (repo / "tests").mkdir()
        (repo / "tests" / "test_x.py").write_text("# base\n", encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "base")
        base = _git(repo, "rev-parse", "HEAD").strip()
        (repo / "tests" / "test_x.py").write_text(
            "# changed\n", encoding="utf-8"
        )
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "change tests")
        evidence_dir = repo / ".evidence"
        evidence_dir.mkdir()
        (evidence_dir / "log.txt").write_text("ran\n", encoding="utf-8")
        rc, out = run_cli(
            ["evidence", "generate", str(evidence_dir), "--head", HEAD_A,
             "--claim", "tests:pass:log.txt",
             "--diff-base", base, "--root", str(repo)]
        )
        self.assertEqual(0, rc, out)
        manifest = json.loads(
            (evidence_dir / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertTrue(manifest["tests_modified"])
        self.assertIsInstance(manifest["oracle_changes"], list)
        rc, out = run_cli(
            ["evidence", "validate", str(evidence_dir), "--head", HEAD_A]
        )
        self.assertEqual(0, rc, out)


class StatusCores(FixtureCase):
    """Pure status/release/label/ledger cores (no network, no git)."""

    def test_status_flags_silent_redispatch_of_unknown_task(self):
        """Protects the never-redispatch-into-UNKNOWN rule; catches a
        controller re-dispatching a task whose previous writer state was
        never reconciled (two writers in one worktree)."""
        ledger = (
            "Task 3: DISPATCHING builder\n"
            "Task 3: UNKNOWN session lost\n"
            "Task 3: DISPATCHING builder again\n"
        )
        findings = standardctl.detect_unknown_redispatch(ledger)
        self.assertIn("unknown-subagent-redispatch", check_ids(findings))

    def test_status_accepts_redispatch_after_reconciliation(self):
        """Protects legitimate recovery; catches an over-eager rule that
        would flag a redispatch even after 'Reconciliation performed:'
        re-established writer exclusivity."""
        ledger = (
            "Task 3: DISPATCHING builder\n"
            "Task 3: UNKNOWN session lost\n"
            "Reconciliation performed: git state verified, no writer\n"
            "Task 3: DISPATCHING builder again\n"
        )
        findings = standardctl.detect_unknown_redispatch(ledger)
        self.assertEqual([], findings)

    def test_release_not_ready_with_open_required_issue(self):
        """Protects the release gate; catches declaring a release ready
        while a required implementation Issue is still open."""
        ready, reasons = standardctl.release_ready(
            [
                {"number": 1, "title": "FEAT: thing", "state": "open",
                 "required": True},
                {"number": 2, "title": "VERIFY: v1.0.0 release",
                 "state": "closed"},
            ]
        )
        self.assertFalse(ready)
        self.assertTrue(any("Issue #1" in r for r in reasons))

    def test_release_not_ready_without_closed_verify_issue(self):
        """Protects the mandatory verification Issue; catches a milestone
        at '100%' that either lacks a VERIFY: Issue or still has it
        open."""
        ready, reasons = standardctl.release_ready(
            [{"number": 1, "title": "FEAT: thing", "state": "closed"}]
        )
        self.assertFalse(ready)
        self.assertTrue(any("VERIFY" in r for r in reasons))
        ready, reasons = standardctl.release_ready(
            [
                {"number": 1, "title": "FEAT: thing", "state": "closed"},
                {"number": 2, "title": "VERIFY: v1.0.0 release",
                 "state": "open"},
            ]
        )
        self.assertFalse(ready)

    def test_release_ready_when_required_and_verify_issues_closed(self):
        """Protects the positive path; catches a rule that could never
        declare readiness, which would push humans to bypass the tool."""
        ready, reasons = standardctl.release_ready(
            [
                {"number": 1, "title": "FEAT: thing", "state": "closed"},
                {"number": 2, "title": "VERIFY: v1.0.0 release",
                 "state": "closed"},
            ]
        )
        self.assertTrue(ready, reasons)
        self.assertEqual([], reasons)

    def test_owner_label_authorization_provenance(self):
        """Protects owner-label provenance: a label applied by a
        non-owner is untrusted, an owner label later removed is
        untrusted, and a current owner-applied label is trusted; catches
        automation honoring a spoofed owner:hold-merge."""
        label = "owner:hold-merge"

        def event(kind, login):
            return {"event": kind, "label": {"name": label},
                    "actor": {"login": login}}

        self.assertFalse(
            standardctl.owner_label_authorized(
                [event("labeled", "mallory")], label, "kgsmith19"
            )
        )
        self.assertFalse(
            standardctl.owner_label_authorized(
                [event("labeled", "kgsmith19"),
                 event("unlabeled", "kgsmith19")],
                label,
                "kgsmith19",
            )
        )
        self.assertTrue(
            standardctl.owner_label_authorized(
                [event("labeled", "kgsmith19")], label, "kgsmith19"
            )
        )


class WorktreeSafety(FixtureCase):
    """Real-git worktree reconciliation and prune safety."""

    def _seed_repo(self):
        repo = self.tmpdir() / "repo"
        repo.mkdir()
        _git_init(repo)
        (repo / "file.txt").write_text("base\n", encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "base")
        return repo

    def test_reconcile_detects_duplicate_worktree_claim(self):
        """Protects single-writer claiming; catches two worktrees both
        claiming Issue #5 via issue/5-* branches, which would race two
        implementation writers."""
        repo = self._seed_repo()
        _git(repo, "worktree", "add",
             str(repo / ".worktrees" / "issue-5-a"), "-b", "issue/5-a")
        _git(repo, "worktree", "add",
             str(repo / ".worktrees" / "issue-5-b"), "-b", "issue/5-b")
        worktrees, findings = standardctl.reconcile_worktrees(repo)
        self.assertEqual(3, len(worktrees))
        self.assertIn("worktree-duplicate-claim", check_ids(findings))

    def test_prune_safe_refuses_dirty_and_unmerged_worktrees(self):
        """Protects against destructive cleanup: a dirty worktree and a
        clean-but-unmerged worktree are both refused (worktree-unsafe-
        prune) and left on disk, while a clean worktree whose branch was
        squash-merged into a since-advanced main is deleted as the
        positive control; catches a prune that discards uncommitted or
        unmerged work and a merged-content oracle unable to recognize
        squash merges (this repository merges squash-only)."""
        repo = self._seed_repo()
        dirty = repo / ".worktrees" / "issue-1-dirty"
        unmerged = repo / ".worktrees" / "issue-2-unmerged"
        merged = repo / ".worktrees" / "issue-3-merged"
        _git(repo, "worktree", "add", str(dirty), "-b", "issue/1-dirty")
        _git(repo, "worktree", "add", str(unmerged), "-b", "issue/2-unmerged")
        _git(repo, "worktree", "add", str(merged), "-b", "issue/3-merged")
        (dirty / "file.txt").write_text("edited\n", encoding="utf-8")
        (unmerged / "new.txt").write_text("unmerged\n", encoding="utf-8")
        _git(unmerged, "add", "-A")
        _git(unmerged, "commit", "-m", "unmerged work")
        (merged / "merged.txt").write_text("merged\n", encoding="utf-8")
        _git(merged, "add", "-A")
        _git(merged, "commit", "-m", "merged work")
        _git(repo, "merge", "--squash", "issue/3-merged")
        _git(repo, "commit", "-m", "squash of issue/3-merged")
        (repo / "after.txt").write_text("later\n", encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "main advances after the squash merge")
        deleted, findings = standardctl.prune_safe_worktrees(repo)
        refused = {
            f.path for f in findings
            if f.check_id == "worktree-unsafe-prune"
        }
        self.assertIn(str(dirty), refused)
        self.assertIn(str(unmerged), refused)
        self.assertTrue(dirty.is_dir())
        self.assertTrue(unmerged.is_dir())
        self.assertEqual([str(merged)], deleted)
        self.assertFalse(merged.exists())


class CapabilityRegistry(FixtureCase):
    """Stage 5: 264-capability registry is machine-readable audit metadata."""

    def test_canonical_registry_source_parses(self):
        """Protects the registry input contract; catches a missing or
        unparseable canonical source."""
        import json
        path = WORKTREE / "Canonical" / "capabilities.json"
        records = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(264, len(records))
        ids = [r["Capability ID"] for r in records]
        self.assertEqual(264, len(set(ids)))

    def test_generator_is_byte_reproducible(self):
        """Protects deterministic generation; catches nondeterministic
        ordering, timestamps, or locale-dependent output."""
        import hashlib
        import subprocess
        for _ in range(2):
            proc = subprocess.run(
                ["python", "tools/gen_capabilities.py"],
                capture_output=True, text=True, cwd=str(WORKTREE),
            )
            self.assertEqual(0, proc.returncode, proc.stderr)
        outdir = WORKTREE / "Canonical" / "generated"
        names = sorted(p.name for p in outdir.glob("*"))
        self.assertEqual(
            ["SHA256SUMS.txt", "by-category.md", "by-route.md",
             "preservation-matrix.csv"],
            names,
        )
        first = {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in outdir.glob("*")
        }
        proc = subprocess.run(
            ["python", "tools/gen_capabilities.py"],
            capture_output=True, text=True, cwd=str(WORKTREE),
        )
        self.assertEqual(0, proc.returncode, proc.stderr)
        second = {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in outdir.glob("*")
        }
        self.assertEqual(first, second)

    def test_preservation_matrix_counts(self):
        """Protects the 234/234 preservation firewall; catches a dropped
        or altered v4.2 capability ID."""
        import csv
        with open(WORKTREE / "Canonical" / "v4.2-preservation.csv",
                  encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(264, len(rows))
        ids = [r["Capability ID"] for r in rows]
        self.assertEqual(264, len(set(ids)))
        present = [r for r in rows
                   if r["v4.2 Status"].strip().upper().startswith("PRESENT")]
        self.assertEqual(234, len(present))
        import json
        records = json.loads(
            (WORKTREE / "Canonical" / "capabilities.json")
            .read_text(encoding="utf-8"))
        reg_ids = {r["Capability ID"] for r in records}
        self.assertEqual(reg_ids, set(ids))

    def test_registry_rejects_duplicate_id(self):
        """Protects ID uniqueness; catches a duplicated capability ID
        with the record count held at 264 so only the duplicate probe
        can fire."""
        root = self.std_fixture()
        import json
        path = root / "Canonical" / "capabilities.json"
        records = json.loads(path.read_text(encoding="utf-8"))
        records[1] = dict(records[0])
        path.write_text(json.dumps(records, indent=2), encoding="utf-8")
        findings = standardctl.check_capability_registry(self.model(root))
        messages = [f.message for f in findings
                    if f.check_id == "capability-registry"]
        self.assertTrue(
            any("duplicate Capability ID" in message for message in messages),
            "duplicate probe must fire; got: %s" % messages)

    def test_registry_rejects_missing_id(self):
        """Protects completeness; catches a silently dropped capability."""
        root = self.std_fixture()
        import json
        path = root / "Canonical" / "capabilities.json"
        records = json.loads(path.read_text(encoding="utf-8"))
        path.write_text(json.dumps(records[1:], indent=2), encoding="utf-8")
        findings = standardctl.check_capability_registry(self.model(root))
        self.assertIn("capability-registry", check_ids(findings))

    def test_registry_rejects_missing_required_field(self):
        """Protects the canary/metric/eject firewall; catches a record
        missing Metric."""
        root = self.std_fixture()
        import json
        path = root / "Canonical" / "capabilities.json"
        records = json.loads(path.read_text(encoding="utf-8"))
        del records[0]["Metric"]
        path.write_text(json.dumps(records, indent=2), encoding="utf-8")
        findings = standardctl.check_capability_registry(self.model(root))
        self.assertIn("capability-registry", check_ids(findings))

    def test_registry_rejects_stale_generated_view(self):
        """Protects view freshness; catches a generated view older than
        its source."""
        root = self.std_fixture()
        view = root / "Canonical" / "generated" / "by-category.md"
        view.write_text(view.read_text(encoding="utf-8") + "\nStale.\n",
                        encoding="utf-8")
        findings = standardctl.check_capability_registry(self.model(root))
        self.assertIn("stale-capability-view", check_ids(findings))

    def test_registry_accepts_clean_tree(self):
        """Protects the positive path; catches a check that can never
        pass."""
        findings = standardctl.check_capability_registry(
            standardctl.RepoModel(WORKTREE))
        errors = [f for f in findings if f.severity == "error"]
        self.assertEqual([], errors)

    def test_registry_rejects_missing_matrix(self):
        """Protects the matrix-input contract; catches a deleted
        preservation matrix instead of crashing."""
        root = self.std_fixture()
        (root / "Canonical" / "v4.2-preservation.csv").unlink()
        findings = standardctl.check_capability_registry(self.model(root))
        self.assertIn("capability-registry", check_ids(findings))

    def test_registry_rejects_present_count_drift(self):
        """Protects the 234/234 firewall; catches a demoted v4.2
        capability that breaks the exact PRESENT count."""
        root = self.std_fixture()
        import csv
        matrix = root / "Canonical" / "v4.2-preservation.csv"
        with open(matrix, encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        rows[0]["v4.2 Status"] = "SUPERSEDED"
        with open(matrix, "w", encoding="utf-8", newline="\n") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]),
                                    lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        findings = standardctl.check_capability_registry(self.model(root))
        messages = [f.message for f in findings
                    if f.check_id == "capability-registry"]
        self.assertTrue(
            any("PRESENT rows" in message for message in messages),
            "count probe must fire; got: %s" % messages)

    def test_registry_rejects_matrix_id_mismatch(self):
        """Protects matrix/registry coherence; catches a matrix row ID
        that no longer exists in the registry."""
        root = self.std_fixture()
        import csv
        matrix = root / "Canonical" / "v4.2-preservation.csv"
        with open(matrix, encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        rows[0]["Capability ID"] = "XXXX-999"
        with open(matrix, "w", encoding="utf-8", newline="\n") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]),
                                    lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        findings = standardctl.check_capability_registry(self.model(root))
        messages = [f.message for f in findings
                    if f.check_id == "capability-registry"]
        self.assertTrue(
            any("does not equal" in message for message in messages),
            "mismatch probe must fire; got: %s" % messages)

    def test_registry_rejects_unparseable_source(self):
        """Protects the input contract; catches a corrupt registry file
        instead of crashing."""
        root = self.std_fixture()
        (root / "Canonical" / "capabilities.json").write_text(
            "{not json", encoding="utf-8")
        findings = standardctl.check_capability_registry(self.model(root))
        self.assertIn("capability-registry", check_ids(findings))

    def test_registry_exempts_consuming_repo(self):
        """Protects consuming repos; catches a firewall that fires where
        no Canonical dir exists (mirrors manifest-integrity exemption)."""
        import tempfile
        with tempfile.TemporaryDirectory(
                prefix="standardctl-no-canon-") as raw:
            target = Path(raw) / "consuming"
            target.mkdir()
            findings = standardctl.check_capability_registry(
                standardctl.RepoModel(target))
            self.assertEqual([], findings)


class ArtifactSchemas(FixtureCase):
    """Stage 6: 29 v5 artifact schemas are versioned machine interfaces."""

    def test_schemas_accept_clean_tree(self):
        """Protects the positive path; catches a check that can never
        pass."""
        findings = standardctl.check_artifact_schemas(
            standardctl.RepoModel(WORKTREE))
        errors = [f for f in findings if f.severity == "error"]
        self.assertEqual([], errors)

    def test_schemas_reject_missing_required_field(self):
        """Protects schema completeness; catches a schema with required
        fields stripped."""
        root = self.std_fixture()
        import json
        path = root / "Canonical" / "schemas" / "work-state.schema.json"
        schema = json.loads(path.read_text(encoding="utf-8"))
        schema["required"] = []
        path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
        findings = standardctl.check_artifact_schemas(self.model(root))
        self.assertIn("artifact-schema", check_ids(findings))

    def test_schemas_reject_version_drift(self):
        """Protects inventory freshness; catches a schema bumped without
        its inventory entry."""
        root = self.std_fixture()
        import json
        path = root / "Canonical" / "schemas" / "work-state.schema.json"
        schema = json.loads(path.read_text(encoding="utf-8"))
        schema["version"] = "9.9.9"
        path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
        findings = standardctl.check_artifact_schemas(self.model(root))
        self.assertIn("stale-artifact-schema", check_ids(findings))

    def test_schemas_reject_deleted_schema(self):
        """Protects the 29-schema inventory; catches a silently dropped
        schema file."""
        root = self.std_fixture()
        (root / "Canonical" / "schemas" / "checkpoint.schema.json").unlink()
        findings = standardctl.check_artifact_schemas(self.model(root))
        self.assertIn("artifact-schema", check_ids(findings))

    def test_schemas_exempt_consuming_repo(self):
        """Protects consuming repos; catches a check that fires where no
        Canonical/schemas dir exists."""
        import tempfile
        with tempfile.TemporaryDirectory(
                prefix="standardctl-no-schemas-") as raw:
            target = Path(raw) / "consuming"
            target.mkdir()
            findings = standardctl.check_artifact_schemas(
                standardctl.RepoModel(target))
            self.assertEqual([], findings)


class ThinnessSignal(unittest.TestCase):
    """Stage 7: six-axis Thinness Signal classifies work size; semantic
    gates outrank counts; the CLI is advisory-only."""

    def _score(self):
        import sys
        sys.path.insert(0, str(WORKTREE / "tools"))
        try:
            from thinness import score
            return score
        finally:
            sys.path.remove(str(WORKTREE / "tools"))

    def _axes(self, *values):
        from thinness import AXES
        sys_path = __import__("sys").path
        return dict(zip(AXES, values))

    def test_micro_scores_zero(self):
        """Protects the micro band; catches threshold drift at total 0."""
        result = self._score()(self._axes(0, 0, 0, 0, 0, 0))
        self.assertEqual((0, "micro", False),
                         (result["total"], result["classification"],
                          result["split_recommended"]))

    def test_preferred_band(self):
        """Protects the preferred band; catches drift at total 5."""
        result = self._score()(self._axes(1, 1, 1, 1, 1, 0))
        self.assertEqual("preferred", result["classification"])
        self.assertFalse(result["split_recommended"])

    def test_medium_recommends_split(self):
        """Protects the medium band; catches a missing split signal."""
        result = self._score()(self._axes(2, 1, 1, 1, 1, 1))
        self.assertEqual("medium", result["classification"])
        self.assertTrue(result["split_recommended"])

    def test_large_total(self):
        """Protects the large band; catches a 9-12 score that does not
        refuse one Builder."""
        result = self._score()(self._axes(2, 2, 2, 2, 2, 1))
        self.assertEqual("large", result["classification"])
        self.assertTrue(result["split_recommended"])

    def test_semantic_veto_escalates(self):
        """Protects semantic-outranks-counts; catches a failed hard
        condition that does not escalate the class (preferred 5
        becomes medium 5 with veto recorded)."""
        result = self._score()(self._axes(1, 1, 1, 1, 1, 0),
                               failed_conditions=["one_writer"])
        self.assertEqual("medium", result["classification"])
        self.assertTrue(result["semantic_veto"])
        self.assertIn("one_writer",
                      " ".join(result["explanations"]))

    def test_rejects_bad_axis_value(self):
        """Protects input validation; catches an out-of-range axis."""
        with self.assertRaises(ValueError):
            self._score()(self._axes(0, 0, 0, 0, 0, 9))

    def test_rejects_unknown_axis(self):
        """Protects input validation; catches an unknown axis name."""
        with self.assertRaises(ValueError):
            self._score()({"bogus_axis": 1})

    def test_thinness_cli_is_advisory(self):
        """Protects advisory-only status; catches a thinness command
        that exits nonzero on a large score."""
        import subprocess
        proc = subprocess.run(
            ["python", "tools/standardctl.py", "thinness", "score",
             "--axes", "2,2,2,2,2,2"],
            capture_output=True, text=True, cwd=str(WORKTREE),
        )
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertIn("large", proc.stdout)


class Disposition(unittest.TestCase):
    """Stage 8: exact-head disposition with first-class NO_CHANGE."""

    def _decide(self):
        import sys
        sys.path.insert(0, str(WORKTREE / "tools"))
        try:
            from disposition import decide
            return decide
        finally:
            sys.path.remove(str(WORKTREE / "tools"))

    def _obs(self, **over):
        obs = {"environment": "e", "command": "c", "head": "h",
               "expected": "x", "observed": "x", "evidence": "e"}
        obs.update(over)
        return obs

    def test_implement_needs_observation(self):
        """Protects observation-first; catches IMPLEMENT without proof."""
        with self.assertRaises(ValueError):
            self._decide()("IMPLEMENT", observation=self._obs(head=""))

    def test_no_change_needs_proof(self):
        """Protects honest NO_CHANGE; catches abstention without proof."""
        with self.assertRaises(ValueError):
            self._decide()("NO_CHANGE", observation=self._obs())
        ok = self._decide()("NO_CHANGE", observation=self._obs(),
                            satisfied=True)
        self.assertEqual("NO_CHANGE", ok["disposition"])
        config_only = self._decide()("NO_CHANGE", observation=self._obs(),
                                     code_is_remedy=False)
        self.assertEqual("not-code-remedy", config_only["reason"])

    def test_insufficient_evidence_names_missing(self):
        """Protects precise follow-up; catches a vague evidence gap."""
        with self.assertRaises(ValueError):
            self._decide()("INSUFFICIENT_EVIDENCE",
                           observation=self._obs(), missing="  ")
        ok = self._decide()("INSUFFICIENT_EVIDENCE",
                            observation=self._obs(),
                            missing="exact head of target env")
        self.assertIn("target env", ok["missing"])

    def test_owner_decision_needs_ambiguity(self):
        """Protects against work avoidance; catches OWNER_DECISION
        without a concrete ambiguity."""
        with self.assertRaises(ValueError):
            self._decide()("OWNER_DECISION", observation=self._obs(),
                           ambiguity=" ")
        ok = self._decide()("OWNER_DECISION", observation=self._obs(),
                            ambiguity="ship or hold needs owner call")
        self.assertIn("owner call", ok["ambiguity"])

    def test_disposition_invalidates_derived(self):
        """Protects freshness; catches a decision that leaves derived
        artifacts valid."""
        ok = self._decide()("IMPLEMENT", observation=self._obs())
        self.assertEqual(["readiness", "molds", "capsules"],
                         ok["invalidates"])

    def test_disposition_cli_guards_no_change(self):
        """Protects the CLI contract; catches a proof-less NO_CHANGE
        exiting zero."""
        import subprocess
        proc = subprocess.run(
            ["python", "tools/standardctl.py", "disposition", "check",
             "--outcome", "NO_CHANGE", "--expected", "x", "--observed", "x",
             "--evidence", "y"],
            capture_output=True, text=True, cwd=str(WORKTREE),
        )
        self.assertNotEqual(0, proc.returncode)
        proc = subprocess.run(
            ["python", "tools/standardctl.py", "disposition", "check",
             "--outcome", "IMPLEMENT", "--expected", "x", "--observed", "x",
             "--evidence", "y"],
            capture_output=True, text=True, cwd=str(WORKTREE),
        )
        self.assertEqual(0, proc.returncode, proc.stderr)


class DefinitionOfReady(unittest.TestCase):
    """Stage 9: machine-gated DoR receipt blocks Arc A on guessed intent."""

    def _check(self):
        import sys
        sys.path.insert(0, str(WORKTREE / "tools"))
        try:
            from ready import check_receipt
            return check_receipt
        finally:
            sys.path.remove(str(WORKTREE / "tools"))

    def _full(self, **over):
        receipt = {
            "outcome": "DoR receipt gates Arc A", "claims": "c",
            "forbidden_outcomes": "Arc A on guessed intent",
            "non_goals": "no builder code", "risk": "R2",
            "autonomy_envelope": "standard", "focus_envelope": "stage 9",
            "allowed_paths": "tools/,tests/", "protected_paths": "main",
            "dependencies": "stages 7-8", "thinness_total": 2,
            "disposition": "IMPLEMENT", "recovery": "revert",
            "owner_decisions": "none", "evidence_strategy": "verify+tests",
            "context_budget_ok": True, "extension_profile_ok": True,
        }
        receipt.update(over)
        return receipt

    def test_full_receipt_ready(self):
        """Protects the positive path; catches a gate that never opens."""
        self.assertEqual([], self._check()(self._full()))

    def test_missing_forbidden_outcome_fails(self):
        """Protects explicit non-goals; catches a missing forbidden
        outcome with repair guidance."""
        repairs = self._check()(self._full(forbidden_outcomes=""))
        self.assertTrue(any("forbidden_outcomes" in r for r in repairs))

    def test_large_thinness_fails(self):
        """Protects right-sizing; catches score 9-12 authorizing a
        Builder."""
        repairs = self._check()(self._full(thinness_total=11))
        self.assertTrue(any("9-12" in r for r in repairs))

    def test_stale_disposition_fails(self):
        """Protects observation freshness; catches a non-IMPLEMENT
        disposition."""
        repairs = self._check()(self._full(disposition="NO_CHANGE"))
        self.assertTrue(any("IMPLEMENT" in r for r in repairs))

    def test_over_budget_context_fails(self):
        """Protects context discipline; catches an over-budget profile."""
        repairs = self._check()(self._full(context_budget_ok=False))
        self.assertTrue(any("context_budget_ok" in r for r in repairs))

    def test_compact_form(self):
        """Protects the R0/R1 fast path; catches a compact receipt
        demanding full fields."""
        check = self._check()
        self.assertEqual([],
                         check({"outcome": "o", "scope": "s", "proof": "p"},
                               compact=True))
        self.assertTrue(check({"outcome": "o", "scope": "s"}, compact=True))

    def test_ready_cli_self_dogfood(self):
        """Protects Stage 9 delivery; this Issue's own receipt is READY."""
        import subprocess
        proc = subprocess.run(
            ["python", "tools/standardctl.py", "ready", "--issue", "107",
             "--claims", "DoR receipt gates Arc A",
             "--forbidden", "Arc A starts on guessed intent",
             "--non-goals", "no builder code", "--risk", "R2",
             "--thinness", "1,0,0,0,1,0", "--disposition", "IMPLEMENT"],
            capture_output=True, text=True, cwd=str(WORKTREE),
        )
        self.assertEqual(0, proc.returncode, proc.stderr + proc.stdout)
        self.assertIn("READY", proc.stdout)


class PromptContract(unittest.TestCase):
    """Stage 10: one-outcome phase-pure prompt contract."""

    def _mod(self):
        import sys
        sys.path.insert(0, str(WORKTREE / "tools"))
        try:
            import prompt_contract
            return prompt_contract
        finally:
            sys.path.remove(str(WORKTREE / "tools"))

    def _contract(self, **over):
        base = {
            "primary_outcome": "o", "repository": "r", "issue": "108",
            "phase": "investigate", "role": "builder", "risk": "R2",
            "disposition": "IMPLEMENT", "allowed_mutations": "a",
            "forbidden_mutations": "f", "write_paths": "tools/",
            "protected_paths": "main", "evidence": "verify",
            "stop_conditions": "green", "first_action": "read spec",
            "outcomes": ["one"], "phases": "investigate",
            "authority": "investigate", "hashes": {},
        }
        base.update(over)
        return base

    def test_clean_contract_passes(self):
        """Protects the positive path; catches a gate that never opens."""
        self.assertEqual([], self._mod().validate(self._contract()))

    def test_missing_stop_condition_fails(self):
        """Protects bounded prompts; catches a prompt with no stop."""
        repairs = self._mod().validate(
            self._contract(stop_conditions=""))
        self.assertTrue(any("stop_conditions" in r for r in repairs))

    def test_mega_prompt_rejected(self):
        """Protects phase purity; catches spec+code+review in one."""
        repairs = self._mod().validate(
            self._contract(outcomes=["a", "b"],
                           phases="investigate,implement,review"))
        self.assertTrue(any("shippable outcomes" in r for r in repairs))
        self.assertTrue(any("write phases" in r or "one phase" in r
                            for r in repairs))

    def test_stale_hash_fails(self):
        """Protects hash freshness; catches a stale artifact hash."""
        repairs = self._mod().validate(
            self._contract(hashes={"a.json": "old"}),
            known_heads={"a.json": "new"})
        self.assertTrue(any("stale hash" in r for r in repairs))

    def test_transcript_dump_rejected(self):
        """Protects context discipline; catches pasted history."""
        repairs = self._mod().validate(
            self._contract(transcript_dump=True))
        self.assertTrue(any("transcript dump" in r for r in repairs))

    def test_render_is_short(self):
        """Protects brevity; generated prompts stay phase-pure short."""
        text = self._mod().render(self._contract())
        self.assertLess(len(text.split()), 180)
        self.assertIn("First safe action", text)

    def test_prompt_cli_renders(self):
        """Protects the CLI contract; a clean contract renders exit 0."""
        import subprocess
        proc = subprocess.run(
            ["python", "tools/standardctl.py", "prompt", "check",
             "--outcome", "o", "--repo", "r", "--issue", "108",
             "--phase", "investigate", "--role", "builder", "--risk", "R2",
             "--disposition", "IMPLEMENT", "--write-paths", "tools/",
             "--protected-paths", "main", "--evidence", "verify",
             "--stop", "green", "--first-action", "read spec"],
            capture_output=True, text=True, cwd=str(WORKTREE),
        )
        self.assertEqual(0, proc.returncode, proc.stderr + proc.stdout)
        self.assertIn("First safe action", proc.stdout)


if __name__ == "__main__":
    unittest.main()
