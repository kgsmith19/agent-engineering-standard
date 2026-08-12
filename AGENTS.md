# Contributor and Agent Guidance

This repository is experimental and non-enforcing. Use these practices as concise working guidance, then follow the explicit instructions and verified commands of the repository being changed.

## Working approach

1. Start from a GitHub Issue with a clear outcome.
2. Make the smallest coherent change that satisfies that outcome.
3. Keep implementation, tests, and documentation consistent.
4. Run the relevant repository checks and record the results.
5. Open a pull request linked to the Issue.
6. Allow `PR Gate` to verify the configured checks.
7. When repository settings permit it, use native squash auto-merge after the gate passes.

Prefer direct, maintainable solutions. Avoid unrelated cleanup, speculative abstractions, and new process artifacts that do not help deliver the requested outcome.

## Evidence

Before handing off a change:

- inspect the final diff;
- check for whitespace errors;
- run the affected formatter, static checks, and tests;
- report commands and results accurately; and
- identify any check that could not be run.

## CI baseline

Workflow enforcement is a single required check named `PR Gate` (or a repository's own `ci.yml` acting as one). Once repository settings permit it, native squash auto-merge is enabled to fire automatically when `PR Gate` passes and there are no merge conflicts — no separate automation is needed to arm it.

## Forbidden artifacts

Do not commit, and remove on sight: `SPEC` files or directories, `PRD` documents, `System_Requirements.md`, data-flow diagrams, changelogs, ADRs, `AI_REVIEW` / "AI Review" workflows or references, `AGENT_VIEW`, `watchdog` automation, or any forced manual governance block (required human sign-off steps, review-request automation, merge-blocking bots beyond `PR Gate`). These were deliberately removed from this repository's own history; the guidance here is prospective as well as retrospective — repositories adopting this standard should not reintroduce them.

## Local scratchpad

An agent may draft a spec, design note, or outline locally to think through a GitHub Issue before writing it — but only in a `.gitignore`d workspace folder. Nothing drafted this way may be committed; the Issue itself is the durable artifact.

## AI agent boundaries

An AI coding agent may create work artifacts only when the task explicitly authorizes them. This can include Issues, branches, commits, pull requests, descriptions, code, tests, and documentation.

An AI agent must not submit reviews, request reviewers, approve changes, block a pipeline, or post an unsolicited comment. It may answer a direct question when explicitly tagged in an Issue or pull request.

## Repository references

A repository may deliberately reference a specific version of this guidance. The reference is informational and does not automatically change that repository. Repository-specific instructions take precedence.
