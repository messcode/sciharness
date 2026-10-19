# Manuscript figures

Figure production is an optional layer on top of the scientific record. It is
separate from the experiment lifecycle and never changes a scientific result.

## Plot vs Figure

```text
outputs/.../plots/       scientific / exploratory / result plots
manuscript/figures/      publication artifact production
```

A **plot** is a scientific or computational visualization. A **Figure** is a
publication artifact with a scientific message, declared evidence, validation
criteria, and paired source data.

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

## Lifecycle

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

- `working/` is mutable production state (`exploratory/`, `validation/`,
  `cache/`, `legacy/`); it is Git ignored.
- `previews/` holds intermediate previews; it is Git ignored.
- `release/` is publication-facing, Git tracked, and contains only declared
  release outputs and source data.

`sci figure init` creates `FIGURE.md`, `manifest.yaml`, `working/`, `previews/`,
and `release/`. It does **not** impose release subdirectories such as
`release/main/with_legend`. The manifest declares the paths; project scripts
create them.

## Figure files

- `FIGURE.md` — scientific message, evidence basis, panel structure, validation
  requirements, release criteria.
- `manifest.yaml` — machine-readable status, style, panels, artifact paths, and
  evidence references.
- `release/APPROVAL.yaml` — written by `sci figure approve`; approver,
  timestamp, commit, and review hashes.

`manifest.yaml` supports multiple evidence targets per panel:

```yaml
panels:
  A:
    role: main
    evidence:
      experiments: [EXP001, EXP002]
      explorations: [X001]
      datasets: [DS001]
    outputs:
      with_legend: release/main/with_legend/Fig3a.pdf
    source_data:
      required: true
      files: [release/source_data/Fig3a.csv]
```

The legacy `evidence: {experiment: EXP001}` form is still accepted.

## Source-data invariant

> Released paired source data must be generated from the same finalized panel
> data used to render the released visual output.

Validation CSVs in `working/validation/` are not automatically authoritative
source data. For each panel, a project-specific script should produce both
outputs from one finalized panel data object:

```text
finalized panel data
        |
        +--> render final visual
        |
        +--> export paired source CSV
```

Panels with no meaningful tabular data (conceptual schematics, microscopy
images, illustrative diagrams) may declare `source_data.required: false`.

## Release approval

Release requires explicit human approval. After the figure is validated:

```bash
sci figure approve figure3 --by "Reviewer Name"
sci figure validate figure3 --release
```

`approve` captures:

- the approver and timestamp;
- the current Git commit;
- a canonical hash of the reviewable manifest content (excluding status and
  approval metadata);
- a `FIGURE.md` hash;
- SHA-256 hashes of every declared release output and required source-data
  file.

`validate --release` recomputes those hashes. Editing the manifest, narrative,
visual, or CSV after approval invalidates the release check. The approval record
makes the decision auditable; it cannot prove that a human rather than an agent
pressed the button, so agents must still wait for explicit user approval.

`status` may be `validated` or `released` for a release-ready figure. The
manifest hash intentionally excludes `status`/`release`, so moving from
`validated` to `released` does not invalidate approval.

## Commands

```bash
sci figure init figure3
sci figure validate figure3
sci figure approve figure3 --by "Reviewer Name"
sci figure validate figure3 --release
```

All figure commands accept `--json`. There is no `sci figure release`; project
scripts render the final visual and export paired source data.
