# Templates

Canonical distribution files for repositories adopting the Agent Engineering Standard. Files here are the single source of truth; GitHub reads templates only from its own fixed paths, so active copies are installed under `.github/` and must stay byte-identical to their canonical sources — the PR Gate compares each pair.

## Canonical and active pairs in this repository

| Canonical | Active copy |
| --- | --- |
| [`ISSUE.md`](./ISSUE.md) | `.github/ISSUE_TEMPLATE/work-item.md` |
| [`ISSUE_CONFIG.yml`](./ISSUE_CONFIG.yml) | `.github/ISSUE_TEMPLATE/config.yml` |
| [`PULL_REQUEST.md`](./PULL_REQUEST.md) | `.github/PULL_REQUEST_TEMPLATE.md` |

## Distribution files for consuming repositories

| File | Destination in a consuming repository |
| --- | --- |
| [`project.yaml`](./project.yaml) | `project.yaml` (rendered, then filled with actual commands) |

The distribution manifest (`manifest.yaml`), consuming-repository lock template (`standard.lock`), desired-state settings and ruleset templates, workflow templates, and the ignore fragment arrive with the standard tooling; `tools/standardctl.py init` and `update` render them into consuming repositories from one exact standard commit. Adoption is explicit, Issue-backed, and owner-controlled; a consuming repository's `standard.lock` records provenance informationally and creates no runtime dependency.
