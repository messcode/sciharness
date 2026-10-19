# Design

SciHarness is a lightweight, cross-agent scientific research harness. It
installs one Python CLI, `sci`, which scaffolds and maintains independent
research repositories whose state lives in Markdown and YAML files.

## Two responsibilities

The design separates two kinds of work:

- **Deterministic bookkeeping** — scaffolding, ID allocation, navigation,
  structural validation, provenance links, and release hashes. This is the
  CLI's job.
- **Scientific interpretation** — deciding what a result means, which
  hypothesis survives, and what to do next. This stays with the researcher or
  the host agent.

The CLI never judges whether a claim is true. It only checks that the record is
structurally sound and internally consistent.

## File-first, tool-agnostic

There is no database and no server. Every piece of state is a text file that can
be read, diffed, reviewed, and migrated with ordinary tools. Agent Skills are an
optional convenience layer; the files and the CLI work without them.

## Filesystem layers

```text
Scientific record
    explorations/      lightweight, adaptive records
    experiments/       evidence-bearing records and run metadata

Generated computation
    outputs/           generated artifacts; non-authoritative, Git ignored

Publication production
    manuscript/figures/   figure production and release artifacts
```

A **plot** is a scientific or exploratory visualization. A **Figure** is a
publication artifact with a scientific message, declared evidence, and paired
source data. Exploratory plots belong under `outputs/`; only publication
Figures belong under `manuscript/figures/`.

`release/` is Git-tracked publication state. `working/` and `previews/` are
mutable and ignored.

## Scientific object model

```text
Question
   |
   v
Exploration
   |-- record: explorations/X###/
   |-- outputs: outputs/explorations/X###/
   v
Experiment
   |-- record/config: experiments/EXP###/
   |-- run metadata: experiments/EXP###/run.yaml
   |-- outputs: outputs/experiments/EXP###/
   v
Evidence / interpretation
   |
   v
Decision
   |
   v
STATE update
```

- **Questions** capture unresolved unknowns (`open`, `answered`, `dropped`).
- **Explorations** are cheap, revisable, and may contain adaptive work.
- **Experiments** are formal tests with competing hypotheses, design, primary
  estimand, and a falsification/decision rule declared before running.
- **Decisions** record a change in scientific belief, hypothesis status, or
  research direction. They are append-only; supersede rather than rewrite.
- **Runs** are computational provenance attached to an Experiment through
  `run.yaml`; they are not a separate record type.
- **Datasets** are declared in `data/registry.yaml` and referenced by
  experiments and figure panels.

## Provenance

Provenance is expressed as relationships between existing objects:

| Relation | Source | Target |
| --- | --- | --- |
| `question` | exploration / experiment / decision | question |
| `exploration` | experiment | exploration |
| `evidence` | decision | exploration / experiment |
| `motivated_by` | exploration / experiment | decision |
| `supersedes` | decision | decision |
| `datasets` | experiment | dataset registry entry |

The relation registry lives in `sciharness/project.py`. `sci show ID --related`
walks it forward and backward, so an agent can answer both “what does this
depend on?” and “what depends on this?”.

## Identity and IDs

IDs are project-level identities, not directory decorations.

- `sci new` scans both existing records and permanent claims in `.sci/ids/`,
  then atomically reserves the next ID with `O_CREAT | O_EXCL`.
- Claims survive record deletion, so an ID is never reused for a different
  scientific object.
- Claims are Git-tracked. Concurrent branch allocations conflict explicitly
  instead of silently producing duplicate IDs.
- `sci doctor --fix` backfills claims for records created before the ledger
  existed.

Deleting a record should be a status transition (`dropped` / `abandoned`), not
an `rm`. If a directory is removed, its claim still protects the ID.

## Lifecycle and pre-registration

A planned experiment should be started explicitly:

```bash
sci start EXP001
```

`sci start` moves the status to `running`, hashes the pre-registered
hypotheses/design/estimand/decision rule and dataset links, and writes
`run.yaml`. Editing those design sections afterwards makes `sci validate` fail.
Editing `Results` or `Interpretation` does not, because they are not part of the
pre-registration.

`run.yaml` records command, code commit, environment, seeds, datasets, and
outputs manifest. SciHarness validates structure and references; project scripts
execute the experiment and write the metadata.

## Validation philosophy

Validation is structural:

- configuration and expected paths;
- record front matter and required fields;
- ID uniqueness and filename agreement;
- references and provenance edges;
- dataset registry shape, local paths, and optional hashes;
- `run.yaml` shape and pre-registration hash;
- figure structure, paths, roles, evidence, approval, and artifact hashes.

It does not judge scientific meaning. Problems become structured diagnostics
with `code`, `severity`, `message`, and optional `path`/`field`/`hint`.
`sci status`, `sci context`, `sci validate`, and `sci doctor` share the same
validator.

## Figure release boundary

Figure production is separate from the scientific record lifecycle:

```text
working -> validation -> explicit human approval -> release
```

`working/` and `previews/` are mutable. `release/` is publication-facing and
Git-tracked. Release layout is **declared by the manifest**, not imposed by the
scaffold.

`sci figure approve` records the approver, timestamp, commit, canonical manifest
hash, `FIGURE.md` hash, and SHA-256 hashes of every declared release output and
required source-data file. `sci figure validate --release` re-checks those
hashes, so editing the manifest, figure narrative, visual, or CSV after approval
invalidates the release check. Approval itself remains an explicit human
decision; the record makes it auditable.

The paired source-data invariant is:

> Released paired source data must be generated from the same finalized panel
> data used to render the released visual output.

## Scaffold lifecycle

`sci init` writes a hash baseline to `.sci/scaffold.json`. `sci doctor`
distinguishes user modifications from files that lag behind the installed
package. `sci upgrade` updates unmodified files and writes `.new` sidecars for
locally modified ones; `--force` is required to overwrite.

Project configuration schema changes are separate: `sci migrate` applies
explicit, sequential migrations to `.sci.yaml`.

## Non-goals

SciHarness intentionally does not provide:

- a database, server, daemon, or workflow orchestrator;
- automatic plotting, source-data export, or `sci figure release`;
- image comparison, journal workbook generation, or submission packaging;
- Git LFS or object-storage integration;
- automatic `STATE.md` updates;
- scientific judgments about hypotheses, results, or conclusions.

The boundary is deliberate: the harness makes the record trustworthy, while the
researcher and host agent remain responsible for the science.
