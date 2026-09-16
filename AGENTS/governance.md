# Governance

## Owner Authority

The **OWNER** is `kgsmith19`, or an explicit instruction authenticated as coming from the owner.
The standard governs agents by default. **The owner governs the standard.**

**Precedence order:** (1) current explicit owner instruction, (2) owner-authorized GitHub Issue
and its acceptance criteria, (3) this `AGENTS.md`, (4) `project.yaml`, (5) pinned shared standard
from `standard.lock` (consuming repositories), (6) harness and provider defaults.

The owner **may override, replace, suspend, or delete any part of this standard at any time**,
without satisfying the old version of the policy — existing policy cannot veto its authorized
replacement, and an agent must evaluate a change against the requested target state, not
superseded rules. An agent **must not** lecture, argue with, reverse, or repeatedly warn about an
explicit owner decision, or create an unsolicited Issue to restore an owner-removed policy.
Technical risks may be stated once, concretely and without obstruction. The owner retains
administrative bypass authority.

> [!IMPORTANT]
> An agent **must not** silently disregard an owner override. When a check is waived, report it
> once as: **"Not run by owner instruction."** And for merges: for every merge not using explicit
> owner bypass, the application-specific PR Gate is the **ultimate machine gate** — no agent
> review, comment, label, artifact upload, or orchestration workflow may bypass it.

Routine agents use a dedicated non-administrative identity with minimum capabilities (contents,
issues, and pull-requests write; actions and metadata read) — no administration, ruleset, secret,
or bypass permissions. Owner administrative credentials stay separate, are never stored in
repository files or workflow secrets, and are used only for explicit owner-authorized
administration or bypass. When agent work runs under the owner account, self-approval does not
protect the control plane — control-plane changes then require an explicit owner administrative
merge decision.

## Sources of Truth

| Information | Source of truth |
| --- | --- |
| Product purpose and quick start | `README.md` |
| Agent and engineering rules | `AGENTS.md` |
| Claude / Gemini compatibility | `CLAUDE.md` / `GEMINI.md` (import-only) |
| Repository facts and exact commands | `project.yaml` |
| Release scope | GitHub Milestone |
| Work intent and acceptance criteria | GitHub Issue |
| Implementation evidence and handoff | Pull request |
| Execution history | GitHub Actions |
| Product behavior | Code and tests |
| Adopted standard revision | `standard.lock` (consuming repositories only) |
| Distribution map | `TEMPLATES/manifest.yaml` |
| Temporary task recovery | Gitignored runtime workspace |
| E2E and verification evidence | Actions artifact plus Evidence Index |
| Long-lived release evidence | GitHub Release assets |

## Session Bootstrap

At the start of every new, resumed, or post-compaction controller session:

