# sciharness

[![CI](https://github.com/messcode/sciharness/actions/workflows/ci.yml/badge.svg)](https://github.com/messcode/sciharness/actions/workflows/ci.yml)

A lightweight, cross-agent scientific research harness.

`sciharness` installs one small Python CLI, `sci`. The CLI scaffolds and
maintains **independent** scientific research repositories whose state lives in
Markdown and YAML files. Any shell-capable agent — Codex, Pi, Claude Code, or
something not written yet — can read and update that state. Agent Skills are an
optional convenience layer, never the source of truth.

The harness handles deterministic bookkeeping: scaffolding, ID allocation,
status summaries, structural validation, provenance links, and release hashes.
Scientific interpretation stays with the researcher or agent.

```text
sciharness repository
        |
        | installs `sci`
        v
sci init <new-project-directory>
        |
        v
independent scientific repository with fresh Git history
```

## Install

Requires Python 3.10+ and Git. You do **not** clone SciHarness to create
scientific projects; install the CLI once and scaffold projects with it.

Install a pinned release from GitHub with uv:

```bash
uv tool install "git+https://github.com/messcode/sciharness.git@v0.7.0"
```

The same Git URL works with other installers:

```bash
pipx install "git+https://github.com/messcode/sciharness.git@v0.7.0"
# or into the current environment:
python -m pip install "git+https://github.com/messcode/sciharness.git@v0.7.0"
```

Check and update:

```bash
sci --version
uv tool upgrade sciharness
```

Pin a tag for reproducible research environments; use the latest tag when
starting a new project.

## Quick start

```bash
sci init my-study
cd my-study

sci status
sci new question "What predicts R_k(t)?"
sci new exploration "Inspect early trajectory" --question Q001
sci new experiment "Test accumulated forcing" \
  --question Q001 --exploration X001

# fill in hypotheses/design/estimand/decision rule, then freeze them:
sci start EXP001
sci context
sci show EXP001 --related
sci validate
```

Publication figures are an optional layer:

```bash
sci figure init figure3
sci figure validate figure3

# after explicit human review of the validated figure:
sci figure approve figure3 --by "Reviewer Name"
sci figure validate figure3 --release
```

## Commands

| Command | Purpose |
| --- | --- |
| `sci --version` | Report the installed package version |
| `sci init TARGET [--name NAME] [--no-git]` | Create an independent project with a fresh Git history |
| `sci status` | Summarize active/recent records and validation state |
| `sci context` | Deterministic agent routing: what to read now, plus diagnostics |
| `sci show ID [--related]` | Locate one record; `--related` adds incoming references |
| `sci new question\|exploration\|experiment\|decision` | Create a record with a CLI-allocated ID |
| `sci start EXP###` | Move planned → running and freeze the pre-registration |
| `sci validate [--verify-hashes]` | Check structure, references, registry, `run.yaml`, pre-registration |
| `sci figure init\|approve\|validate` | Scaffold, approve, and validate manuscript figures |
| `sci doctor [--fix]` | Diagnose structure, scaffold drift, and unclaimed IDs |
| `sci upgrade [--dry-run] [--force]` | Update managed scaffold files without clobbering edits |
| `sci migrate [--dry-run]` | Apply `.sci.yaml` schema migrations |
| `sci web [--host HOST] [--port PORT] [--open]` | Serve a read-only local decision-chain/provenance viewer |

All project commands accept `--path DIR` (default: current directory, searching
upwards for `.sci.yaml`) and `--json`. IDs are always allocated by the CLI,
never by hand. `sci web --json` prints the viewer URL before serving.

## Agent interface

`--json` emits one stable object:

```json
{
  "schema_version": 1,
  "command": "context",
  "ok": true,
  "project": {"root": "/path/to/project", "name": "My Study"},
  "read_first": ["docs/CHARTER.md", "docs/STATE.md"],
  "active": {"questions": [], "explorations": [], "experiments": []},
  "recent_decisions": [],
  "guidance": [],
  "diagnostics": []
}
```

`diagnostics` carry `code`, `severity`, `message`, and optional `path`/`field`/
`hint`. Exit codes: `0` success, `1` validation failure, `2` usage, `3`
project/config error. JSON errors still emit JSON.

## File layers

```text
Scientific record        explorations/  experiments/
Generated computation    outputs/            (Git ignored)
Publication production   manuscript/figures/ (release/ tracked)
```

Experiments keep identity/status/provenance in `README.md`, computational
settings in `config.yaml`, run metadata in `run.yaml`, and generated artifacts
under `outputs/experiments/EXP###/`. Datasets are declared in
`data/registry.yaml`. Figure panels declare evidence experiments, explorations,
and datasets; release layout is declared by the manifest, not imposed by the
scaffold.

## Documentation

- [Design and invariants](docs/DESIGN.md)
- [CLI reference, JSON, exit codes](docs/CLI.md)
- [File schemas](docs/SCHEMA.md)
- [Manuscript figures](docs/FIGURES.md)
- [Web viewer](docs/WEB.md)
- [Changelog](CHANGELOG.md)

The generated project also contains `docs/guides/FIGURES.md`, `AGENTS.md`, and
the `scientific-research` / `scientific-figures` Skills under `.agents/skills/`.

## Scope

v0.1 provides the scientific object model and CLI; v0.1.1 adds standalone
distribution and Skills; v0.2 establishes the filesystem/figure boundary;
v0.2.1 hardens clone/ID/config/release invariants; v0.3 adds the JSON agent
interface, backlinks, `doctor`, and `upgrade`; v0.4 adds dataset/run/
pre-registration provenance and declarative figure layout; v0.5 adds docs,
`sci migrate`, and maintenance tooling; v0.6 adds the read-only `sci web`
decision-chain viewer; v0.7 adds figure nodes, filters, and SVG/PNG export to
that viewer.

Intentionally **not** included: `sci figure release`, automatic plotting or
source-data export, pandas/matplotlib dependencies, image comparison, journal
workbook generation, Git LFS or object-storage integration, manuscript
submission packaging, Obsidian support, automatic `STATE.md` updates, and
workflow orchestration. We will dogfood the figure
workflow on real manuscript figures before designing a generic release command.

## Development

```bash
git clone https://github.com/messcode/sciharness.git
cd sciharness
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
ruff check src tests
pytest
```

The test suite builds a wheel and an sdist and installs the wheel into a
throwaway directory to verify packaged resources and the `sci` entry point, so
`build` and `setuptools` are included in the `dev` extra.

## License

MIT. See [`LICENSE`](LICENSE).
