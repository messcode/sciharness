# Agent bootstrap

This project uses SciHarness. `sci` performs deterministic bookkeeping;
scientific interpretation stays with the researcher and the host agent.

## Scientific context

For current scientific state, read `docs/CHARTER.md` (purpose, scope,
constraints) and `docs/STATE.md` (current understanding and next actions).
Use the `scientific-research` skill when available
(`.agents/skills/scientific-research/SKILL.md`). STATE.md, not a
chronological replay, is the current picture: when history and STATE differ,
keep the historical provenance but trust the newer state.

## Bookkeeping

- Create records with `sci new question|exploration|experiment|decision`.
- Never invent IDs (Q###, X###, EXP###, D###); `sci` allocates them.
- Run `sci validate` after structural changes.
- Orient with `sci context`; locate one record with `sci show ID`.

## Manuscript figures

When creating, revising, validating, or preparing manuscript figures for release:

1. read `docs/guides/FIGURES.md`;
2. use the `scientific-figures` skill when available;
3. read the relevant figure's `FIGURE.md` and `manifest.yaml`;
4. read and use the project-declared plotting style file.

Do not load figure guidance for unrelated tasks.

## Invariants

- Source data is immutable once acquired.
- Generated outputs belong under `outputs/`.
- Experiment-specific settings belong to that experiment.
- Historical decisions are append-only; supersede, do not rewrite.
- Markdown/YAML files and the `sci` CLI work without any skill support.
