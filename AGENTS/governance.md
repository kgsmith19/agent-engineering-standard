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

## Owner Stand-in

The **Owner Stand-in** is an agent acting as the owner's delegate. It makes the decisions and clears the blockers that the owner has delegated to it, and nothing else. Its authority ranks below an explicit current owner instruction and the owner-authorized Issue, and above harness and provider defaults. The owner **may revoke or narrow the stand-in at any time with one instruction**, which takes effect immediately. Only the owner may change the guardrails below.

The stand-in always identifies itself as an agent acting for the owner. It never presents itself as the owner.

Blockers on delegated work follow seven steps:

1. State the blocker and the owner's intent on the Issue before acting.
2. Generate at least three materially different solutions, one of which may be to wait.
3. Research each solution in web sources, vendor documentation and open-source prior art.
4. Rank the solutions by value, quality, reversibility, security, cost and automation potential.
5. Choose one and record a decision record on the Issue: the options, their scores, the choice and why.
6. Execute, preferring automation in this order: API, then CLI, then a scripted browser job, then manual steps. Turn any manual web setup into a re-runnable, idempotent job with waits, retries and error handling.
7. Verify the result against the acceptance criteria and record a receipt on the Issue.

These guardrails are fixed. No stand-in decision may override them:

- Never impersonate the owner to a third party. Never bypass a security control, a permission denial or a safety classifier; put the exact command to the owner for approval instead.
- Never print, move or commit secret values. Refer to them by vault reference only.
- Never enter payment details or spend money without an explicit owner budget.
- Before any irreversible or destructive production action, take a backup or define a rollback, and record a receipt.
- Legal, contractual or identity-binding acceptance goes to the owner.
- Every decision is logged on the Issue; the decision record is the log.

The pilot lessons are rules for every stand-in action:

- Finalize commit trailers and messages before enabling auto-merge.
- Post-merge criteria go on the parent Issue, never as pre-merge checkboxes.
- Evidence the reviewer must see goes in a PR comment.

The ladder applies only to delegated decisions, in this order:

- **Level 1, decide alone.** The stand-in decides when the choice lies inside the delegation and touches no guardrail.
- **Level 2, log and notify.** The decision is logged on the Issue and the owner is notified once.
- **Level 3, ask.** The owner is asked only when a guardrail blocks the action or the action needs the owner's own identity or credentials. Each ask states the exact one-click or one-command action.

An ambiguous owner signal is not a delegated decision. It still escalates under the human-exception rules in [`tools/human_exception.py`](../tools/human_exception.py).

## Sources of Truth

| Information | Source of truth |
| --- | --- |
| Product purpose and quick start | `README.md` |
| Agent and engineering rules | `AGENTS.md` |
| Claude / Gemini compatibility | `GEMINI.md` (thin `@AGENTS.md` adapter; no root `CLAUDE.md` — Claude Code reads `AGENTS.md` natively) |
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

## Role and Authority Contract

This contract defines **what MUST be proven** before an agent action is authorized. It does not define how an agent is hosted, which runtime runs it, or which personas exist. The machine reference is `tools/role_contract.py` (`decide`), pinned by the frozen fixtures in `Canonical/corpus/role-contract/`.

**Grant.** An agent action that changes the repository or GitHub MUST be covered by a grant with these fields, all required except `github_identity`:

- `actor_id`, `run_id`, `grantor`: non-empty strings.
- `duty`: a role from `tools/role_authority.py` `ROLES` (for example `builder`, `verifier`, `reviewer`, `remediator`, `spec_author`, `spec_critic`). Duties are SDLC functions, never persona names.
- `scope`: a non-empty list of path prefixes.
- `head_sha`: the 40-character lowercase commit the grant is valid for.
- `provider`: `{family, model}`. `provenance`: `{source, provider_observed}`.
- `issued_at`, `expires_at`: ISO-8601 UTC with `Z`. The window MUST NOT exceed 3600 seconds.
- `github_identity`: REQUIRED only for actions that post to or mutate GitHub.

**Decision.** An action is allowed only when no rule refuses it. Refusals carry rule ids:

