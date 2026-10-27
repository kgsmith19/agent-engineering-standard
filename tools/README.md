# tools

Standard tooling for this repository. `standardctl.py` verifies the standard through its check groups (`policy`, `lean`, `security`). `work_queue.py` keeps the owner's execution queue and answers which item to resume.

## Ubiquitous Language

| Term | Meaning in this context |
|---|---|
| Check | A registered policy function in `CHECKS` that returns findings. |
| Finding | One rule violation: check id, severity, path, and message. |
| Queue item | One entry in the owner's execution queue, normally one Issue. |
| Bounded context | A folder with `context.yaml`, `AGENTS.md`, and `README.md` (see `../AGENTS/contexts.md`). |

## Responsibilities

- Verification: `standardctl.py` runs checks and reports findings.
- Queue: `work_queue.py` reports the next item and guards claims; owner writes are logged.
- Shared primitives: manifest parsing, the repository model, ownership and repo maps.

## Interfaces

Public entrypoints (see `context.yaml`): `standardctl.py`, `work_queue.py`.

## How To Run

1. Verify: `python3 tools/standardctl.py verify`
2. Tests: `python3 -m unittest discover -s tests -p "test_*.py"`
