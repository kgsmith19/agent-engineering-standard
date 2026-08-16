# Agent Engineering Standard

An operational engineering standard for repositories where AI coding agents do real work under absolute human authority.

## 🎯 Purpose

The standard turns agent work into small, verified, independently mergeable changes with honest evidence. GitHub is the machinery of record: Milestones define releases, thin Issues define work, pull requests carry evidence, and a single fail-closed PR Gate is the only machine authority over merges. The owner may override anything at any time; agents may not use superseded policy to resist an authorized change.

## 🧭 Lifecycle

1. A release Milestone scopes the work; a thin Issue states one observable outcome, its behavior claims, and its risk tier (R0–R3).
2. An agent claims the Issue by atomically creating its `issue/<n>-<slug>` branch, then implements in an isolated worktree.
3. Verification scales with risk: tests with failure-sensitivity proofs, disclosed oracle changes, and independent exact-head verification for R2/R3.
4. A ready (never draft) pull request carries the evidence; the `Agent Engineering Standard PR Gate` must conclude success on the exact head.
5. Native squash auto-merge executes the merge; the Merge Policy workflow keeps PR state honest without ever running PR code.
6. A `VERIFY:` Issue proves each release before it is called done.

The full rules live in [`AGENTS.md`](./AGENTS.md) — the single source of agent and engineering policy. `CLAUDE.md` and `GEMINI.md` are import-only pointers to it; repository facts and exact commands live in [`project.yaml`](./project.yaml).

## 📚 Adoption by other repositories

Canonical distribution files live in [`TEMPLATES/`](./TEMPLATES/). `tools/standardctl.py` renders them into a consuming repository from one exact standard commit (`init`), updates an existing adopter (`update`), and validates invariants (`verify`); a consuming repository's `standard.lock` records provenance informationally. Adoption and every update are explicit, Issue-backed, and owner-controlled — nothing propagates automatically, and this repository being unavailable never breaks an adopter.

## 🔒 AI agent participation

Agents may, when a task authorizes it: create Issues, branches, commits, pull requests, code, tests, and documentation. Agents must not: submit reviews, request reviewers, approve changes, block pipelines, post unsolicited comments, bypass a failing gate, or weaken an oracle to get green. An agent may answer a direct question when explicitly tagged.

## ⚙️ Useful local commands

```bash
python tools/standardctl.py verify
python -m unittest discover -s tests -p "test_*.py"
python tools/standardctl.py worktrees reconcile
git status --short && git diff --check
```

<!-- canary #87: harmless draft-promotion test content -->

<!-- canary #89: harmless auto-merge re-arm test content -->
