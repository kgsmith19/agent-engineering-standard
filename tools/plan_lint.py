"""Stage 26 Standard half: plan-shape discipline for design/planning
help.

Bounds brainstorming and plan writing so design help stays precise
without reopening approved decisions or generating mega-plans. The lint
consumes a PLAN as plain data (a dict per the field set below) — never a
file: plans stay local/gitignored, there is no permanent plan tracker,
and this module performs no filesystem access itself. ``thinness`` is
caller-supplied, scored by ``tools/thinness.py``; the lint never
recomputes it, it only maps the total onto the plan bands (micro 0-3 /
preferred 4-6 / split-required 7-8 / never-one-Builder 9-12) through
``thinness.classify``.

Contract semantics (fail closed, with repair guidance):

- ``entry_rule`` is the precise entry rule for design/planning help.
  Micro tasks (thinness 0-3, no behavior change) get no plan and minimal
  ceremony — design/planning help must not impose ceremony on a
  micro-task. An owner-approved Spec routes to execution planning and
  never re-design. A behavior change requires a red-first bounded plan.
  Thinness 7-8 may plan architecturally with exactly one outcome;
  thinness 9-12 is never-one-Builder and must split before planning.
- ``lint(plan)`` returns repair findings; empty means the plan is
  acceptable. One outcome per plan: multiple declared outcomes hide
  independent PRs, and such a plan must split.
- A bounded plan declares exactly one shippable outcome and at most
  ``MAX_STEPS`` steps; if it changes behavior (any ``implement`` step) it
  must hold a ``red`` step before the first ``implement`` step (no true
  RED is a finding). Every injected ``research_refs`` entry must be
  cited by some step's ``cites``; uncited research is irrelevant
  research. A micro plan (``MICRO_STEPS`` or fewer steps) imposes at
  most the narrowest check.
- An architectural plan is allowed only in the split-required band
  (thinness 7-8) with exactly one outcome; thinness 9-12 is a hard
  never-one-Builder finding. The step cap still applies.
- A spike produces findings, not shippable code: ``red``/``implement``
  steps are a misdeclaration, and evidence beyond a short findings note
  is ceremony. The step cap still applies (a spike is bounded
  exploration).
- An owner-approved Spec's decisions are inputs, not proposals: on every
  shape, a plan that reopens an approved decision is rejected.
"""

import os
import sys
from typing import Any, Dict, List

SHAPES = ("spike", "bounded", "architectural")

SPEC_STATUSES = ("none", "draft", "owner_approved")

STEP_KINDS = ("red", "implement", "verify", "research")

MAX_STEPS = 7  # preferred-band thin-slice cap; more steps is a mega-plan

MICRO_STEPS = 2  # a plan this small is micro work

MIN_EVIDENCE_FOR_MICRO = 1  # the narrowest check a micro plan may impose

MAX_EVIDENCE_FOR_SPIKE = 1  # a spike needs only a short findings note

BAND_NAMES = {
    "micro": "micro",
    "preferred": "preferred",
    "medium": "split-required",
    "large": "never-one-Builder",
}


def _thinness():
    """Import the Stage 7 thinness scorer from this module's directory."""
    tools_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, tools_dir)
    try:
        import thinness
        return thinness
    finally:
        sys.path.remove(tools_dir)


def band(thinness_total: int) -> str:
    """Map a thinness total (0-12) onto the Stage 26 plan bands.

    Band names follow the plan contract (micro 0-3 / preferred 4-6 /
    split-required 7-8 / never-one-Builder 9-12); thresholds come from
    ``tools/thinness.classify`` so there is one source of truth.
    """
    return BAND_NAMES[_thinness().classify(int(thinness_total))]


def _cited_refs(steps: List[Any]) -> set:
    """Union of the steps' ``cites`` entries (the citation convention)."""
    cited: set = set()
    for step in steps:
        if isinstance(step, dict) and isinstance(step.get("cites"), list):
            cited.update(str(c) for c in step["cites"])
    return cited


