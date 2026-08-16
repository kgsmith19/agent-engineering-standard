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
        """Protects the owner-authority contract in AGENTS.md; catches an
        edit that drops the mandatory waiver-reporting phrase and would
        erode the override protocol."""
        root = self.std_fixture()
        agents = root / "AGENTS.md"
        agents.write_text(
            agents.read_text(encoding="utf-8").replace(
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
        prune) and left on disk, while a content-merged clean worktree is
        deleted as the positive control; catches a prune that discards
        uncommitted or unmerged work."""
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


if __name__ == "__main__":
    unittest.main()
