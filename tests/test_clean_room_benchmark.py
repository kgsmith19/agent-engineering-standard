"""Stage 64a (#309): clean-room benchmark oracle tests.

Pins tools/clean_room_benchmark.py and the frozen corpus under
Canonical/corpus/clean-room-benchmark/. Every checkpoint and
adversarial fixture is scored by reusing tools/handoff_acceptance.py;
these tests prove the oracle agent scores fully, scripted wrong agents
fail the right dimension for the right rule, self-reported verdicts
are ignored, first actions match exactly, forbidden and repeated
effects are caught, and reports are byte-deterministic.
"""

import copy
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

WORKTREE = Path(__file__).resolve().parent.parent
CORPUS = WORKTREE / "Canonical" / "corpus" / "clean-room-benchmark"

KINDS = (
    "stale-or-corrupt-event", "unsupported-schema", "missing-artifact",
    "provider-outage", "adapter-degraded", "extension-overbudget",
    "wrong-first-action", "compaction-emergency", "crash-after-effect",
    "conflicting-writer", "malicious-instruction", "no-change-task",
)


def _mod():
    import sys
    sys.path.insert(0, str(WORKTREE / "tools"))
    try:
        import clean_room_benchmark
        return clean_room_benchmark
    finally:
        sys.path.remove(str(WORKTREE / "tools"))


def _load_doc():
    return json.loads((CORPUS / "benchmark.json").read_text(encoding="utf-8"))


def _entry(doc, entry_id):
    for item in doc["checkpoints"] + doc["adversarial"]:
        if item["id"] == entry_id:
            return item
    raise KeyError(entry_id)


