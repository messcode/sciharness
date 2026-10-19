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

Requires Python 3.8+ and Git. You do **not** clone SciHarness to create
scientific projects; install the CLI once and scaffold projects with it.

Install directly from GitHub with uv:

```bash
uv tool install git+https://github.com/messcode/sciharness.git
```

The same Git URL works with other installers:

```bash
pipx install git+https://github.com/messcode/sciharness.git
# or into the current environment:
python -m pip install git+https://github.com/messcode/sciharness.git
```

Check the installed version:

```bash
sci --version
```

Update later with:

```bash
uv tool upgrade sciharness
```

## Quick start

```bash
uv tool install git+https://github.com/messcode/sciharness.git

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

# after explicit human review of the validated figure:
sci figure approve figure3 --by "Reviewer Name"
sci figure validate figure3 --release
```

## Provenance links

Record why a decision was made and what work it motivated:

```bash
sci new decision "Revise the working hypothesis" \
  --question Q001 \
  --evidence X003 \
  --evidence EXP007

sci new experiment "Test revised prediction" \
  --question Q001 \
  --motivated-by D001
```

`evidence` links scientific observations/tests to a Decision; `motivated_by`
links that Decision to subsequent work. `sci validate` checks that these
references are structurally valid; it does not judge the science.

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
| `sci new exploration TITLE [--question Q###] [--motivated-by D###]` | Create `explorations/X###-slug/NOTE.md` |
| `sci new experiment TITLE [--question Q###] [--exploration X###] [--motivated-by D###]` | Create `experiments/EXP###-slug/` with `README.md` and `config.yaml` |
| `sci new decision TITLE [--question Q###] [--experiment EXP###] [--evidence X###|EXP###] [--supersedes D###]` | Create an append-only decision at `docs/decisions/D###-slug.md` |
| `sci figure init FIGURE_ID` | Lazily create `manuscript/figures/<id>/` with `FIGURE.md`, `manifest.yaml`, `working/`, `previews/`, and `release/` |
| `sci figure approve FIGURE_ID [--by NAME]` | Record explicit approval plus manifest/FIGURE/artifact hashes at `release/APPROVAL.yaml`; requires `status: validated` |
| `sci figure validate FIGURE_ID [--release]` | Check figure structure, paths, roles, references; `--release` also checks the approval record and artifact/source-data hashes |
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
  fields may be filled in later. Identity, status, and provenance live only in
  `README.md` front matter; `config.yaml` holds computational settings
  (`record: EXP###`, parameters, environment) and does not duplicate them.
- **Decisions** record a change in scientific belief, hypothesis status, or
  research direction — not ordinary implementation choices. Supersede rather
  than rewrite: `sci new decision "..." --supersedes D001`.
- **Runs** are computational provenance; they are not first-class scientific
  records in the current version.

Provenance is expressed as relationships between existing scientific objects:
`evidence` on a Decision, and `motivated_by` on an Exploration or Experiment.
`sci` records and validates the explicit structure only; deciding scientific
meaning stays with the researcher or host agent. Add a new object type only
after real use shows the existing objects cannot represent the required
provenance.

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
├── .sci/
│   └── ids/               (permanent ID claims; Git tracked)
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
    ├── APPROVAL.yaml      (written by `sci figure approve`)
    ├── main/{with_legend, without_legend_text}/
    ├── supplementary/{with_text, without_text}/
    ├── caption/
    └── source_data/