| Rule | Refuses when |
| --- | --- |
| `grant-invalid` / `action-invalid` | a field is missing, extra, or mistyped, or the action kind is unknown. An unknown risk is treated as R3. |
| `grant-expired` | `now` is outside `[issued_at, expires_at)`. |
| `stale-head` | `head_sha` is not the current head. |
| `self-grant` | the grantor is the actor, unless the grantor is the owner. |
| `unverified-provenance` | `provider_observed` is empty or not the declared provider family. |
| `out-of-scope` | the path is outside the grant scope or the duty's write roots, or it escapes its root. |
| `forbidden-self-review` | a review or verify action is taken by the builder of the same head, by the same actor that built it, or (at R2/R3) by the same provider family that built it. |
| `unauthorized-github-write` | a `post` or `mutate_github` action has no `github_identity`. |
| `owner-override` | an override is supplied that is not an explicit owner decision: another owner, an empty decision or scope, or a different owner than the one decided for. |

**Rules.**

- Authorization MUST fail closed. Any missing or invalid field refuses; no default is inferred.
- Reviewer and verifier independence MUST hold: a builder MUST NOT validate its own head, and at R2/R3 the reviewer's provider family MUST differ from the builder's. Advisory R0/R1 review remains advisory.
- GitHub identity MUST NOT be required for local evidence writes, and MUST be present for every post or mutation of GitHub.
- An owner override MUST be explicit: owner `kgsmith19`, a non-empty decision, and a non-empty scope. It MAY waive only `grant-expired` and `stale-head`. It MUST NOT waive `self-grant`, `forbidden-self-review`, `unverified-provenance`, or any other rule.
- This contract MUST NOT loosen the PR Gate, independent LLM review, or owner authority defined elsewhere in this standard. A grant is evidence that the PR Gate checks; it never replaces the gate or any review.

**Examples.**

1. **Interactive subagent.** The orchestrator issues a `builder` grant scoped to `src/` for one head and a 30-minute window. The subagent writes locally with no `github_identity`. A later `verifier` grant of another provider family, at R2/R3, records its verdict under `evidence/verification/`. A `verify` by the same actor is refused as `forbidden-self-review`.
2. **Isolated container worker (for example OpenHands).** The same grant fields are issued at container start and recorded in the run receipt. The container holds no GitHub credential, so it can only write local evidence. Any post goes through a GitHub App identity outside the container, and the post is refused without that identity.
3. **Existing GitHub App path.** The reviewer GitHub App is the `github_identity` for its post to a PR. The grant's provider family MUST differ from the builder's at R2/R3, which is the existing Provider Separation rule. Nothing in this path changes.

**Compatibility with external agent systems.** The contract names fields and rule ids, not runtimes, hosts, or personas, so an external agent system can emit grants that satisfy it. `hyper-agents` is an example consumer: it keeps its own personas, runtime, and role definitions, and it may emit grants in these fields to be checked here. This repository has no dependency on `hyper-agents` or any other agent system, and no external system defines this standard's duties or rules.

## Collaboration Policy

This policy separates the guarantees every SDLC run must keep from the mechanisms that may change. It builds on the grant contract above; `tools/role_contract.py` (`record`) and its fixtures pin it.

**Mandatory guarantees (binding):**

- **Scope:** every write is covered by a grant whose path prefixes name what it may touch.
- **One writer per mutable worktree:** overlapping builder or remediator scopes on the same head never run in parallel.
- **Independent review and verification:** a builder never validates its own head, and R2/R3 review or verification comes from a different provider family.
- **No privilege escalation:** a delegated grant needs the owner or a grantor who holds the same duty.
- **Exact-head evidence:** acceptance evidence names the tested head and is recorded on the Issue or PR.
- **PR Gate as the sole release path:** nothing reaches `main` except through the PR Gate.

**Replaceable mechanisms (not mandated):**

- The agent harness, hosting, scheduler, and mint or discharge service.
- Prompts and agent configuration.
- Any product. A runtime such as OpenHands or TAKT may serve as an example, never as a requirement.

**Collaboration receipt.** `record` returns one receipt per action: `schema_version`, `task`, `duty`, `specialty`, `actor_id`, `run_id`, `grantor`, `provider`, `provenance`, `scope`, `exact_sha`, input and output artifacts as `{path, sha256}`, `acceptance_ids`, `claims`, `decision` (`allow` or `refuse`), `rules`, and `decided_at`. A specialist such as security or DBA is a reviewer or verifier that sets `specialty` on its receipt; it is never a grant key. R2/R3 work that touches auth, secrets, or migration paths suggests a specialist; nothing enforces that choice.

**Human approval** follows the existing risk and authority rules. It is required where those rules require it, not for every handoff.

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
