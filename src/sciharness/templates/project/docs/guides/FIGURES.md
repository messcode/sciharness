# Manuscript figures

This guide defines how publication figures are produced in this project. It
applies to every figure under `manuscript/figures/`.

## Plots are not Figures

```text
outputs/.../plots/     scientific / exploratory / result plots
manuscript/figures/    publication artifact production
```

A **plot** is a scientific or computational visualization. A **Figure** is a
publication artifact with a scientific message, a declared evidence basis and
paired source data. Exploratory and result plots belong under `outputs/`; only
publication Figures belong under `manuscript/figures/`.

Do not move an exploratory plot into a manuscript figure directory and treat it
as publication evidence. The intended provenance is:

```text
X003 exploratory plot
        |
        v
candidate phenomenon
        |
        v
EXP007 evidence-bearing test
        |
        v
Figure 3B publication artifact
```

Regenerate the Figure from finalized evidence/data rather than copying an
exploratory output.

## Figure lifecycle

```text
working
   |
   v
validation
   |
   v
explicit human approval
   |
   v
final rendering + paired source-data export
   |
   v
release
```

- `working/` is mutable production state (`working/exploratory/`,
  `working/validation/`, `working/cache/`, `working/legacy/`). It is ignored by
  Git.
- `previews/` holds intermediate previews and is ignored by Git.
- `release/` is publication-facing state and is Git tracked.

## Source data invariant

> Released paired source data must be generated from the same finalized panel
> data used to render the released visual output.

Validation CSVs in `working/validation/` are not automatically authoritative
source data. Do not copy stale validation CSVs into release source data after a
panel has changed.

For each panel, a project-specific script must produce both outputs from one
finalized panel data object:

```text
finalized panel data
        |
        +--> render final visual
        |
        +--> export paired source CSV
```

Panels with no meaningful tabular data (conceptual schematics, microscopy
images, illustrative diagrams) may declare `source_data.required: false`.

## Figure files

Every figure directory contains:

- `FIGURE.md` — scientific message, evidence basis, panel structure, validation
  requirements and release criteria;
- `manifest.yaml` — machine-readable status, style, panels and artifact paths.

Paths declared in `manifest.yaml`:

- `generator.file` and `style_file` are relative to the project root;
- panel `outputs.*` and `source_data.files` are relative to the figure
  directory.

## Release requires explicit approval

Release requires explicit human approval. Agents must not set
`release.approved: true` unless the user explicitly approves release, and must
not move a figure to `released` on their own. `sci figure validate --release`
does not approve or mutate anything. Working, cache, validation, preview and
legacy artifacts must never silently become release artifacts.
