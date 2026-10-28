"""PR Gate aggregation check (Issue #314).

The gate job in ``.github/workflows/pr-gate.yml`` calls this module. The
decision is the pure function ``evaluate``; ``main`` only reads the
workflow environment and prints the result.

Environment (set by the gate job):
  NEEDS           JSON object from ``toJSON(needs)``
  REQUIRED_JOBS   space-separated job ids that must conclude ``success``
  OPTIONAL_JOBS   space-separated job ids reported as warnings only
"""

import json
import os
import sys


def evaluate(needs, required, optional):
    """Return ``(problems, warnings)`` for the gated jobs.

    ``needs`` maps job id to a dict with a ``result`` key. Every job in
    ``required | optional`` must be present, and no other job may appear.
    A required job must conclude exactly ``success``. An optional job that
    does not conclude ``success`` is a warning.
    """
    problems = []
    warnings = []

    expected = set(required) | set(optional)
    if set(needs) != expected:
        problems.append(
            "gated jobs %s do not equal the expected set %s"
            % (sorted(needs), sorted(expected))
        )

    for job, info in sorted(needs.items()):
        result = info.get("result")
        if job in required and result != "success":
            problems.append("REQUIRED job %s concluded %r" % (job, result))
        elif job in optional and result != "success":
            warnings.append("optional job %s concluded %r" % (job, result))
    return problems, warnings


def main(environ=None, out=None):
    env = os.environ if environ is None else environ
    out = sys.stdout if out is None else out
    # Fail closed: the only accepted required conclusion is 'success'. The
    # workflow pins it explicitly so the strict rule is visible in the gate.
    if env.get("REQUIRED_RESULT") != "success":
        print("ERROR: REQUIRED_RESULT must be 'success' (fail closed)", file=out)
        return 1

    needs = json.loads(env["NEEDS"])
    required = set(env["REQUIRED_JOBS"].split())
    optional = set(env.get("OPTIONAL_JOBS", "").split())

    problems, warnings = evaluate(needs, required, optional)

    for warning in warnings:
        print("WARNING:", warning, file=out)
    for problem in problems:
        print("ERROR:", problem, file=out)

    if problems:
        print("\nGate FAILED: Required jobs did not succeed", file=out)
        return 1
    if warnings:
        print("\nGate PASSED: Optional jobs had issues but required jobs succeeded",
              file=out)
        return 0
    print("\nGate PASSED: All jobs succeeded", file=out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
