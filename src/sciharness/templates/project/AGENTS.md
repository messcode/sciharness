# Agent bootstrap

This project uses SciHarness.

- `docs/CHARTER.md` defines project scope.
- `docs/STATE.md` defines the current scientific state.
- Use the `scientific-research` skill when the host supports Agent Skills:
  `.agents/skills/scientific-research/SKILL.md`.
- Use the `sci` CLI for deterministic record creation and validation.

```bash
sci status
sci new question "..."
sci new exploration "..."
sci new experiment "..."
sci validate
```

The Markdown/YAML files and the `sci` CLI work without any skill support.
