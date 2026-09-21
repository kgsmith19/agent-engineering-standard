"""T15 Standard half: task baseline with frozen, stale, and fragmented kinds.

The baseline corpus captures at least one task of each of the
seven kinds — frozen, local, shared-schema, missing-access,
ambiguous, stale, fragmented — with the kind labeled per task,
plus a NO_CHANGE task (no code change warranted, recorded as a
first-class verdict), an over-fragmented task (fragmented below
useful scope with the harm recorded), and total effort per task
(controller + workers + reviews + retries + rotations, units
stated). Frozen tasks record their frozen Mold so later
comparison runs against the same contract. A narrow patch that
fixes one kind's symptom while breaking its wider contract (the
broken-narrow-patch canary) is rejected. The corpus format
supports matched tasks + repeats + held-out selection for the
T16 pilot and T23 benchmark without re-collecting.

Pure functions: no I/O, no network — data in, violations out.
Frozen rules, stable output order.
"""

from typing import Any, Dict, List, Optional, Set, Tuple

# The seven baseline task kinds (AC1). Every kind needs a task.
TASK_KINDS = (
    "frozen",
    "local",
    "shared-schema",
    "missing-access",
    "ambiguous",
    "stale",
    "fragmented",
)

# Effort dimensions summed into total effort (AC6, units stated).
EFFORT_DIMENSIONS = (
    "controller",
    "workers",
    "reviews",
    "retries",
    "rotations",
)


def check_inventory(tasks: Any) -> List[str]:
    """Return violations for one baseline task list.

    Every one of the seven kinds must appear at least once with
    its kind labeled; a missing kind fails naming the kind, so
    the baseline never silently drops a category.
    """
    violations: List[str] = []
    if not isinstance(tasks, list):
        return ["baseline tasks must be a list"]
    seen = set()
    for task in tasks:
        if isinstance(task, dict) and task.get("kind"):
            seen.add(str(task["kind"]))
    for kind in TASK_KINDS:
        if kind not in seen:
            violations.append(
                "baseline missing kind %r: one task of each of "
                "the seven kinds is required" % (kind,))
    unknown = seen - set(TASK_KINDS) - {"no-change", "over-fragmented"}
    for kind in sorted(unknown):
        violations.append(
            "baseline task has unknown kind %r" % (kind,))
    return violations


def check_no_change(tasks: Any) -> List[str]:
    """Return violations when no NO_CHANGE task is captured.

    The corpus includes a task whose correct outcome is
    NO_CHANGE, recorded as a first-class verdict (not an
    omission); without one, the baseline cannot prove the
    pipeline ever correctly does nothing.
    """
    if not isinstance(tasks, list):
        return ["baseline tasks must be a list"]
    for task in tasks:
        if isinstance(task, dict) and task.get(
                "verdict") == "NO_CHANGE":
            return []
    return ["baseline has no NO_CHANGE task: a first-class "
            "no-change verdict is required"]


def check_over_fragmentation(tasks: Any) -> List[str]:
    """Return violations when no over-fragmented task is captured.

    The corpus includes a task fragmented below useful scope,
    labeled over-fragmented with the harm recorded; without one,
    the baseline cannot recognize harmful fragmentation.
    """
    if not isinstance(tasks, list):
        return ["baseline tasks must be a list"]
    for task in tasks:
        if not isinstance(task, dict):
            continue
        if task.get("kind") == "over-fragmented" or task.get(
                "over_fragmented"):
            if not task.get("harm"):
                return ["over-fragmented task %r records no harm" % (
                    task.get("id", "?"),)]
            return []
    return ["baseline has no over-fragmented task: fragmentation "
            "harm must be captured"]


def check_frozen_molds(tasks: Any) -> List[str]:
    """Return violations for frozen tasks without a frozen Mold.

    Every frozen task records its frozen Mold (verification
    contract version) so later comparison runs against the same
    contract; a frozen task without one fails naming the task.
    """
    violations: List[str] = []
    if not isinstance(tasks, list):
        return ["baseline tasks must be a list"]
    for task in tasks:
        if not isinstance(task, dict):
            continue
        if task.get("kind") == "frozen" and not task.get(
                "frozen_mold"):
            violations.append(
                "frozen task %r records no frozen Mold" % (
                    task.get("id", "?"),))
    return violations


def check_narrow_patch(patch: Any) -> List[str]:
    """Return violations for a broken narrow patch.

    A fixture that fixes one task kind's symptom while breaking
    its wider contract (e.g., the local symptom while violating
    the shared schema) is rejected naming the breakage — the
    canary that proves the baseline is a contract, not a list.
    """
    violations: List[str] = []
    if not isinstance(patch, dict):
        return ["narrow patch must be a mapping"]
    if patch.get("breaks_contract"):
        violations.append(
            "broken narrow patch rejected: fixes %r while "
            "breaking %r" % (patch.get("fixes", "?"),
                             patch.get("breaks_contract", "?")))
    if not patch.get("fixes"):
        violations.append(
            "narrow patch names no fixed symptom")
    return violations


