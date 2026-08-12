# Agent Engineering Standard

This repository contains experimental engineering guidance for repositories that use coding agents. It is a learning resource, not an enforcement mechanism. Its contents will evolve as the practices are tested and refined.

## Purpose

The guidance favors lean changes, clear intent, maintainable code, focused tests, and evidence that a pull request is ready to merge. Each repository remains responsible for choosing and configuring the practices that fit its product and technology.

## Suggested lifecycle

1. Record the desired outcome in a GitHub Issue.
2. Implement the smallest coherent change that satisfies the Issue.
3. Run the repository's relevant formatters, static checks, and tests.
4. Open a pull request that links the Issue and records the verification performed.
5. Let the repository's `PR Gate` run automatically.
6. After repository settings are configured, use native squash auto-merge when `PR Gate` passes.

A pull request should make the change, its rationale, and its verification easy to understand.

## Engineering guidance

- Keep each change narrow enough to inspect and recover safely.
- Prefer simple code and explicit behavior over speculative abstractions.
- Add or update tests when behavior changes.
- Run the checks that are relevant to the affected code.
- Preserve unrelated work and document any known limitation.
- Treat a passing gate as evidence that configured checks ran, not as a substitute for engineering judgment.

## Templates

`TEMPLATES/` holds reference material — root docs, a pull request template, an issue template, a test ledger, and a `project.yaml` metadata schema — for a repository to copy and adapt. See `TEMPLATES/README.md`. Copying these files does not create an ongoing dependency; a repository's own `standard.lock` records, informationally, which version of this standard it was drawn from.

## Use by other repositories

Other repositories may reference a specific version of this repository. Adoption is deliberate and repository-specific; no content here updates another repository automatically. A reference communicates which guidance was considered, but does not impose behavior or replace the repository's own instructions.

## AI agent participation

When explicitly tasked, an AI coding agent may create or update Issues, branches, commits, pull requests, descriptions, code, tests, and documentation within the authorized scope.

AI agents may not submit reviews, request reviewers, approve changes, block pipelines, or post unsolicited comments. An AI agent may answer a direct question when it is explicitly tagged in an Issue or pull request.

## Useful local commands

Use the commands defined by the repository being changed. Common evidence includes:

```bash
git status --short
git diff --check
git diff --stat
# Run the repository's documented formatter, type checker, and test commands.
```
