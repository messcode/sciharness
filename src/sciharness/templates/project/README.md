# {{PROJECT_NAME}}

Created: {{PROJECT_DATE}}

This is a scientific research project managed with the `sci` CLI from
`sciharness`. Scientific state is stored in Markdown/YAML files, so the
project is readable and editable without any particular agent or tool.

## Layout

| Path | Purpose |
| --- | --- |
| `docs/CHARTER.md` | Purpose, scope, and boundaries |
| `docs/STATE.md` | Current understanding and next actions |
| `docs/questions/` | Formal questions (`Q001-...`) |
| `docs/decisions/` | Append-only scientific decisions (`D001-...`) |
| `explorations/` | Lightweight exploration (`X001-.../NOTE.md`) |
| `experiments/` | Evidence-bearing experiments (`EXP001-...`) |
| `data/` | Data notes and the dataset registry `registry.yaml` |
| `outputs/` | Generated figures, tables, and results |
| `src/`, `scripts/`, `tests/` | Code for computations and analyses |

## Start here

1. Fill in `docs/CHARTER.md`.
2. Record the first formal question: `sci new question "..."`
3. Keep `docs/STATE.md` current as understanding evolves.
4. Check structure before committing: `sci validate`.

Use `sci status` for a deterministic summary of active records.