def check_effort(tasks: Any) -> List[str]:
    """Return violations for tasks without total effort.

    Every baseline task records total effort = controller +
    workers + reviews + retries + rotations with units stated;
    a task missing any dimension or its units fails naming the
    task and the gap.
    """
    violations: List[str] = []
    if not isinstance(tasks, list):
        return ["baseline tasks must be a list"]
    for task in tasks:
        if not isinstance(task, dict):
            continue
        task_id = task.get("id", "?")
        effort = task.get("effort")
        if not isinstance(effort, dict):
            violations.append(
                "task %r records no effort breakdown" % (task_id,))
            continue
        for dimension in EFFORT_DIMENSIONS:
            if effort.get(dimension) is None:
                violations.append(
                    "task %r effort missing %r" % (
                        task_id, dimension))
        if not task.get("effort_units") and not effort.get("units"):
            violations.append(
                "task %r effort states no units" % (task_id,))
    return violations


def check_reusable_format(corpus: Any) -> List[str]:
    """Return violations when the corpus cannot serve pilots.

    The format supports matched tasks, repeats, and held-out
    selection for the T16 pilot and T23 benchmark: the corpus
    carries matched groups, a repeat count, and a held-out set.
    A missing leg fails naming the leg, so no re-collection is
    ever needed.
    """
    violations: List[str] = []
    if not isinstance(corpus, dict):
        return ["baseline corpus must be a mapping"]
    for leg in ("matched", "repeats", "held_out"):
        if leg not in corpus:
            violations.append(
                "baseline corpus missing %r: matched + repeats + "
                "held-out serve the T16 pilot and T23 benchmark"
                % (leg,))
    return violations


def validate_baseline_corpus(corpus: Any) -> Tuple[List[str], List[Any]]:
    """Validate the frozen task-baseline fixture oracle.

    Returns (findings, entries). Every entry carries an id, a
    target surface (inventory, nochange, fragmentation, frozen,
    narrowpatch, effort, reusable), a record, and the expected
    violation fragment ("" means clean).
    """
    if not isinstance(corpus, dict):
        return (["baseline corpus must be a mapping"], [])
    if corpus.get("_frozen") is not True:
        return (["baseline corpus is not frozen: set "
                 "\"_frozen\": true"], [])
    entries = corpus.get("entries")
    if not isinstance(entries, list):
        return (["baseline corpus entries must be a list"], [])
    findings: List[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            findings.append("corpus entry is not a mapping: %r"
                            % (entry,))
            continue
        entry_id = entry.get("id", "?")
        target = entry.get("target")
        record = entry.get("record")
        expected = entry.get("expected_violation_fragment", "")
        if target == "inventory":
            violations = check_inventory(record)
        elif target == "nochange":
            violations = check_no_change(record)
        elif target == "fragmentation":
            violations = check_over_fragmentation(record)
        elif target == "frozen":
            violations = check_frozen_molds(record)
        elif target == "narrowpatch":
            violations = check_narrow_patch(record)
        elif target == "effort":
            violations = check_effort(record)
        elif target == "reusable":
            violations = check_reusable_format(record)
        else:
            findings.append(
                "entry %s has unknown target %r" % (entry_id, target))
            continue
        if expected:
            if not any(expected in v for v in violations):
                findings.append(
                    "entry %s: expected fragment %r not reproduced "
                    "(got %r)" % (entry_id, expected, violations))
        elif violations:
            findings.append(
                "entry %s: expected clean, got %r" % (entry_id,
                                                      violations))
    return (findings, entries)


def clean_task(kind: str, task_id: str) -> Dict[str, Any]:
    """One baseline task with full effort recorded (units stated)."""
    task: Dict[str, Any] = {
        "id": task_id,
        "kind": kind,
        "effort": {"controller": 1, "workers": 2, "reviews": 1,
                   "retries": 0, "rotations": 0},
        "effort_units": "hours",
    }
    if kind == "frozen":
        task["frozen_mold"] = "mold-v1"
    return task


def clean_corpus_tasks() -> List[Dict[str, Any]]:
    """One task per kind plus NO_CHANGE and over-fragmented tasks."""
    tasks = [clean_task(kind, "task-%s" % kind)
             for kind in TASK_KINDS]
    tasks.append({"id": "task-nochange", "kind": "local",
                  "verdict": "NO_CHANGE",
                  "effort": {"controller": 1, "workers": 0,
                             "reviews": 1, "retries": 0,
                             "rotations": 0},
                  "effort_units": "hours"})
    tasks.append({"id": "task-frag", "kind": "over-fragmented",
                  "harm": "slices too small to review independently",
                  "effort": {"controller": 1, "workers": 2,
                             "reviews": 1, "retries": 1,
                             "rotations": 0},
                  "effort_units": "hours"})
    return tasks