```

`sci init` copies the template bundled in the Python package, fills the project
name and creation date, creates the empty directories (with `.gitkeep`
placeholders so a fresh clone keeps them), deploys the packaged
`scientific-research` and `scientific-figures` skills into `.agents/skills/`,
writes `.sci.yaml`, and runs `git init` plus one initial commit (skip with
`--no-git`). It never clones this repository and never copies its `.git`
history. `sci new` also recreates a missing record directory lazily, so a
cloned or partially cleaned project remains usable.

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

The CLI, not the agent, allocates IDs. `sci new` scans both existing records
and the permanent claims in `.sci/ids/`, then atomically reserves the next ID
with `O_CREAT | O_EXCL` (`Q001`, `Q002`, ...; `EXP012`, ...).

- **IDs are never reused.** A claim file survives deletion of its record, so
  `rm -rf experiments/EXP003-*` cannot make a future experiment become
  `EXP003` and inherit the old `outputs/experiments/EXP003/`.
- **Concurrent `sci new` calls are safe.** They race on the claim file, not on
  a read-then-write scan; losers retry with the next number.
- **Claims are Git tracked.** If two branches allocate the same ID, the claim
  files conflict explicitly (they carry a random `claim_id`) instead of
  silently producing duplicate records after a merge.
- **Delete is a status change, not a file operation.** Prefer setting a
  record's status to `dropped`/`abandoned`; if a directory is removed, its
  claim still prevents reuse. A future `sci renumber` is the repair path for
  duplicate IDs introduced by a merge.

## Validation

`sci validate` checks that:

- `.sci.yaml` exists, parses, and uses a supported `schema_version`;
- every configured path exists and is of the right kind;
- record front matter and experiment `config.yaml` files parse;
- required fields (`id`, `title`, `status`, `created`) are present and valid;
- experiment `config.yaml` declares the owning `record: EXP###` (legacy `id`
  and `title` copies are accepted when they agree with the README);
- IDs are unique and match filenames;
- referenced `Q` / `X` / `EXP` / `D` IDs exist, and `supersedes` points
  backwards.

Validation never makes scientific judgments. `sci status` reuses the same
validator and returns a non-zero exit code when problems exist, so it can be
used as a health check by agents and CI.

### Figure validation

`sci figure validate FIGURE_ID` checks a manuscript figure without scientific
judgment: the figure directory and `FIGURE.md` exist, `manifest.yaml` parses,
`figure_id` matches the directory, statuses and panel roles are valid, declared
paths are project-relative and stay inside the project, declared release
outputs and source data do not point into `working/` or `previews/`, release
output paths are not duplicated, declared evidence experiments exist, and
declared `generator.file` / `style_file` paths exist.

`sci figure validate FIGURE_ID --release` additionally requires
`status: validated` or `released`, `release.approved: true`, at least one
declared release output, every declared output and required paired source-data
file on disk, and an intact `release/APPROVAL.yaml`.

`release/APPROVAL.yaml` is written by `sci figure approve FIGURE_ID --by NAME`
(requires `status: validated`) and records the approver, timestamp, current Git
commit, a canonical manifest hash, a `FIGURE.md` hash, and SHA-256 hashes of
all declared artifacts and required source data. `--release` recomputes them,
so editing the manifest, `FIGURE.md`, visual, or CSV after approval invalidates
the release check. Approval is still an explicit human decision; the record
makes it auditable rather than merely a boolean. Validation never mutates
status or approval. `sci validate` itself never requires `manuscript/`, so old
projects without figures keep validating.

There is intentionally **no** `sci figure release` in v0.2: project-specific
scripts render the final visual and export the paired source CSV from the same
finalized panel data. After approval, a human may change `status` to
`released`; the approval remains valid because review hashes exclude the
`status` and `release` fields themselves.

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
v0.2.1 hardens the invariants: clone-safe scaffolds, permanent atomic ID
claims, a single source of truth for experiment identity, auditable figure
approval hashes, and a non-zero `sci status` exit code on validation failure.
Intentionally **not** included in v0.2: `sci figure release`, automatic
plotting, automatic source-data CSV export, pandas/matplotlib dependencies,
source-data inference, image comparison, journal workbook generation, Git LFS
or external-storage integration, manuscript submission packaging, graph
visualization, Obsidian support, migrations, `sci doctor`, automatic `STATE`
updates, and any workflow orchestration. We will dogfood the figure workflow on
real manuscript figures before designing a generic release command.

## License

MIT. See [`LICENSE`](LICENSE).
