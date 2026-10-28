"""Std#300 runtime-neutral role/authority contract conformance.

Pins tools/role_contract.decide against the frozen positive and
negative fixtures under Canonical/corpus/role-contract/ and against
the fail-closed properties the contract promises. Reuses the path and
provider rules of tools/role_authority.py.
"""

import copy
import json
import sys
import unittest
from pathlib import Path

WORKTREE = Path(__file__).resolve().parent.parent

CORPUS = WORKTREE / "Canonical" / "corpus" / "role-contract" / "contracts.json"

REQUIRED_RULES = (
    "grant-invalid",
    "action-invalid",
    "grant-expired",
    "stale-head",
    "self-grant",
    "unverified-provenance",
    "out-of-scope",
    "forbidden-self-review",
    "unauthorized-github-write",
    "owner-override",
    "privilege-escalation",
    "parallel-write",
    "missing-evidence",
)

REQUIRED_KEYS = {"id", "grant", "action", "now", "current_head", "expect"}

OPTIONAL_KEYS = {"owner", "override", "other_grants", "delegated"}

FLOW_STEP_KEYS = {"grant", "action", "task", "now", "current_head",
                  "acceptance_ids", "claims", "input_artifacts",
                  "output_artifacts", "specialty", "owner", "override",
                  "other_grants", "delegated", "expect"}

RECEIPT_KEYS = {"schema_version", "task", "duty", "specialty", "actor_id",
                "run_id", "grantor", "provider", "provenance", "scope",
                "exact_sha", "input_artifacts", "output_artifacts",
                "acceptance_ids", "claims", "decision", "rules",
                "decided_at"}

# Non-waivable refusals: an owner override must leave these standing.
NON_WAIVABLE_IDS = (
    "role-contract.refuse.self-grant",
    "role-contract.refuse.same-actor-builder-verifier",
    "role-contract.refuse.review-same-family-r3",
    "role-contract.refuse.provenance-empty",
    "role-contract.refuse.github-post-no-identity",
    "role-contract.refuse.scope-outside-grant",
)


def _mod():
    sys.path.insert(0, str(WORKTREE / "tools"))
    try:
        import role_contract
        return role_contract
    finally:
        sys.path.remove(str(WORKTREE / "tools"))


def _ra():
    sys.path.insert(0, str(WORKTREE / "tools"))
    try:
        import role_authority
        return role_authority
    finally:
        sys.path.remove(str(WORKTREE / "tools"))


def _doc():
    return json.loads(CORPUS.read_text(encoding="utf-8"))


def _case(case_id):
    for case in _doc()["cases"]:
        if case["id"] == case_id:
            return copy.deepcopy(case)
    raise AssertionError("missing fixture %s" % case_id)


def _decide(mod, case, **overrides):
    kwargs = {
        "now": case["now"],
        "current_head": case["current_head"],
        "owner": case.get("owner"),
        "override": case.get("override"),
        "other_grants": case.get("other_grants", []),
    }
    if "delegated" in case:
        kwargs["delegated"] = case["delegated"]
    kwargs.update(overrides)
    return mod.decide(case["grant"], case["action"], **kwargs)