def lint(plan: Dict[str, Any]) -> List[str]:
    """Return repair findings for one plan; empty means acceptable.

    The plan is plain data, never a file. Structural malformations fail
    closed with repair strings; thinness is trusted as caller-supplied
    input and only range-checked.
    """
    findings: List[str] = []
    if not isinstance(plan, dict):
        return ["plan must be a mapping of plain data, not %s"
                % type(plan).__name__]

    shape = plan.get("shape")
    if shape not in SHAPES:
        findings.append("unknown plan shape %r: shape is one of %s"
                        % (shape, ", ".join(SHAPES)))
    spec_status = plan.get("spec_status")
    if spec_status not in SPEC_STATUSES:
        findings.append("unknown spec_status %r: spec_status is one of %s"
                        % (spec_status, ", ".join(SPEC_STATUSES)))
    if not str(plan.get("title") or "").strip():
        findings.append("plan needs a non-empty title")

    outcomes = plan.get("outcomes")
    if not isinstance(outcomes, list) or not all(
            isinstance(o, str) and o.strip() for o in outcomes):
        findings.append("outcomes must be a list of non-empty strings")
        outcomes = []

    steps = plan.get("steps")
    if not isinstance(steps, list):
        findings.append("steps must be a list of step mappings")
        steps = []
    else:
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                findings.append("step %d must be a mapping" % i)
                continue
            if step.get("kind") not in STEP_KINDS:
                findings.append(
                    "step %d has unknown kind %r: kind is one of %s"
                    % (i, step.get("kind"), ", ".join(STEP_KINDS)))
            if not str(step.get("title") or "").strip():
                findings.append("step %d needs a non-empty title" % i)

    thinness_total = plan.get("thinness")
    if (not isinstance(thinness_total, int)
            or isinstance(thinness_total, bool)
            or not 0 <= thinness_total <= 12):
        findings.append(
            "thinness must be an int 0-12 scored by tools/thinness.py")
        thinness_total = None

    evidence = plan.get("evidence")
    if not isinstance(evidence, list) or not all(
            isinstance(e, str) and e.strip() for e in evidence):
        findings.append("evidence must be a list of non-empty strings")
        evidence = []

    decisions = plan.get("decisions")
    if not isinstance(decisions, list):
        findings.append("decisions must be a list of decision mappings")
        decisions = []

    research_refs = plan.get("research_refs")
    if not isinstance(research_refs, list) or not all(
            isinstance(r, str) and r.strip() for r in research_refs):
        findings.append("research_refs must be a list of non-empty strings")
        research_refs = []

    cited_refs = plan.get("cited_refs")
    if cited_refs is not None and (
            not isinstance(cited_refs, list)
            or not all(isinstance(c, str) for c in cited_refs)):
        findings.append("cited_refs must be a list of strings")

    red_positions = [
        i for i, step in enumerate(steps)
        if isinstance(step, dict) and step.get("kind") == "red"]
    implement_positions = [
        i for i, step in enumerate(steps)
        if isinstance(step, dict) and step.get("kind") == "implement"]
    changes_behavior = bool(implement_positions)
    layer_tags = sorted({
        str(step.get("layer")) for step in steps
        if isinstance(step, dict) and str(step.get("layer") or "").strip()})
    cited = _cited_refs(steps)

    # Re-litigation (all shapes): approved decisions are inputs.
    if spec_status == "owner_approved":
        for decision in decisions:
            if (isinstance(decision, dict)
                    and decision.get("approved")
                    and decision.get("reopen")):
                findings.append(
                    "re-litigates owner-approved decision %s: approved "
                    "decisions are inputs, not proposals"
                    % decision.get("id", "<unnamed>"))

    # Hidden multiple PRs (all shapes).
    if len(outcomes) > 1:
        findings.append(
            "plan hides %d independent PRs; split into one outcome per "
            "plan" % len(outcomes))

    # Mega-plan cap (all shapes).
    if len(steps) > MAX_STEPS:
        findings.append(
            "mega-plan: %d steps exceed the %d-step thin-slice cap; "
            "split into thin slices" % (len(steps), MAX_STEPS))

    # True RED and layer-only discipline for behavior-changing plans.
    if shape in ("bounded", "architectural") and changes_behavior:
        if not red_positions:
            findings.append(
                "no true RED: a behavior-changing plan must write the "
                "failing test before the first implement step")
        elif red_positions[0] > implement_positions[0]:
            findings.append(
                "no true RED: the first red step must precede the first "
                "implement step (write the failing test first)")
        if not red_positions and len(layer_tags) > 1:
            findings.append(
                "layer-only plan: %d layer tags (%s) with no red step; "
                "slice vertically through one behavior instead"
                % (len(layer_tags), ", ".join(layer_tags)))

    # Irrelevant research: injected refs must be cited by some step.
    if shape in ("bounded", "architectural"):
        for ref in research_refs:
            if ref not in cited:
                findings.append(
                    "irrelevant research: ref %r is not cited by any "
                    "step; remove it or cite the step that uses it" % ref)
    if isinstance(cited_refs, list):
        for ref in cited_refs:
            if ref not in cited:
                findings.append(
                    "cited_refs entry %r is not cited by any step; "
                    "recompute cited_refs from the steps' cites" % ref)

    if shape == "spike":
        for i, step in enumerate(steps):
            if isinstance(step, dict) and step.get("kind") in (
                    "red", "implement"):
                findings.append(
                    "misdeclared spike: step %d (%r) is %s; spikes "
                    "produce findings, not shippable code — declare "
                    "shape 'bounded' for behavior change"
                    % (i, step.get("title"), step.get("kind")))
        if len(evidence) > MAX_EVIDENCE_FOR_SPIKE:
            findings.append(
                "ceremony: a spike needs only a short findings note, "
                "not %d evidence requirements" % len(evidence))

    if shape == "bounded":
        if not outcomes:
            findings.append(
                "bounded plan must declare exactly one shippable "
                "outcome; none declared")
        if (len(steps) <= MICRO_STEPS
                and len(evidence) > MIN_EVIDENCE_FOR_MICRO):
            findings.append(
                "ceremony: a micro plan (%d steps) imposes %d evidence "
                "requirements; keep only the narrowest check"
                % (len(steps), len(evidence)))

    if shape == "architectural" and thinness_total is not None:
        plan_band = band(thinness_total)
        if plan_band == "never-one-Builder":
            findings.append(
                "thinness %d is never-one-Builder: do not plan this as "
                "one Builder assignment; split into more work items"
                % thinness_total)
        elif plan_band == "split-required":
            if len(outcomes) != 1:
                findings.append(
                    "split required: an architectural plan (thinness %d) "
                    "is allowed only with exactly one outcome; %d "
                    "declared" % (thinness_total, len(outcomes)))
        else:
            findings.append(
                "misdeclared shape 'architectural': thinness %d is %s; "
                "architectural plans require thinness 7-8 (use bounded)"
                % (thinness_total, plan_band))

    return findings


