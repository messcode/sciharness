# sciharness

[![CI](https://github.com/messcode/sciharness/actions/workflows/ci.yml/badge.svg)](https://github.com/messcode/sciharness/actions/workflows/ci.yml)

A lightweight, cross-agent scientific research harness.

`sciharness` installs one small Python CLI, `sci`. The CLI scaffolds and
maintains **independent** scientific research repositories whose state lives in
Markdown and YAML files. Any shell-capable agent — Codex, Pi, Claude Code, or
something not written yet — can read and update that state. Agent skills are an
optional convenience layer, never the source of truth.

The harness handles deterministic bookkeeping: scaffolding, ID allocation,
status summaries, and structural validation. Scientific interpretation stays
with the researcher or agent.

```
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

Requires Python 3.8+ and (optionally) Git. You do **not** clone SciHarness to
create scientific projects; install the CLI once and scaffold projects with it.

Recommended, once published to PyPI:

```bash
uv tool install sciharness
```

Latest development version from GitHub:

```bash
uv tool install git+https://github.com/messcode/sciharness.git
```

Alternatives:

```bash
pipx install sciharness
# or into the current environment:
python -m pip install sciharness
```

Check the installed version:

```bash
sci --version
```

## Quick start

```bash
uv tool install sciharness

sci init my-study
cd my-study

sci status
sci new question "What predicts R_k(t)?"
sci new exploration "Inspect early trajectory" --question Q001
sci new experiment "Test accumulated forcing" --question Q001 --exploration X001
sci context
sci show EXP001
sci validate
```

Publication figures are an optional layer on top of the scientific record:

```bash
sci new exploration "Inspect residual structure"
sci new experiment "Confirm residual reproducibility"

sci figure init figure3
sci figure validate figure3
```

## Filesystem layers

SciHarness keeps a clear boundary between four kinds of files:

```text
Scientific record
    explorations/     lightweight scientific records
    experiments/      evidence-bearing records and reproducible settings

Generated computation
    outputs/          generated artifacts; non-authoritative and disposable

Publication production
    manuscript/figures/   publication-figure production and release artifacts
```

The conceptual flow is:

```text
Question
   |
   v
Exploration
   |-- record: explorations/X###/
   |-- generated outputs: outputs/explorations/X###/
   v
Experiment
   |-- record/settings: experiments/EXP###/
   |-- generated outputs: outputs/experiments/EXP###/
   v
Evidence
   v
Manuscript Figure
   |-- working/   (mutable, Git ignored)
   v
 release/          (publication-facing, Git tracked)
```

Exploratory/result plots belong under `outputs/`; manuscript Figures belong
under `manuscript/figures/`. A **plot** is a scientific/computational
visualization; a **Figure** is a publication artifact with a scientific
message and paired source data.

`release/` is Git-tracked publication state; `working/` and `previews/` are
ignored mutable production state. The full lifecycle and the paired
source-data invariant are documented in the generated project's
`docs/guides/FIGURES.md`.

## Commands

| Command | Purpose |
| --- | --- |
| `sci --version` | Report the installed SciHarness package version |
| `sci init TARGET [--name NAME] [--no-git]` | Create a new project from the bundled scaffold and initialize its own Git repository |
| `sci status [--path DIR]` | Deterministic summary of active/recent records and validation state |
| `sci context [--path DIR]` | Deterministic agent routing: which files to read now (charter, state, active records, guidance) |
| `sci show ID [--path DIR]` | Resolve one record ID (`Q###`/`X###`/`EXP###`/`D###`) to its canonical record and output workspace |
| `sci new question TITLE` | Create a question at `docs/questions/Q###-slug.md` |
| `sci new exploration TITLE [--question Q###]` | Create `explorations/X###-slug/NOTE.md` |
| `sci new experiment TITLE [--question Q###] [--exploration X###]` | Create `experiments/EXP###-slug/` with `README.md` and `config.yaml` |
| `sci new decision TITLE [--question Q###] [--experiment EXP###] [--supersedes D###]` | Create an append-only decision at `docs/decisions/D###-slug.md` |
| `sci figure init FIGURE_ID` | Lazily create `manuscript/figures/<id>/` with `FIGURE.md`, `manifest.yaml`, `working/`, `previews/`, and `release/` |
| `sci figure validate FIGURE_ID [--release]` | Check figure structure, paths, roles, references; `--release` also checks approval and artifact/source-data presence |
| `sci validate [--path DIR]` | Check config, expected paths, IDs, required fields, and references |

Commands accept `--path DIR` (default: the current directory, searching
upwards for `.sci.yaml`). IDs are always allocated by the CLI, never by hand.

`sci status`, `sci context`, and `sci show` are intentionally distinct:
`status` reports which scientific objects exist, `context` reports what an
agent should read now, and `show` locates one specific record.

## Scientific object model

```
Question            docs/questions/Q001-<slug>.md
   |
   v
Exploration         explorations/X001-<slug>/NOTE.md        (lightweight, adaptive)
   |
   | optional promotion
   v
Experiment          experiments/EXP001-<slug>/README.md     (evidence-bearing)
   |                                               config.yaml
   v
Evidence / interpretation
   |
   v
Decision            docs/decisions/D001-<slug>.md           (append-only)
   |
   v
STATE update        docs/STATE.md                           (maintained by humans/agents)
```

- **Questions** capture unresolved unknowns. `status: open | answered | dropped`.
- **Explorations** are cheap, revisable, and may contain adaptive work.
- **Experiments** are formal tests: competing hypotheses, design, primary
  estimand, and a falsification/decision rule declared before running. Result
  fields may be filled in later.
- **Decisions** record a change in scientific belief, hypothesis status, or
  research direction — not ordinary implementation choices. Supersede rather
  than rewrite: `sci new decision "..." --supersedes D001`.
- **Runs** are computational provenance in v0.1, not first-class records.

## Generated project layout

```
project/
├── README.md
├── AGENTS.md
├── .gitignore
├── .agents/
│   └── skills/
│       ├── scientific-research/
│       │   └── SKILL.md
│       └── scientific-figures/
│           └── SKILL.md
├── .sci.yaml
├── docs/
│   ├── CHARTER.md
│   ├── STATE.md
│   ├── guides/
│   │   └── FIGURES.md
│   ├── questions/
│   └── decisions/
├── explorations/
├── experiments/
├── data/
│   ├── README.md
│   └── registry.yaml
├── outputs/               (Git ignored)
│   ├── explorations/
│   └── experiments/
├── src/
├── scripts/
└── tests/
```

`manuscript/` is **not** created during `sci init`. It appears lazily the first
time a manuscript figure is initialized:

```
manuscript/figures/figure3/
├── FIGURE.md              (tracked)
├── manifest.yaml          (tracked)
├── working/               (ignored)
│   ├── exploratory/  validation/  cache/  legacy/
├── previews/              (ignored)
└── release/               (tracked)
    ├── main/{with_legend, without_legend_text}/
    ├── supplementary/{with_text, without_text}/
    ├── caption/
    └── source_data/
```

`sci init` copies the template bundled in the Python package, fills the project
name and creation date, creates the empty directories, deploys the packaged
`scientific-research` and `scientific-figures` skills into `.agents/skills/`,
writes `.sci.yaml`, and runs `git init` plus one initial commit (skip with
`--no-git`). It never clones this repository and never copies its `.git`
history.

The `.sci.yaml` schema is intentionally minimal:

```yaml
schema_version: 1

project:
  name: PROJECT_NAME
  created: PROJECT_DATE

paths:
  charter: docs/CHARTER.md
  state: docs/STATE.md
  questions: docs/questions
  decisions: docs/decisions
  explorations: explorations
  experiments: experiments
```

## ID allocation

The CLI, not the agent, allocates IDs. `sci new` scans the existing record
files and uses the highest numeric suffix plus one (`Q001`, `Q002`, ...;
`EXP012`, ...). Allocation is deterministic, testable, and race-free enough for
single-user research projects.

## Validation

`sci validate` checks that:

- `.sci.yaml` exists, parses, and uses a supported `schema_version`;
- every configured path exists and is of the right kind;
- record front matter and experiment `config.yaml` files parse;
- required fields (`id`, `title`, `status`, `created`) are present and valid;
- IDs are unique and match filenames;
- referenced `Q` / `X` / `EXP` / `D` IDs exist, and `supersedes` points
  backwards.

Validation never makes scientific judgments. `sci status` reuses the same
validator and reports the number of problems.

### Figure validation

`sci figure validate FIGURE_ID` checks a manuscript figure without scientific
judgment: the figure directory and `FIGURE.md` exist, `manifest.yaml` parses,
`figure_id` matches the directory, statuses and panel roles are valid, declared
paths are project-relative and stay inside the project, declared release
outputs and source data do not point into `working/` or `previews/`, release
output paths are not duplicated, declared evidence experiments exist, and a
declared `style_file` exists.

`sci figure validate FIGURE_ID --release` additionally requires
`status: validated`, `release.approved: true`, every declared release output on
disk, and every required paired source-data file on disk. Validation never
mutates status or approval. `sci validate` itself never requires
`manuscript/`, so old projects without figures keep validating.

There is intentionally **no** `sci figure release` in v0.2: project-specific
scripts render the final visual and export the paired source CSV from the same
finalized panel data.

## Agent skills

Two canonical skills are packaged and included in both wheels and sdists:

```
src/sciharness/resources/skills/scientific-research/SKILL.md
src/sciharness/resources/skills/scientific-figures/SKILL.md
```

`sci init` deploys both to the portable project-level location:

```
.agents/skills/scientific-research/SKILL.md
.agents/skills/scientific-figures/SKILL.md
```

The `scientific-research` skill describes when to read `CHARTER.md`/`STATE.md`,
when to use an exploration rather than an experiment, when to record a
decision, and to propose rather than silently rewrite scientific state. The
`scientific-figures` skill is loaded only for manuscript-figure work and points
the agent at `docs/guides/FIGURES.md`, the figure's `FIGURE.md` and
`manifest.yaml`, and the project-declared `style.py`. Generated projects also
include a minimal always-on `AGENTS.md` router pointing at the skills and the
`sci` CLI. No agent-specific directories (`.pi/`, `.codex/`, `.claude/`) are
created, and the harness works fully without any skill support.

## Development

```bash
git clone https://github.com/messcode/sciharness.git
cd sciharness
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
pytest
```

The test suite builds a wheel and an sdist and installs the wheel into a
throwaway directory to verify packaged resources and the `sci` entry point, so
`build` and `setuptools` are included in the `dev` extra.

## Scope

v0.1 provides the scientific object model and CLI; v0.1.1 adds distribution as
a standalone tool and portable project-level Agent Skill deployment; v0.2
establishes the filesystem boundary between scientific records, generated
outputs, manuscript-figure production, and publication release artifacts.
Intentionally **not** included in v0.2: `sci figure release`, automatic
plotting, automatic source-data CSV export, pandas/matplotlib dependencies,
source-data inference, image comparison, journal workbook generation, Git LFS
or external-storage integration, manuscript submission packaging, graph
visualization, Obsidian support, migrations, `sci doctor`, automatic `STATE`
updates, and any workflow orchestration. We will dogfood the figure workflow on
real manuscript figures before designing a generic release command.

## License

MIT. See [`LICENSE`](LICENSE).