class RoleContract(unittest.TestCase):
    """Std#300: one harness-neutral grant contract, fail closed."""

    def test_every_fixture_matches_decide(self):
        """Protected behavior: each frozen fixture's allow/refuse outcome
        and rule ids equal decide(); catches any drift in the contract
        (a permissive regression flips an allow.* or refuse.* case)."""
        mod = _mod()
        for case in _doc()["cases"]:
            with self.subTest(case=case["id"]):
                allowed, rules = _decide(mod, case)
                self.assertEqual(case["expect"]["allowed"], allowed)
                self.assertEqual(case["expect"]["rules"], rules)

    def test_corpus_is_frozen_and_covers_every_rule(self):
        """Protected behavior: the corpus is frozen, has at least 10
        unique cases with both allow and refuse outcomes, every id
        names its outcome, and every rule id is pinned by a fixture.
        Catches a silently thinned or unpinned oracle."""
        doc = _doc()
        self.assertIs(True, doc["_frozen"])
        cases = doc["cases"]
        self.assertGreaterEqual(len(cases), 10)
        ids = [case["id"] for case in cases]
        self.assertEqual(len(ids), len(set(ids)))
        for case in cases:
            outcome = "allow" if case["expect"]["allowed"] else "refuse"
            self.assertTrue(
                case["id"].startswith("role-contract.%s." % outcome),
                case["id"])
            self.assertLessEqual(REQUIRED_KEYS, set(case), case["id"])
            self.assertLessEqual(set(case),
                                 REQUIRED_KEYS | OPTIONAL_KEYS, case["id"])
        self.assertTrue(any(c["expect"]["allowed"] for c in cases))
        self.assertTrue(any(not c["expect"]["allowed"] for c in cases))
        covered = {rule for case in cases
                   for rule in case["expect"]["rules"]}
        covered |= {rule for flow in _doc()["flows"]
                    for step in flow["steps"]
                    for rule in step["expect"]["rules"]}
        self.assertEqual(set(REQUIRED_RULES), covered)

    def test_rule_vocabulary_is_pinned(self):
        """Protected behavior: the rule ids and their order are the
        frozen vocabulary; a renamed or reordered rule breaks every
        consumer that matches on rule ids."""
        mod = _mod()
        self.assertEqual(REQUIRED_RULES, tuple(mod.RULES))

    def test_duty_set_is_role_authority_roles(self):
        """Protected behavior: duties are the role_authority ROLES set
        (reuse, no second role catalog); a persona or divergent duty
        name is refused as grant-invalid. Catches a forked role list."""
        mod = _mod()
        ra = _ra()
        self.assertIs(ra, mod.ra)
        case = _case("role-contract.allow.builder-write")
        for duty in ra.ROLES:
            with self.subTest(duty=duty):
                case["grant"]["duty"] = duty
                allowed, rules = _decide(mod, case)
                self.assertNotIn("grant-invalid", rules)
        case["grant"]["duty"] = "planner"
        self.assertEqual((False, ["grant-invalid"]),
                         _decide(mod, case))

    def test_malformed_input_fails_closed(self):
        """Protected behavior: any missing, extra, or wrongly typed
        field, or a malformed clock or other grant, is refused with a
        rule id and never raises. Catches fail-open and crash-open
        handling of bad input."""
        mod = _mod()
        base = _case("role-contract.allow.builder-write")
        missing_scope = copy.deepcopy(base["grant"])
        del missing_scope["scope"]
        extra_key = copy.deepcopy(base["grant"])
        extra_key["admin"] = True
        bad_sha = copy.deepcopy(base["grant"])
        bad_sha["head_sha"] = "A1" * 20
        cases = [
            ("grant-none", None, base["action"], {}),
            ("grant-missing-scope", missing_scope, base["action"], {}),
            ("grant-extra-key", extra_key, base["action"], {}),
            ("grant-bad-sha", bad_sha, base["action"], {}),
            ("action-not-mapping", base["grant"], "write", {}),
            ("action-unknown-kind", base["grant"],
             {"kind": "delete", "path": "src/x.py"}, {}),
            ("now-unparseable", base["grant"], base["action"],
             {"now": "not-a-time"}),
            ("other-grants-not-list", base["grant"], base["action"],
             {"other_grants": None}),
            ("other-grant-none", base["grant"], base["action"],
             {"other_grants": [None]}),
        ]
        for label, grant, action, extra in cases:
            with self.subTest(case=label):
                kwargs = {"now": base["now"],
                          "current_head": base["current_head"]}
                kwargs.update(extra)
                allowed, rules = mod.decide(grant, action, **kwargs)
                self.assertFalse(allowed)
                self.assertTrue(rules)
                self.assertTrue(set(rules) <= set(REQUIRED_RULES))

    def test_expiry_window_boundaries(self):
        """Protected behavior: a grant is live on [issued_at,
        expires_at); expiry at exactly expires_at refuses, a window of
        exactly one hour is accepted, and one second more is refused as
        grant-invalid. Catches off-by-one expiry and an unbounded TTL."""
        mod = _mod()
        base = _case("role-contract.allow.builder-write")
        base["grant"]["issued_at"] = "2026-10-28T10:00:00Z"
        base["grant"]["expires_at"] = "2026-10-28T11:00:00Z"
        self.assertEqual((True, []), _decide(mod, base, now=base["now"]))
        self.assertEqual(
            (True, []),
            _decide(mod, base, now="2026-10-28T10:00:00Z"))
        self.assertEqual(
            (False, ["grant-expired"]),
            _decide(mod, base, now="2026-10-28T11:00:00Z"))
        base["grant"]["expires_at"] = "2026-10-28T11:00:01Z"
        self.assertEqual((False, ["grant-invalid"]),
                         _decide(mod, base, now=base["now"]))

    def test_owner_override_never_waives_non_waivable_rules(self):
        """Protected behavior: a valid owner override waives only
        grant-expired and stale-head. Self-grant, forbidden self-review,
        unverified provenance, unauthorized GitHub writes and
        out-of-scope writes stay refused with the same rule ids.
        Catches an override that becomes a general bypass."""
        mod = _mod()
        override = {
            "owner": "kgsmith19",
            "decision": "waive everything for this run",
            "scope": "run-300-a",
        }
        for case_id in NON_WAIVABLE_IDS:
            with self.subTest(case=case_id):
                case = _case(case_id)
                case["owner"] = "kgsmith19"
                case["override"] = override
                allowed, rules = _decide(mod, case)
                self.assertFalse(allowed)
                self.assertEqual(_case(case_id)["expect"]["rules"], rules)

    def test_github_identity_is_required_only_for_posting(self):
        """Protected behavior: a local evidence write needs no GitHub
        identity; post and mutate_github need one. The same grant
        without identity is allowed for write and refused for post.
        Catches identity demands on local work and identity-free posts."""
        mod = _mod()
        case = _case("role-contract.allow.github-app-post")
        del case["grant"]["github_identity"]
        case["action"] = {"kind": "write",
                          "path": "evidence/review/verdict.json",
                          "risk": "R2"}
        self.assertEqual((True, []), _decide(mod, case))
        case["action"] = {"kind": "post", "risk": "R2"}
        self.assertEqual((False, ["unauthorized-github-write"]),
                         _decide(mod, case))

    def test_unknown_risk_is_treated_as_r3(self):
        """Protected behavior: an unrecognized risk level is treated as
        R3, so a same-family review that is advisory at R1 is blocking
        at an unknown level. Catches a downgrade of unknown risk to
        advisory."""
        mod = _mod()
        case = _case("role-contract.refuse.unknown-risk-treated-as-r3")
        case["action"]["risk"] = "R1"
        self.assertEqual((True, []), _decide(mod, case))
        case["action"]["risk"] = "R9"
        self.assertEqual((False, ["forbidden-self-review"]),
                         _decide(mod, case))

    def test_provenance_must_match_declared_family(self):
        """Protected behavior: provider_observed must belong to the
        declared provider family (text before '/'); an empty or
        mismatched observation is unverified-provenance. Catches a
        grant that claims one family and was served by another."""
        mod = _mod()
        case = _case("role-contract.allow.builder-write")
        case["grant"]["provenance"]["provider_observed"] = \
            "anthropic/fast-tier-a"
        self.assertEqual((True, []), _decide(mod, case))
        case["grant"]["provenance"]["provider_observed"] = "   "
        self.assertEqual((False, ["unverified-provenance"]),
                         _decide(mod, case))

    def test_override_must_pass_owner_override_ok(self):
        """Protected behavior: an override is honored only when it passes
        role_authority.owner_override_ok (owner kgsmith19, non-empty
        decision and scope) and names the owner the decision is made for.
        Any other override refuses with owner-override and waives
        nothing. Catches an empty-scope or unnamed-owner override being
        treated as an explicit owner decision."""
        mod = _mod()
        expired = _case("role-contract.refuse.expired")
        valid = {"owner": "kgsmith19", "decision": "extend once",
                 "scope": "run-300-a"}
        attempts = (
            ("empty-scope", dict(valid, scope=""), None),
            ("blank-decision", dict(valid, decision=" "), None),
            ("wrong-owner-unnamed", dict(valid, owner="someone-else"),
             None),
            ("owner-param-mismatch", valid, "someone-else"),
            ("not-a-mapping", "kgsmith19", None),
        )
        for label, override, owner in attempts:
            with self.subTest(override=label):
                case = copy.deepcopy(expired)
                case["override"] = override
                allowed, rules = _decide(mod, case, owner=owner)
                self.assertEqual(
                    (False, ["grant-expired", "owner-override"]),
                    (allowed, rules))

    def test_collaboration_flows_match_record(self):
        """Protected behavior: every step of every collaboration flow
        yields the expected decision and rule ids through record(), and
        each allowed or refused step emits a receipt with exactly the
        pinned keys. Catches a flow that stops proving its SDLC steps."""
        mod = _mod()
        self.assertTrue(hasattr(mod, "record"),
                        "record() is missing from tools/role_contract.py")
        self.assertTrue(_doc()["flows"])
        for flow in _doc()["flows"]:
            for index, step in enumerate(flow["steps"]):
                label = "%s[%d]" % (flow["id"], index)
                with self.subTest(step=label):
                    self.assertLessEqual(set(step), FLOW_STEP_KEYS)
                    kwargs = {k: v for k, v in step.items()
                              if k != "expect"}
                    receipt = mod.record(**kwargs)
                    self.assertEqual(RECEIPT_KEYS, set(receipt))
                    self.assertEqual(1, receipt["schema_version"])
                    self.assertEqual(step["expect"]["decision"],
                                     receipt["decision"])
                    self.assertEqual(step["expect"]["rules"],
                                     receipt["rules"])
                    self.assertEqual(step.get("specialty"),
                                     receipt["specialty"])

    def test_delegation_and_evidence_edges(self):
        """Protected behavior: a delegated grant from a grantor who holds
        the same duty is allowed; a passing claim proves acceptance only
        when it lists an output artifact path; missing-evidence applies
        to verifier and reviewer, never to a builder. Catches an
        over-broad escalation check and a claim that proves nothing."""
        mod = _mod()
        self.assertTrue(hasattr(mod, "record"),
                        "record() is missing from tools/role_contract.py")
        base = _case("role-contract.allow.builder-write")
        base["grant"]["grantor"] = "lead-1"
        holder = dict(base["grant"], actor_id="lead-1", grantor="orchestrator-1",
                      scope=["plans/"])
        self.assertEqual(
            (True, []),
            mod.decide(base["grant"], base["action"], now=base["now"],
                       current_head=base["current_head"],
                       other_grants=[holder], delegated=True))
        verifier = _case("role-contract.allow.local-evidence-no-identity")
        out = [{"path": "evidence/verification/run-a.json",
                "sha256": "5" * 64}]
        unlisted = [{"id": "AC1", "result": "pass",
                     "artifacts": ["evidence/verification/other.json"]}]
        listed = [{"id": "AC1", "result": "pass",
                   "artifacts": ["evidence/verification/run-a.json"]}]
        shared = {"task": "std#301", "now": verifier["now"],
                  "current_head": verifier["current_head"],
                  "acceptance_ids": ["AC1"], "output_artifacts": out}
        refused = mod.record(verifier["grant"], verifier["action"],
                             claims=unlisted, **shared)
        self.assertEqual(["missing-evidence"], refused["rules"])
        proven = mod.record(verifier["grant"], verifier["action"],
                            claims=listed, **shared)
        self.assertEqual(("allow", []), (proven["decision"], proven["rules"]))
        # A verifier or reviewer that names no acceptance id proves
        # nothing, so it is refused rather than vacuously allowed.
        vacuous = mod.record(verifier["grant"], verifier["action"],
                             claims=listed, **dict(shared, acceptance_ids=[]))
        self.assertEqual(["missing-evidence"], vacuous["rules"])
        builder = mod.record(
            base["grant"], base["action"], task="std#301",
            now=base["now"], current_head=base["current_head"],
            acceptance_ids=["AC1"])
        self.assertEqual(("allow", []), (builder["decision"],
                                         builder["rules"]))

    def test_four_role_flow_separates_harnesses_and_families(self):
        """Protected behavior: in flow.four-role every step names a
        different harness in provenance.source, and the reviewer and
        verifier families differ from the builder family. Catches a
        flow that reuses one harness or one family for independent
        review."""
        flow = [f for f in _doc()["flows"]
                if f["id"] == "flow.four-role"][0]
        grants = [step["grant"] for step in flow["steps"]]
        self.assertEqual(4, len(grants))
        sources = [g["provenance"]["source"] for g in grants]
        self.assertEqual(4, len(set(sources)))
        duties = [g["duty"] for g in grants]
        self.assertEqual(["spec_author", "builder", "reviewer", "verifier"],
                         duties)
        builder = grants[1]["provider"]["family"]
        self.assertNotEqual(builder, grants[2]["provider"]["family"])
        self.assertNotEqual(builder, grants[3]["provider"]["family"])

    def test_specialty_is_receipt_only(self):
        """Protected behavior: a specialist carries specialty on the
        receipt, never as a grant key; the security flow's reviewer
        grant has the grant keys only. Catches a specialty leaking into
        grant authority."""
        flow = [f for f in _doc()["flows"]
                if f["id"] == "flow.security-specialist"][0]
        reviewer = flow["steps"][1]
        self.assertEqual("security", reviewer["specialty"])
        self.assertEqual("reviewer", reviewer["grant"]["duty"])
        self.assertNotIn("specialty", reviewer["grant"])

    def test_record_rejects_malformed_inputs_as_action_invalid(self):
        """Protected behavior: a malformed artifact, claim or acceptance
        list refuses with action-invalid and never raises; the receipt
        still records the refusal. Catches fail-open artifact handling."""
        mod = _mod()
        self.assertTrue(hasattr(mod, "record"),
                        "record() is missing from tools/role_contract.py")
        base = _case("role-contract.allow.builder-write")
        bad_inputs = (
            {"input_artifacts": [{"path": "src/a.py"}]},
            {"output_artifacts": [{"path": "", "sha256": "0" * 64}]},
            {"acceptance_ids": "AC1"},
            {"claims": [{"id": "AC1", "result": "pass"}]},
        )
        for extra in bad_inputs:
            with self.subTest(extra=sorted(extra)):
                receipt = mod.record(
                    base["grant"], base["action"], task="std#301",
                    now=base["now"], current_head=base["current_head"],
                    **extra)
                self.assertEqual("refuse", receipt["decision"])
                self.assertEqual(["action-invalid"], receipt["rules"])


if __name__ == "__main__":
    unittest.main()
