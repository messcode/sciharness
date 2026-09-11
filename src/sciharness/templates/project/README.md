# {{PROJECT_NAME}}

Created: {{PROJECT_DATE}}

This is a scientific research project managed with the `sci` CLI from
`sciharness`. Scientific state is stored in Markdown/YAML files, so the
project is readable and editable without any particular agent or tool.

## Layers

```text
Scientific record
    explorations/
    experiments/

Generated computation
    outputs/

Publication production
    manuscript/figures/
```

- `explorations/` and `experiments/` hold **scientific records** and reproducible
  settings. They are Git tracked.
- `outputs/` holds **generated computational artifacts** (plots, tables, logs,
  checkpoints, caches). It is non-authoritative, disposable, and Git ignored.
- `manuscript/figures/` holds **publication-figure production and release
  artifacts**. `release/` is Git tracked; `working/` and `previews/` are ignored
  mutable production state.

Exploratory/result plots belong under `outputs/`; manuscript Figures belong
under `manuscript/figures/`. See `docs/guides/FIGURES.md` for the figure
lifecycle and the paired source-data invariant.

## Layout

| Path | Purpose |
| --- | --- |
| `docs/CHARTER.md` | Purpose, scope, and boundaries |
| `docs/STATE.md` | Current understanding and next actions |
| `docs/guides/FIGURES.md` | Project-wide manuscript-figure conventions |
| `docs/questions/` | Formal questions (`Q001-...`) |
| `docs/decisions/` | Append-only scientific decisions (`D001-...`) |
| `explorations/` | Lightweight exploration (`X001-.../NOTE.md`) |
| `experiments/` | Evidence-bearing experiments (`EXP001-...`) |
| `outputs/` | Generated outputs: `outputs/explorations/X###/`, `outputs/experiments/EXP###/` |
| `manuscript/figures/` | Publication figures (`<id>/working`, `previews`, `release`) |
| `data/` | Data notes and the dataset registry `registry.yaml` |
| `src/`, `scripts/`, `tests/` | Code for computations and analyses |
| `.agents/skills/` | Portable project-level Agent Skills (optional; the host may ignore it) |

## Start here

1. Fill in `docs/CHARTER.md`.
2. Record the first formal question: `sci new question "..."`
3. Keep `docs/STATE.md` current as understanding evolves.
4. Check structure before committing: `sci validate`.

Use `sci status` for a deterministic summary of active records.