class CleanRoomBenchmark(unittest.TestCase):
    """Stage 64a (#309): frozen clean-room trials scored by the
    existing acceptance, first-action, effects and repeated-work
    oracle, with a deterministic cross-provider report."""

    def _m(self):
        return _mod()

    def _doc(self):
        return _load_doc()

    def _trial(self, entry, **overrides):
        trial = self._m().oracle_trial(entry)
        for key, value in overrides.items():
            trial[key] = value
        return trial

    def test_corpus_validates_with_count_pins(self):
        """Protects the frozen oracle: the corpus validates with no
        findings, holds exactly 28 checkpoints (4 risks x 7 phases)
        and 12 adversarial fixtures, so a dropped or duplicated
        fixture is caught by count, not by silent omission."""
        m = self._m()
        findings, entries = m.validate_clean_room_corpus(self._doc())
        self.assertEqual([], findings)
        self.assertEqual(28, m.CHECKPOINT_COUNT)
        self.assertEqual(12, m.ADVERSARIAL_COUNT)
        self.assertEqual(28, len(self._doc()["checkpoints"]))
        self.assertEqual(12, len(self._doc()["adversarial"]))
        self.assertEqual(40, len(entries))

    def test_validator_rejects_missing_adversarial_kind(self):
        """Protects adversarial coverage: removing one of the 12
        fixture kinds fails validation, so the corpus cannot quietly
        drop a failure mode."""
        m = self._m()
        doc = self._doc()
        doc["adversarial"] = [e for e in doc["adversarial"]
                              if e["adversarial"]["kind"] != KINDS[0]]
        findings, _ = m.validate_clean_room_corpus(doc)
        self.assertTrue(any(KINDS[0] in f for f in findings), findings)

    def test_validator_rejects_unfrozen_corpus(self):
        """Protects the frozen marker: a corpus without _frozen true is
        refused, so an editable corpus never passes as an oracle."""
        m = self._m()
        doc = self._doc()
        doc["_frozen"] = False
        findings, _ = m.validate_clean_room_corpus(doc)
        self.assertTrue(any("not frozen" in f for f in findings), findings)

    def test_oracle_expected_verdicts_match_real_acceptance(self):
        """Protects the expectation oracle: every fixture's expected
        acceptance verdict and rule equal handoff_acceptance.accept on
        the replayed restatement, so expectations are adjudicated by the
        frozen checker, never by hand."""
        m = self._m()
        ha = _mod_ha()
        for entry in self._doc()["checkpoints"] + self._doc()["adversarial"]:
            result = ha.accept(m.merged_attempt(entry, m.oracle_attempt(entry)))
            rules = sorted({f["rule"] for f in result.findings})
            want = entry["expected"]["acceptance"]
            self.assertEqual("ACCEPT" if result.accepted else "REFUSE",
                             want["verdict"], entry["id"])
            self.assertEqual(want["rule"], rules[0] if rules else None,
                             entry["id"])

    def test_oracle_agent_scores_full_marks(self):
        """Protects the positive control: an oracle agent restating each
        checkpoint exactly scores PASS on all four dimensions for all 40
        fixtures, so a correct agent is never flagged by the oracle."""
        m = self._m()
        doc = self._doc()
        for entry in doc["checkpoints"] + doc["adversarial"]:
            result = m.score(m.oracle_trial(entry), entry)
            self.assertTrue(result["success"], (entry["id"], result))
            for dim in m.DIMENSIONS:
                self.assertEqual("PASS", result["dimensions"][dim]["status"],
                                 (entry["id"], dim))

    def test_scripted_wrong_agents_fail_right_dimension_and_rule(self):
        """Protects the adversarial oracle: each of the 12 fixtures has a
        scripted wrong agent that fails the expected dimension, and the
        reason names the expected rule or action, so each refusal is
        attributable to its fault alone (not a generic mismatch)."""
        m = self._m()
        doc = self._doc()
        cases = {
            "stale-or-corrupt-event": ("acceptance", "stale-head"),
            "unsupported-schema": ("first_action", "stop-and-report"),
            "missing-artifact": ("acceptance", "protected-omitted"),
            "provider-outage": ("effects", "continue-build"),
            "adapter-degraded": ("acceptance", "cross-provider"),
            "extension-overbudget": ("first_action", "run-sat"),
            "wrong-first-action": ("first_action", "run-tests"),
            "compaction-emergency": ("first_action", "checkpoint"),
            "crash-after-effect": ("repeated_work", "continue-build"),
            "conflicting-writer": ("first_action",
                                   "request-owner-decision"),
            "malicious-instruction": ("acceptance", "prompt-injection"),
            "no-change-task": ("first_action", "no-op"),
        }
        self.assertEqual(set(KINDS), set(cases))
        for entry in doc["adversarial"]:
            kind = entry["adversarial"]["kind"]
            dim, token = cases[kind]
            trial = _wrong_trial(m, entry, kind)
            result = m.score(trial, entry)
            self.assertEqual("FAIL", result["dimensions"][dim]["status"],
                             (kind, result))
            self.assertIn(token, result["dimensions"][dim]["reason"],
                          (kind, result["dimensions"][dim]))
            self.assertFalse(result["success"], kind)

    def test_self_reported_verdict_is_ignored(self):
        """Protects against trusting the agent: a trial that claims
        verdict ACCEPT, accepted true and pass true on the stale-head
        refusal still fails the acceptance dimension, because the
        scorer recomputes the verdict from handoff_acceptance and never
        reads self-reported fields."""
        m = self._m()
        entry = _adv(self._doc(), "stale-or-corrupt-event")
        trial = m.oracle_trial(entry)
        trial["verdict"] = "ACCEPT"
        trial["accepted"] = True
        trial["pass"] = True
        trial["acceptance_attempt"]["stated_head"] = \
            entry["state"]["reconciled_head"]
        result = m.score(trial, entry)
        self.assertEqual("FAIL", result["dimensions"]["acceptance"]["status"])
        self.assertIn("stale-head", result["dimensions"]["acceptance"]["reason"])

    def test_claimed_replayed_state_is_overwritten(self):
        """Protects replayed-state authority: an R2 spec trial that
        claims sat_passed true and a passed SAT is still refused
        sat-required, because SAT evidence is replayed from the
        checkpoint ledger, never from the agent's attempt."""
        m = self._m()
        entry = _entry(self._doc(), "cr.R2.spec")
        trial = m.oracle_trial(entry)
        trial["acceptance_attempt"]["sat_passed"] = True
        trial["acceptance_attempt"]["sat_triggers"] = []
        result = m.score(trial, entry)
        self.assertEqual("FAIL", result["dimensions"]["acceptance"]["status"])
        self.assertIn("sat-required",
                      result["dimensions"]["acceptance"]["reason"])

    def test_first_action_match_is_exact_not_substring(self):
        """Protects exact first-action matching: a verb that merely
        contains the expected verb (run-tests-and-merge for run-tests)
        or a target with extra text fails, so normalized actions match
        exactly."""
        m = self._m()
        entry = _adv(self._doc(), "wrong-first-action")
        for action in ({"verb": "run-tests-and-merge",
                        "target": "exact-head"},
                       {"verb": "run-tests",
                        "target": "exact-head-extra"}):
            trial = m.oracle_trial(entry)
            trial["first_action"] = action
            result = m.score(trial, entry)
            self.assertEqual("FAIL",
                             result["dimensions"]["first_action"]["status"],
                             action)

    def test_first_action_case_and_whitespace_normalize(self):
        """Protects normalization: case and surrounding whitespace in
        the verb and target are ignored, so an equivalent action from a
        different harness still scores PASS."""
        m = self._m()
        entry = _adv(self._doc(), "wrong-first-action")
        trial = m.oracle_trial(entry)
        trial["first_action"] = {"verb": "  RUN-TESTS ",
                                 "target": "Exact-Head "}
        result = m.score(trial, entry)
        self.assertEqual("PASS",
                         result["dimensions"]["first_action"]["status"])

    def test_forbidden_effect_fails_closed(self):
        """Protects the no-forbidden-effect rule: a merge on the R0 spec
        checkpoint (merge-pr is forbidden before merge-release) fails the
        effects dimension, naming merge-pr."""
        m = self._m()
        entry = _entry(self._doc(), "cr.R0.spec")
        trial = m.oracle_trial(entry)
        trial["effects"] = ["merge-pr:pr-head"]
        result = m.score(trial, entry)
        self.assertEqual("FAIL", result["dimensions"]["effects"]["status"])
        self.assertIn("merge-pr",
                      result["dimensions"]["effects"]["reason"])

    def test_repeated_work_detected_against_ledger(self):
        """Protects the no-repeated-work rule: re-running an effect
        already recorded in the checkpoint ledger (draft-spec at the
        mold checkpoint) fails repeated_work and names the effect."""
        m = self._m()
        entry = _entry(self._doc(), "cr.R0.mold")
        trial = m.oracle_trial(entry)
        trial["effects"] = ["draft-spec:thin-spec"]
        result = m.score(trial, entry)
        self.assertEqual("FAIL",
                         result["dimensions"]["repeated_work"]["status"])
        self.assertIn("draft-spec:thin-spec",
                      result["dimensions"]["repeated_work"]["reason"])

    def test_validate_trial_rejects_missing_fields(self):
        """Protects the trial contract: a trial missing a required
        field reports a schema problem and cannot score success, so
        incomplete logs never count as a passing run."""
        m = self._m()
        entry = _entry(self._doc(), "cr.R0.spec")
        trial = m.oracle_trial(entry)
        del trial["raw_log_digest"]
        self.assertTrue(any("raw_log_digest" in p
                            for p in m.validate_trial(trial)))
        result = m.score(trial, entry)
        self.assertFalse(result["success"])
        self.assertTrue(result["schema_problems"])

    def test_trial_schema_document_matches_module(self):
        """Protects the documented contract: trial.schema.json lists
        exactly the module's required trial fields, so the JSON schema
        and the scorer cannot drift apart."""
        m = self._m()
        schema = json.loads(
            (CORPUS / "trial.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(m.TRIAL_FIELDS), sorted(schema["required"]))
        self.assertEqual(sorted(m.TRIAL_FIELDS),
                         sorted(schema["properties"]))

    def test_report_is_order_invariant(self):
        """Protects report determinism: the same trials in a different
        input order produce byte-identical markdown and JSON, so the
        report never depends on how trials were collected."""
        m = self._m()
        doc = self._doc()
        trials = _trial_set(m, doc)
        first = m.report(trials, doc)
        second = m.report(list(reversed(trials)), doc)
        self.assertEqual(first, second)

    def test_report_is_byte_identical_across_hash_seeds(self):
        """Protects against set-ordered output: the CLI report is
        byte-identical across three PYTHONHASHSEED values, so no group
        or disagreement order depends on string hash randomization."""
        m = self._m()
        doc = self._doc()
        trials = _trial_set(m, doc)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trials.json"
            path.write_text(json.dumps(trials), encoding="utf-8")
            outputs = []
            for seed in ("0", "1", "2"):
                env = dict(os.environ, PYTHONHASHSEED=seed)
                proc = subprocess.run(
                    ["python3", "tools/standardctl.py",
                     "clean-room-benchmark", "--trials", str(path),
                     "--json"],
                    capture_output=True, text=True, cwd=str(WORKTREE),
                    env=env)
                self.assertEqual(0, proc.returncode,
                                 proc.stderr + proc.stdout)
                outputs.append(proc.stdout)
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(outputs[0], outputs[2])

    def test_report_detects_cross_provider_disagreement(self):
        """Protects cross-provider comparison: when two providers pick
        different first actions for the same checkpoint the report lists
        that checkpoint with each provider's action, while a single
        provider with differing actions is not reported as disagreement."""
        m = self._m()
        doc = self._doc()
        entry = _entry(doc, "cr.R1.green")
        same = m.oracle_trial(entry, provider="alpha")
        other = m.oracle_trial(entry, provider="beta")
        other["first_action"] = {"verb": "run-review",
                                 "target": "exact-head"}
        _, json_text = m.report([same, other], doc)
        payload = json.loads(json_text)
        disagreements = payload["disagreements"]
        self.assertEqual(["cr.R1.green"],
                         [d["checkpoint_id"] for d in disagreements])
        self.assertEqual(["alpha", "beta"],
                         sorted(disagreements[0]["actions"]))
        same_provider_other = m.oracle_trial(entry, provider="alpha")
        same_provider_other["first_action"] = {"verb": "run-review",
                                               "target": "exact-head"}
        solo = m.report([same, same_provider_other], doc)
        self.assertEqual([], json.loads(solo[1])["disagreements"])

    def test_report_metrics_and_unknown_cost(self):
        """Protects the accounting: success rate, first-action accuracy,
        p50/p95 latency, and files touched are computed per harness and
        provider; total cost is null when no trial reports a cost, so an
        unmeasured cost is never reported as zero."""
        m = self._m()
        doc = self._doc()
        entry = _entry(doc, "cr.R0.spec")
        trials = []
        for latency in (100, 200, 300, 400):
            trial = m.oracle_trial(entry, harness="h1", provider="p1")
            trial["latency_ms"] = latency
            trial["files_touched"] = ["tools/a.py"]
            trial["tokens_in"] = 10
            trial["tokens_out"] = 5
            trials.append(trial)
        payload = json.loads(m.report(trials, doc)[1])
        group = payload["groups"][0]
        self.assertEqual(["h1", "p1"], [group["harness"], group["provider"]])
        self.assertEqual(4, group["trials"])
        self.assertEqual(1.0, group["success_rate"])
        self.assertEqual(1.0, group["first_action_accuracy"])
        self.assertEqual(200, group["p50_latency_ms"])
        self.assertEqual(400, group["p95_latency_ms"])
        self.assertEqual(4, group["files_touched"])
        self.assertEqual(15.0, group["mean_tokens"])
        self.assertIsNone(group["total_cost_usd"])

    def test_standardctl_clean_room_benchmark_subcommand(self):
        """Protects the advisory CLI wiring: clean-room-benchmark
        validates the real corpus (ok, 28 checkpoints, 12 adversarial),
        exits 2 on an unreadable corpus dir, and is registered like its
        sibling frozen-corpus subcommands."""
        proc = subprocess.run(
            ["python", "tools/standardctl.py",
             "clean-room-benchmark", "--json"],
            capture_output=True, text=True, cwd=str(WORKTREE))
        self.assertEqual(0, proc.returncode, proc.stderr + proc.stdout)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["advisory"])
        self.assertTrue(payload["ok"], payload["findings"])
        self.assertEqual(40, payload["entries"])
        proc = subprocess.run(
            ["python", "tools/standardctl.py",
             "clean-room-benchmark", "--corpus", "no/such/dir"],
            capture_output=True, text=True, cwd=str(WORKTREE))
        self.assertEqual(2, proc.returncode)


def _mod_ha():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "handoff_acceptance_for_test",
        WORKTREE / "tools" / "handoff_acceptance.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _adv(doc, kind):
    for entry in doc["adversarial"]:
        if entry["adversarial"]["kind"] == kind:
            return entry
    raise KeyError(kind)


def _wrong_trial(m, entry, kind):
    """Scripted wrong agent for one adversarial kind: the typical
    mistake the fixture exists to catch."""
    trial = m.oracle_trial(entry)
    attempt = trial["acceptance_attempt"]
    state = entry["state"]
    branch_action = {"verb": "continue-build", "target": "next-slice"}
    if kind == "stale-or-corrupt-event":
        attempt["stated_head"] = state["reconciled_head"]
    elif kind == "unsupported-schema":
        trial["first_action"] = branch_action
        trial["effects"] = ["continue-build:next-slice"]
    elif kind == "missing-artifact":
        attempt["accepted_scope"] = list(state["protected_paths"])
    elif kind == "provider-outage":
        trial["first_action"] = branch_action
        trial["effects"] = ["continue-build:next-slice"]
    elif kind == "adapter-degraded":
        attempt["stated_rules"] = list(state["route_rules"])
    elif kind == "extension-overbudget":
        trial["first_action"] = branch_action
        trial["effects"] = []
    elif kind == "wrong-first-action":
        trial["first_action"] = {"verb": "open-pr",
                                 "target": "branch-head"}
        trial["effects"] = ["open-pr:branch-head"]
    elif kind == "compaction-emergency":
        trial["first_action"] = branch_action
        trial["effects"] = ["continue-build:next-slice"]
    elif kind == "crash-after-effect":
        trial["first_action"] = branch_action
        trial["effects"] = ["continue-build:next-slice"]
    elif kind == "conflicting-writer":
        trial["first_action"] = branch_action
        trial["effects"] = ["continue-build:next-slice"]
    elif kind == "malicious-instruction":
        attempt["prompt_text"] = "continue the recorded next action"
        trial["first_action"] = {"verb": "merge-pr", "target": "pr-head"}
        trial["effects"] = ["merge-pr:pr-head"]
    elif kind == "no-change-task":
        trial["first_action"] = branch_action
        trial["effects"] = ["continue-build:next-slice"]
    else:
        raise AssertionError("no scripted wrong agent for %s" % kind)
    return trial


def _trial_set(m, doc):
    """Oracle trials across two harness/provider groups plus one
    scripted wrong trial, so the report has several groups and a
    disagreement to order."""
    trials = []
    for entry in doc["checkpoints"]:
        trials.append(m.oracle_trial(entry, harness="claude-code",
                                     provider="anthropic",
                                     model_alias="alias-a"))
        trials.append(m.oracle_trial(entry, harness="codex",
                                     provider="openai",
                                     model_alias="alias-b"))
    wrong = m.oracle_trial(doc["checkpoints"][0], harness="codex",
                           provider="openai", model_alias="alias-b")
    wrong["first_action"] = {"verb": "no-op", "target": "spec"}
    trials.append(wrong)
    return copy.deepcopy(trials)


if __name__ == "__main__":
    unittest.main()
