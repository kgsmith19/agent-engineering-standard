"""Stage 25a Standard half: the Controlled Superpowers Router.

Routes Superpowers by work phase instead of keeping a resident process
empire in context. The router consumes Stage 20a SkillDescriptor-shaped
records (contract v1.0.0, additive-only) as plain data and turns each
phase into capability requests resolved by the Stage 20b profile
compiler's ``select_candidates``: routing sees names, blurbs, budget
estimates, and dependency edges — never bodies. Bodies are never loaded
at routing time and this module performs no filesystem access itself.

Routing semantics (fail closed, with repair guidance):

- A phase must be one of the ten categories in ``PHASES``. An unknown
  phase is a finding, not a crash; nothing is selected.
- ``DEFAULT_ROUTES`` maps each phase to its process-skill request(s).
  Requests are Standard policy — semantic IDs or slugs — resolved
  against whatever catalog the caller supplies; absent entries surface
  as profile-compiler repair findings.
- Signals adjust routing deterministically: an owner-approved Spec in
  the design phase suppresses the brainstorming trigger; a declared
  behavior change in the implement phase keeps the TDD capability
  requested first; an unexpected failure in a write phase overrides the
  route to systematic debugging before any fix.
- Over-budget / multi-skill rejection belongs to the profile compiler's
  one-process-plus-one-domain policy. The router never raises the
  budget and never truncates selections; any compile finding means no
  selection is delivered.
- A provider without Superpowers gets an honest manual fallback from
  ``MANUAL_FALLBACKS``: no capability selection, no faked skill load.
"""

import os
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

PHASES = (
    "bootstrap", "design", "spec", "execute", "implement",
    "review", "debug", "verify", "integrate", "document",
)

WRITE_PHASES = ("implement", "execute", "integrate")

DEFAULT_ROUTES = {
    "bootstrap": ("using-superpowers",),
    "design": ("brainstorming",),
    "spec": ("writing-plans",),
    "execute": ("executing-plans",),
    "implement": ("test-driven-development",),
    "review": ("requesting-code-review",),
    "debug": ("systematic-debugging",),
    "verify": ("verification-before-completion",),
    "integrate": ("finishing-a-development-branch",),
    "document": ("writing-clearly-and-concisely",),
}

MANUAL_FALLBACKS = {
    "bootstrap": "read the governing rules and identify the active task "
                 "before touching code",
    "design": "explore intent and constraints with the owner before "
              "committing to a design",
    "spec": "write a precise spec with exact acceptance criteria before "
            "implementation",
    "execute": "follow the written plan step by step, marking each step "
               "done as it lands",
    "implement": "write the failing test first, then the smallest change "
                 "that passes it",
    "review": "request independent review of the change with evidence "
              "citations before merging",
    "debug": "reproduce the failure, isolate the root cause before "
             "proposing any fix",
    "verify": "run the narrowest relevant check and read its actual "
              "output before claiming success",
    "integrate": "land the work through the PR gate with fresh evidence "
                 "at the exact head",
    "document": "state the objective in precise language with concrete "
                "examples and no padding",
}


def _profile_compiler():
    """Import the Stage 20b compiler from this module's directory."""
    tools_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, tools_dir)
    try:
        import profile_compiler
        return profile_compiler
    finally:
        sys.path.remove(tools_dir)


@dataclass
class RouteResult:
    """One phase-routing outcome from descriptors alone."""

    selected: List[Dict[str, Any]] = field(default_factory=list)
    findings: List[str] = field(default_factory=list)
    suppressed: List[str] = field(default_factory=list)
    discovery_tokens: int = 0
    body_tokens_est: int = 0
    provider: str = ""
    phase: str = ""
    requests: List[str] = field(default_factory=list)
    fallback: bool = False
    manual_process: str = ""

    @property
    def ok(self) -> bool:
        return not self.findings


def route(descriptors: List[Dict[str, Any]],
          phase: str,
          *,
          signals: Optional[Dict[str, Any]] = None,
          provider: str = "claude",
          superpowers: bool = True,
          budget_tokens: Optional[int] = None,
          extra_requests: Optional[List[str]] = None) -> RouteResult:
    """Route one phase to capability requests resolved against the
    caller-supplied descriptor catalog — no body loading, no I/O.

    Raises:
        ValueError: On duplicate capabilities (index integrity), via the
            profile compiler.
    """
    signals = dict(signals or {})
    if phase not in PHASES:
        return RouteResult(
            provider=provider, phase=str(phase),
            findings=["unknown phase %r: route is one of %s"
                      % (phase, ", ".join(PHASES))])

    if not superpowers:
        return RouteResult(
            provider=provider, phase=phase, fallback=True,
            manual_process=MANUAL_FALLBACKS[phase])

    requests = list(DEFAULT_ROUTES[phase])
    suppressed: List[str] = []
    if signals.get("unexpected_failure") and phase in WRITE_PHASES:
        suppressed.append(
            "unexpected_failure in phase %r overrides the default route "
            "(%s) to the debug route (%s): systematic debugging before "
            "any fix" % (phase, ", ".join(requests),
                         ", ".join(DEFAULT_ROUTES["debug"])))
        requests = list(DEFAULT_ROUTES["debug"])
    elif phase == "design" and signals.get("owner_spec_approved"):
        suppressed.append(
            "owner_spec_approved in phase 'design' suppresses the "
            "brainstorming trigger: an owner-approved Spec already "
            "covers design; brainstorming is not re-triggered")
        requests = [r for r in requests if r != "brainstorming"]
    if (phase == "implement" and signals.get("behavior_change")
            and "test-driven-development" in requests):
        requests = ["test-driven-development"] + [
            r for r in requests if r != "test-driven-development"]

    if extra_requests:
        requests = requests + [str(r) for r in extra_requests]

    compiled = _profile_compiler().select_candidates(
        descriptors, requests, budget_tokens=budget_tokens,
        provider=provider)

    result = RouteResult(
        findings=list(compiled.findings),
        suppressed=suppressed,
        discovery_tokens=compiled.discovery_tokens,
        body_tokens_est=compiled.body_tokens_est,
        provider=provider, phase=phase, requests=requests,
    )
    if compiled.ok:
        result.selected = compiled.selected
    return result
