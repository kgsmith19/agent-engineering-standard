# Templates

Canonical distribution files for repositories adopting the Agent Engineering Standard.
**Files here are the single source of truth.** GitHub reads templates only from its own fixed
paths, so active copies are installed under `.github/` and must stay byte-identical to their
canonical sources — the PR Gate compares each pair.

## Canonical and active pairs, in this repository

| Canonical | Active copy | Byte-identical? |
| --- | --- | --- |
| [`ISSUE.md`](./ISSUE.md) | `.github/ISSUE_TEMPLATE/work-item.md` | ✅ enforced by the PR Gate |
| [`ISSUE_CONFIG.yml`](./ISSUE_CONFIG.yml) | `.github/ISSUE_TEMPLATE/config.yml` | ✅ enforced by the PR Gate |
| [`PULL_REQUEST.md`](./PULL_REQUEST.md) | `.github/PULL_REQUEST_TEMPLATE.md` | ✅ enforced by the PR Gate |

## Starting points for consuming repositories

Installed by `tools/standardctl.py init` from one exact standard commit, then owned and edited by
the adopting repository — **not** byte-identity-enforced downstream the way the pairs above are.

| Source | Destination | Mode | What it is |
| --- | --- | --- | --- |
| [`../AGENTS.md`](../AGENTS.md) (this repository's own root file) | `AGENTS.md` | `adapt` — installed once if absent, never overwritten by `update` | This repository's own 19-section, fully-formatted `AGENTS.md` **is** the starter. There is no separate copy-paste template: an adopter installs it via `init`, then edits every repo-specific fact (owner, file paths, tool references) until it genuinely describes the adopting repository. |
| [`project.yaml`](./project.yaml) | `project.yaml` | `render` | Token-rendered, then filled with the adopting repository's actual commands. |

> [!TIP]
> Keeping `AGENTS.md` itself as the seed — rather than a second, drifting `TEMPLATES/AGENTS.md` —
> means every adopter starts from the same document this repository holds itself to, formatting
> included, with no parallel file to keep in sync.

The distribution manifest (`manifest.yaml`), the consuming-repository lock template
(`standard.lock`), desired-state settings and ruleset templates, workflow templates, and the
ignore fragment arrive with the standard tooling.

> [!NOTE]
> Adoption is **explicit, Issue-backed, and owner-controlled** — never automatic. A consuming
> repository's `standard.lock` records provenance informationally and creates no runtime
> dependency.
