# Agent bootstrap

This is a sciharness scientific project. Scientific state lives in files:

- `docs/CHARTER.md` — purpose, scope, and boundaries
- `docs/STATE.md` — current scientific understanding and next actions
- `docs/questions/` — formal questions (`Q###`)
- `docs/decisions/` — append-only scientific decisions (`D###`)
- `explorations/` — lightweight exploratory work (`X###`)
- `experiments/` — evidence-bearing experiments (`EXP###`)
- `data/registry.yaml` — dataset registry

Use `sci` for deterministic bookkeeping (the CLI, not the agent, allocates IDs):

```bash
sci status
sci new question "..."
sci new exploration "..." --question Q001
sci new experiment "..." --question Q001 --exploration X001
sci new decision "..." --question Q001 --experiment EXP001
sci validate
```

If your agent supports skills, load the `scientific-research` skill before
acting. Read `docs/CHARTER.md` and `docs/STATE.md` first. Propose changes to
scientific state; do not silently rewrite it.