1. Invoke `superpowers:using-superpowers` when the harness provides Superpowers.
2. Read `AGENTS.md`, then `project.yaml`.
3. Initialize the dev agent and reviewer agent (see [Agent identities](#agent-identities)).
4. Identify the active GitHub Issue, milestone, branch, PR, and exact head.
5. Detect whether the environment is already isolated.
6. Reconcile the local recovery ledger with Git history and remote state.
7. Run the documented clean-baseline verification before modifying code.

## Agent Identities

Two GitHub App identities back this repository. Both MUST be initialized at session start.

| Agent | GitHub App | App ID | Installation | Role |
| --- | --- | --- | --- | --- |
| **Dev** | `hyperbolic-core-dev` | 4656454 | 155589222 | Builder — implements Issues, opens PRs |
| **Reviewer** | `hyperbolic-core-reviewer` | 4656330 | 155589128 | Independent LLM Review — posts findings to PRs |

Both apps are installed on `kgsmith19` with `issues: write`, `contents: write`, `pull_requests: write`, `metadata: read`.

### Credentials

Credentials live in Infisical at `https://app.infisical.com`, project `hyperbolic-core`, environment `production`. The harness resolves them; nothing is hardcoded in repository files.

| Agent | App ID secret | Private key secret |
| --- | --- | --- |
| Dev | `/dev/DEV_GITHUB_APP_ID` | `/dev/DEV_GITHUB_APP_PRIVATE_KEY` |
| Reviewer | `/review/REVIEW_GITHUB_APP_ID` | `/review/REVIEW_GITHUB_APP_PRIVATE_KEY` |

### Authentication Flow

1. Read the app ID and private key from Infisical.
2. Generate a JWT signed with RS256: `iss` = app ID, `iat` = now − 60s, `exp` = now + 600s.
3. `POST /app/installations/<installation_id>/access_tokens` with the JWT.
4. Use the resulting installation token for all GitHub API requests.

### Provider Separation

The reviewer agent MUST use a different provider family than the dev agent (e.g., dev on `anthropic` → reviewer on `openai` or `gemini`). The harness configures both; the repository never hardcodes a provider or model.

### CI Integration

The Independent LLM Review CI job (see `.github/workflows/llm-review.yml`) uses the reviewer GitHub App to post review comments on PRs. Its provider family, model, and credential are supplied by the harness at dispatch time (for example from the same Infisical paths above) — the repository carries NO statically-configured reviewer variables or secrets for this job, and the gate never fails for their absence. **Owner directive (supersedes any older text in this repo or its templates): the harness owns reviewer configuration; no rule may require the repository to hold reviewer provider/model/credential values.**

### Agent Communication Workflows

All automated comments post via agent identities, never the repository token:

**Work State comments** (merge-policy → post-work-state.yml):
- Merge-policy reconciles PR state and builds Work State body
- Dispatches `post-work-state.yml` with pr_number, issue_number, body
- Dev-agent posts to both PR and linked Issue as `@hyperbolic-core-dev [bot]`
- Includes metadata: `<!-- agent-metadata:dev-agent:EVENT:RUN_URL -->`

**LLM Review failures** (pr-gate → dev-agent-post-v2.yml):
- PR Gate llm_review job builds failure comment
- Dispatches `dev-agent-post-v2.yml` with action=post_comment
- Dev-agent posts failure details as `@hyperbolic-core-dev [bot]`
- Includes same metadata marker for tracking

**Body transmission safety:**
- Complex markdown (backticks, multiline) passed via stdin with heredoc: `-f body@- << 'EOF'`
- JavaScript uses `JSON.parse('${{ toJSON(...) }}')` to safely deserialize
- Prevents shell interpretation of special characters

**Collaboration framework** (see `.kilo/AGENT-COLLABORATION.md`):
- Structured comment templates in `.github/COLLABORATION_TEMPLATE.md`
- Reviewer-trigger.yml monitors PR commits and iteration counter
- Auto-escalates to owner after 10 discussion rounds
- Machine-readable markers: `<!-- agent-collaboration:review-round:N -->`

## Provider-Neutral Roles

| Role | Responsibility |
| --- | --- |
| **Owner** | Controls intent and may override anything. |
| **Controller** | Coordinates the Issue, worktree, tasks, subagents, evidence, and recovery state. |
| **Builder** | Implements one bounded task or slice. |
| **Test Designer** | Challenges acceptance criteria and designs defect-sensitive evidence. |
| **Verifier** | Independently challenges intent interpretation, tests, implementation, security, structure, and exact-head evidence. |
| **Investigator** | Researches, reproduces, traces, or measures without implementation authority. |

Supported provider families: `anthropic`, `openai`, `gemini`. Any family may perform any role.
For R2/R3 work: prefer a different provider family for verifier versus builder, require
exact-head verification, and record the provider family and model. The owner may waive provider
separation.

## Releases and Milestones

A GitHub Milestone defines a release (for example `v1.4.0`, `vNext`). Use an existing open
release milestone when one is clearly applicable; otherwise create `vNext`. **Do not invent a
semantic version without owner intent.**

Every release-bound Issue belongs to its release milestone. Release state reads directly from the
milestone: open Issue = not completed; `status:ready` = available; `status:active` = claimed;
linked PR = implementation or verification in progress; `status:blocked` = blocked; closed by
merged PR = completed; closed as not planned or duplicate = excluded, not delivered.

Every release milestone contains exactly one Issue titled `VERIFY: <milestone-name> release`. It
verifies: every required implementation Issue closed by merged work; final `main` passing its PR
Gate; release-level commands passing at the exact final SHA; critical E2E behavior; required
artifacts; independent verification of R2/R3 behavior; migration and rollback validation where
applicable; no known release-blocking defect; and published durable release evidence.

> [!IMPORTANT]
> A release is ready only when all required Issues, the verification Issue, and final `main`
> verification are complete — **never merely because the milestone displays 100%.**

## Risk Classification

Every Issue carries exactly one tier:

| Tier | Meaning |
| --- | --- |
| **R0** | Mechanical |
| **R1** | Local and reversible |
| **R2** | Shared, integrated, or stateful |
| **R3** | Critical, privileged, destructive, financial, security-sensitive, concurrent, or irreversible |

Verification scales with tier. **R0:** document syntax, references, formatting, structural
validation. **R1:** adds formatter, lint and static analysis, build and type checks, focused
tests, and the affected suite. **R2:** adds integration, contract, persistence, failure and
boundary behavior, property and differential tests, and independent exact-head verification.
**R3:** adds a different-provider verifier, targeted mutation testing, fuzzing, security
analysis, state-machine and concurrency exploration, fault injection, migration dry-run, rollback
verification, canary or shadow execution, and runtime invariants, as applicable. The owner may
override any tier or mechanism.
