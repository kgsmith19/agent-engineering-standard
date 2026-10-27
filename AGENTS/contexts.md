# Contexts

Agentic Domain-Driven Development (ADDD) combines bounded contexts from Domain-Driven Design with Clean Architecture and Clean Code. An agent works inside one context folder and relies on that folder's local files instead of a whole-repository context window. Contexts get finer as the code grows.

## Bounded Contexts

**Definition.** A bounded context is a folder that contains `context.yaml`, `AGENTS.md`, and `README.md`. A repository with no `context.yaml` is unaffected (opt-in). The check `bounded-contexts` (`standardctl verify --select policy`) enforces this rule.

**Manifest (`context.yaml`).** Schema: `TEMPLATES/context/context.schema.json` (JSON Schema 2020-12, closed).
- Required: `name` (kebab-case), `purpose` (one sentence, 200 characters or fewer), `public` (relative paths inside the folder), `depends_on` (context names), `commands` (`test`, `lint`, `build` strings).
- Optional: `invariants`, `owners`, `children` (relative paths of nested contexts).
- Unknown keys fail. Names are unique across the repository.

**`AGENTS.md` (context rules).** Holds only context-local rules: purpose, invariants, public interface, scoped commands, and do-not-touch paths. It links up to root rules (`AGENTS.md`, `AGENTS/*.md`) and never copies them. Budget: 120 lines by default. A project may override it with `contexts: {agents_md_max_lines: N}` in `project.yaml`.

**`README.md` (human and domain view).** Ubiquitous-language glossary, responsibilities, interfaces, and how to run. It is written for a person learning the domain.

**Layering.** Inside a context, Clean Architecture applies: domain (pure rules, no I/O) -> application (use cases) -> interface/infrastructure (CLI, storage, network). Dependencies point inward only.

**Cross-context access.** A context uses another context only through that context's declared `public` paths, and only along a declared `depends_on` edge. The dependency graph must be acyclic. Reaching into another context's other files is a boundary violation.

**Nesting and splitting.** Finer contexts are declared, never implicit. A context folder nested inside another must be listed in the parent's `children`, and every listed child must be a context folder. A context that exceeds its AGENTS.md budget, or whose work spans unrelated concerns, gets a split Issue: the orchestrator architects finer child contexts. Adding rules to an over-budget AGENTS.md is not an allowed fix.

**Edit scope and related primitives.** A context's edit scope is its folder. An implementer working in a context writes nothing outside it. `ownership_map.py` declares root-level read, edit, and impact scopes; a context's folder should be the edit scope it declares. `repo_map.py` entries should cite a context's `AGENTS.md` and `README.md` as the local source instead of repeating root rules. The task capsule should name the active context so a resumed session restarts in the same folder.

**Enforcement.** `check_bounded_contexts` reports: missing `AGENTS.md` or `README.md`; AGENTS.md over budget; a manifest that violates the contract; duplicate names; `depends_on` naming an unknown context; dependency cycles; `public` paths that do not exist inside the folder; and undeclared or unresolvable nesting.

Templates: `TEMPLATES/context/` (`AGENTS.md`, `README.md`, `context.yaml`, `context.schema.json`).
