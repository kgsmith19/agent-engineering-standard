# AES vNext Conformance Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a tidy AES template topology and a deterministic conformance check that consuming repositories can run locally.

**Architecture:** Canonical source names become descriptive and consistently cased inside `TEMPLATES/`; GitHub's fixed destination paths remain unchanged through the distribution manifest. `standardctl` gains a small, network-free conformance check that proves the adopted files, root metadata, and final-gate contract agree, while product tests remain repository-owned.

**Tech Stack:** Python 3.9+ standard library, restricted YAML manifest parser, GitHub Actions YAML templates, Python unittest.

**Spec:** `docs/superpowers/specs/2026-10-30-aes-vnext-conformance-design.md`

## Global Constraints

- Preserve explicit, pinned, owner-controlled adoption; never add an AES runtime dependency.
- Keep one final fail-closed PR gate and exact-head verification.
- Do not automatically modify consuming repositories.
- Retain GitHub fixed destination paths; only canonical AES source names change.
- Use thin, independently mergeable commits and do not remove a workflow without a separate dependency audit.

## Review Focus

- Existing consumers must update from an older manifest without a missing source path.
- A root gate that is present but not final/aggregating must fail conformance.
- Adapt-mode repository instructions must remain repository-owned and never be overwritten.
- A stale `standard.lock` must be reported as provenance, not silently rewritten.
- A repository with product-specific CI must pass only when its declared final gate covers that CI.

---

### Task 1: Normalize canonical template names

**Files:**
- Rename: `TEMPLATES/ISSUE.md` → `TEMPLATES/issue-template.md`
- Rename: `TEMPLATES/ISSUE_CONFIG.yml` → `TEMPLATES/issue-config.yml`
- Rename: `TEMPLATES/PULL_REQUEST.md` → `TEMPLATES/pull-request-template.md`
- Modify: `TEMPLATES/manifest.yaml`
- Modify: `TEMPLATES/README.md`
- Test: `tests/test_standardctl.py` (or the existing manifest/update test module)

**Interfaces:**
- Consumes: manifest `mappings[].source` paths.
- Produces: the same three GitHub destination files from consistently named canonical sources.

- [ ] Write failing manifest/update tests that assert the three new source names produce `.github/ISSUE_TEMPLATE/work-item.md`, `.github/ISSUE_TEMPLATE/config.yml`, and `.github/PULL_REQUEST_TEMPLATE.md`.
- [ ] Run the targeted tests and confirm they fail because the new canonical sources do not exist.
- [ ] Rename the three files; update only the corresponding manifest source paths and documentation links.
- [ ] Run `python -m unittest discover -s tests -p "test_*.py"` and `python tools/standardctl.py verify`; both must pass.
- [ ] Commit: `refactor(templates): normalize canonical template names`.

### Task 2: Declare the conformance contract in the manifest

**Files:**
- Modify: `TEMPLATES/manifest.yaml`
- Create: `TEMPLATES/conformance-contract.md`
- Modify: `TEMPLATES/README.md`
- Test: existing manifest parser tests

**Interfaces:**
- Consumes: manifest mappings and `project.yaml` fields `ci.workflow` and `ci.required_check`.
- Produces: a compact contract describing required root metadata, copied artifacts, and the final gate.

- [ ] Write failing parser/validation tests for a `conformance:` manifest block requiring `AGENTS.md`, `project.yaml`, `standard.lock`, the named final gate workflow, and the named check.
- [ ] Run the targeted tests and confirm the manifest rejects a missing required key and accepts a complete contract.
- [ ] Add the minimal `conformance:` block and a concise explanatory document; do not duplicate the full governance policy.
- [ ] Run the manifest tests, `python tools/standardctl.py verify`, and the full unit suite.
- [ ] Commit: `feat(standardctl): declare repository conformance contract`.

### Task 3: Add a deterministic local conformance check

**Files:**
- Modify: `tools/standardctl.py`
- Modify: `tests/test_standardctl.py` (or the existing command test module)
- Modify: `README.md`

**Interfaces:**
- Produces: `standardctl conformance --target DIR [--json]`.
- Exit result: `0` only when every required contract item is satisfied; `1` for any finding.
- JSON result: `{"ok": bool, "findings": [{"id": str, "message": str}]}`.

- [ ] Write failing tests for: a conforming fixture; a missing `standard.lock`; a missing final-gate workflow; and a workflow that lacks the configured required-check name.
- [ ] Run the targeted tests and confirm the command is absent/fails.
- [ ] Implement the command with standard-library file reads and the existing line/indentation workflow extraction helper; emit stable finding ids `conformance-metadata`, `conformance-lock`, `conformance-gate-workflow`, and `conformance-required-check`.
- [ ] Run targeted tests, then `python -m unittest discover -s tests -p "test_*.py"` and `python tools/standardctl.py verify`.
- [ ] Commit: `feat(standardctl): verify repository conformance contract`.

### Task 4: Make the release and rollout boundaries explicit

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-10-30-aes-vnext-conformance-design.md`
- Modify: `docs/superpowers/plans/2026-10-30-aes-vnext-conformance-foundation.md`

**Interfaces:**
- Consumes: the completed `standardctl conformance` command.
- Produces: a documented rollout order: AES → Core root → Core apps → Extensions → Hyper-Agents → Deep Search import.

- [ ] Add the exact local command and the explicitly manual, repository-by-repository rollout rule to the README.
- [ ] Run the documented commands against AES itself; record only actual outcomes in the PR evidence.
- [ ] Run `git diff --check`, the full unit suite, and `python tools/standardctl.py verify`.
- [ ] Commit: `docs: describe AES conformance rollout`.