def entry_rule(task: Dict[str, Any]) -> Dict[str, Any]:
    """The precise entry rule for design/planning help.

    Given ``task = {"thinness": int, "spec_status": str,
    "behavior_change": bool}``, return ``{"plan_shape": ..., "ceremony":
    ..., "notes": [...]}``. Raises ValueError on a thinness outside
    0-12, matching tools/thinness.py's fail-closed inputs.
    """
    thinness_total = task.get("thinness")
    if (not isinstance(thinness_total, int)
            or isinstance(thinness_total, bool)
            or not 0 <= thinness_total <= 12):
        raise ValueError("task thinness must be an int 0-12")
    spec_status = str(task.get("spec_status", "none"))
    behavior_change = bool(task.get("behavior_change", False))
    plan_band = band(thinness_total)
    notes: List[str] = []

    if plan_band == "micro" and not behavior_change:
        shape = "none"
        ceremony = "minimal"
        notes.append(
            "micro task (thinness 0-3, no behavior change): no plan and "
            "minimal ceremony; design/planning help must not impose "
            "ceremony on a micro-task")
        if spec_status == "owner_approved":
            notes.append(
                "spec owner-approved: implement the approved decisions; "
                "do not re-open design")
        return {"plan_shape": shape, "ceremony": ceremony,
                "notes": notes}

    if plan_band == "never-one-Builder":
        return {
            "plan_shape": "none",
            "ceremony": "standard",
            "notes": [
                "thinness %d is never-one-Builder: split into thin work "
                "items before planning; no single plan may cover it"
                % thinness_total],
        }

    if spec_status == "owner_approved":
        shape = "bounded"
        ceremony = "standard"
        notes.append(
            "spec owner-approved: implement the approved decisions; do "
            "not re-open design")
    elif behavior_change:
        shape = "bounded"
        ceremony = "standard"
    elif plan_band == "split-required":
        return {
            "plan_shape": "architectural",
            "ceremony": "standard",
            "notes": [
                "thinness 7-8: an architectural plan is allowed only "
                "with exactly one outcome; split otherwise"],
        }
    else:
        shape = "bounded"
        ceremony = "standard"
    if behavior_change:
        notes.append(
            "behavior change: red-first bounded plan (write the failing "
            "test before the first implement step)")
    return {"plan_shape": shape, "ceremony": ceremony, "notes": notes}
