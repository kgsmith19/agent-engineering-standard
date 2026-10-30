# AES vNext Conformance Program

## Intent

Make the Agent Engineering Standard easier to adopt and verify while preserving its
fail-closed gate, explicit owner authority, and repository-specific adaptations.

## Owner-approved architecture

- `agent-engineering-standard` is the independent canonical standard.
- `hyperbolic-core` is the application monorepo. Existing and future applications,
  including the demo app and Deep Search, live under `apps/<name>/`.
- `hyper-agents` is the separate local agent-runtime monorepo.
- `agent-extensions` is the separate cross-harness bootstrap and capability layer.
- There is no second application monorepo and Hyper-Agents is not moved into Core.

## Goals

1. Give AES one tidy, consistently named template surface and one documented
   distribution manifest.
2. Make a consuming repository's compliance independently checkable without a
   runtime dependency on AES.
3. Make the required CI contract consistent: one final fail-closed gate, exact-head
   verification, and no hidden duplicate workflow authority.
4. Adopt the resulting standard one repository at a time, preserving each product's
   local commands, tests, and bounded-context instructions.

## Non-goals

- No fleet-wide automatic rewrite or forced update.
- No removal of repository-specific `AGENTS.md` instructions.
- No bulk import of Deep Search or the demo app before their standalone conformance
  slice passes.
- No CI bypass, weakened check, or required runtime connection to AES.
- No re-architecture of product code as part of standards adoption.

## Approaches considered

1. **One giant Hyperbolic Core monorepo.** Rejected: it couples agent-runtime
   security and machine bootstrap concerns to application delivery.
2. **A second application monorepo.** Rejected: it adds another boundary without
   reducing ownership or CI complexity.
3. **Independent standard plus two focused monorepos.** Chosen: Core owns apps,
   Hyper-Agents owns runtime, Extensions owns machine capabilities, and AES owns
   reusable governance and verification.

## Conformance contract

A repository is conformant when:

- `standard.lock` names the adopted AES revision;
- root `AGENTS.md` and `project.yaml` accurately state repo-specific rules
  and commands;
- generated/copy-mode standard artifacts match their canonical source;
- one final required PR gate aggregates every applicable check and verifies the
  exact PR head;
- `standardctl verify` passes locally; and
- repository-specific tests remain authoritative for product behavior.

An application inside Core additionally keeps a scoped `AGENTS.md`, an explicit
test/build command, and a declared owner boundary. It does not need a second,
independent GitHub workflow tree.

## Delivery order

1. AES vNext: clean template/workflow topology and deterministic conformance
   verification.
2. Hyperbolic Core root: update pin, gate contract, and monorepo conformance map.
3. Core applications/services: one thin adoption slice per application or coherent
   group, including the demo app.
4. Agent Extensions and Hyper-Agents: separate adoption slices.
5. Deep Search: conform standalone first, then import as `apps/deep-search` with
   its history and local tests preserved.

## Evidence standard

Every slice has one Issue, branch, ready PR, exact-head local verification, and
a green final PR gate. A repository is never called conformant merely because
files were copied; its own validator and CI evidence must pass.
