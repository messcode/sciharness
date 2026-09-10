# sciharness

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

Requires Python 3.8+ and (optionally) Git.

```bash
git clone <this-repository> sciharness
cd sciharness
python -m pip install -e .
# or, isolated:
# pipx install .
```

## Quick start

```bash
sci init ~/projects/example --name "Example Scientific Project"
cd ~/projects/example

sci new question "What predicts R_k(t)?"
sci new exploration "Inspect early trajectory" --question Q001
sci new experiment "Test accumulated forcing" --question Q001 --exploration X001
sci new decision "Product-law sufficiency weakened" --question Q001 --experiment EXP001

sci status
sci validate
```

## Commands (v0.1)

| Command | Purpose |
| --- | --- |
| `sci init TARGET [--name NAME] [--no-git]` | Create a new project from the bundled scaffold and initialize its own Git repository |
| `sci status [--path DIR]` | Deterministic summary of active/recent records and validation state |
| `sci new question TITLE` | Create a question at `docs/questions/Q###-slug.md` |
| `sci new exploration TITLE [--question Q###]` | Create `explorations/X###-slug/NOTE.md` |
| `sci new experiment TITLE [--question Q###] [--exploration X###]` | Create `experiments/EXP###-slug/` with `README.md` and `config.yaml` |
| `sci new decision TITLE [--question Q###] [--experiment EXP###] [--supersedes D###]` | Create an append-only decision at `docs/decisions/D###-slug.md` |
| `sci validate [--path DIR]` | Check config, expected paths, IDs, required fields, and references |

Commands accept `--path DIR` (default: the current directory, searching
upwards for `.sci.yaml`). IDs are always allocated by the CLI, never by hand.

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
├── .sci.yaml
├── docs/
│   ├── CHARTER.md
│   ├── STATE.md
│   ├── questions/
│   └── decisions/
├── explorations/
├── experiments/
├── data/
│   ├── README.md
│   └── registry.yaml
├── outputs/
├── src/
├── scripts/
└── tests/
```

`sci init` copies the template bundled in the Python package, fills the project
name and creation date, creates the empty directories, writes `.sci.yaml`, and
runs `git init` plus one initial commit (skip with `--no-git`). It never clones
this repository and never copies its `.git` history.

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

## Agent skills

`skills/scientific-research/SKILL.md` is a single small skill describing when
to read `CHARTER.md`/`STATE.md`, when to use an exploration rather than an
experiment, when to record a decision, and to propose rather than silently
rewrite scientific state. Generated projects include a short `AGENTS.md`
bootstrap pointing compatible agents at that skill. The harness works fully
without any skill support.

## Development

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Scope of v0.1

Intentionally **not** included: databases, web UI, Obsidian integration,
agent-specific extensions, GitHub Issues integration, manuscript release
builders, automatic `STATE.md` rewriting, dependency graphs, migrations, and
any workflow orchestration. Runs, dataset checksums, and richer analysis
provenance are candidates for later versions.
