# File schemas

All persistent state is Markdown/YAML. The schemas below are validated
structurally by `sci validate` and `sci figure validate`; they never encode
scientific judgments.

## `.sci.yaml`

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

Required path keys: `charter`, `state`, `questions`, `decisions`,
`explorations`, `experiments`. Paths must be project-relative and stay inside
the project root. `sci migrate` upgrades older/missing `schema_version` values.

## Record front matter

Common required fields:

```yaml
id: Q001            # Q### / X### / EXP### / D###
title: "..."
status: open
created: 2026-10-19
```

Status values by kind:

| Kind | Statuses |
| --- | --- |
| question | `open`, `answered`, `dropped` |
| exploration | `active`, `paused`, `completed`, `dropped` |
| experiment | `planned`, `running`, `completed`, `abandoned` |
| decision | `active`, `superseded`, `rejected` |

Optional references:

```yaml
question: Q001
exploration: X001
motivated_by: [D001]
evidence: [X003, EXP007]
supersedes: D001
datasets: [DS001]       # experiment
```

`decision.evidence` may point to explorations or experiments. `motivated_by`
points to decisions. `supersedes` must point to an earlier decision.

Records live at:

```text
docs/questions/Q001-<slug>.md
docs/decisions/D001-<slug>.md
explorations/X001-<slug>/NOTE.md
experiments/EXP001-<slug>/README.md
```

## Experiment `config.yaml`

Computational settings only; identity/status/provenance are **not** duplicated
here.

```yaml
schema_version: 1
record: EXP001
parameters: {}
```

Legacy configs with `id`/`title` are accepted when they agree with the README.

## Experiment `run.yaml`

Optional until a run happens; `sci start` creates it.

```yaml
schema_version: 1
record: EXP001
command: python scripts/run_exp001.py   # string or list of strings
code_commit: "<git sha>"
started_at: "2026-10-19T03:00:00+00:00"
finished_at: "2026-10-19T05:00:00+00:00"
environment: {python: "3.12", lockfile_sha256: "<sha>"}
datasets: [DS001]
seeds: {numpy: 0}
outputs_manifest: outputs/experiments/EXP001/manifest.json
preregistration_sha256: "<hash>"
```

`record`, `started_at`, and `preregistration_sha256` are written/updated by
`sci start`. `sci validate` checks types, dataset references, path safety, and
that the pre-registration hash still matches the README's design sections.

## `data/registry.yaml`

```yaml
schema_version: 1
datasets:
  - id: DS001
    name: trajectory-run-01
    storage: local              # local (default) or external
    path: data/raw/run01.csv    # required for local
    sha256: "<64-hex>"          # optional
    source: simulation
    acquired: "2026-02-12"
    license: CC-BY-4.0
    notes: Initial forcing sweep.
```

External datasets use `uri:` instead of `path:`. Local paths must exist and stay
inside the project. `sci validate --verify-hashes` recomputes `sha256`.

## Figure `manifest.yaml`

```yaml
schema_version: 1
figure_id: figure3
status: working                 # working / validated / released
style_file: style.py            # or null; project-relative

release:
  approved: false               # written by `sci figure approve`

panels:
  A:
    role: main                  # main / supplementary
    evidence:
      experiment: EXP001        # legacy single experiment
      experiments: [EXP001]     # or lists
      explorations: [X001]
      datasets: [DS001]
    generator:
      file: scripts/figure3.py
      target: panel_a
    outputs:
      with_legend: release/main/with_legend/Fig3a.pdf
    source_data:
      required: true
      files: [release/source_data/Fig3a.csv]
```

Path conventions:

- `generator.file` and `style_file` are relative to the project root;
- panel `outputs.*` and `source_data.files` are relative to the figure
  directory; paths rooted at `manuscript/` are accepted and resolved from the
  project root.

Release output paths must stay inside the figure's own `release/` tree; source
data must stay inside `release/source_data/`; duplicates are rejected.

## `release/APPROVAL.yaml`

Written by `sci figure approve`; do not edit by hand.

```yaml
schema_version: 1
figure_id: figure3
approved_by: "Reviewer Name"
approved_at: "2026-10-19T10:30:00+08:00"
reviewed_commit: "<git sha or null>"
manifest_sha256: "<canonical reviewable manifest hash>"
figure_md_sha256: "<FIGURE.md hash>"
artifacts:
  release/main/with_legend/Fig3a.pdf: "<sha256>"
  release/source_data/Fig3a.csv: "<sha256>"
```

The canonical manifest hash excludes `status` and `release`, so the legitimate
`validated -> released` transition does not invalidate approval.

## `.sci/scaffold.json`

Managed-file baseline used by `sci doctor` / `sci upgrade`.

```json
{
  "schema_version": 1,
  "sciharness_version": "0.6.0",
  "scaffold_version": 1,
  "files": {"AGENTS.md": "<sha256>", "...": "..."},
  "pending": ["AGENTS.md"]
}
```

`pending` appears only when `.new` sidecars still need review.

## Version fields

| File | Field | Current |
| --- | --- | --- |
| `.sci.yaml` | `schema_version` | 1 |
| experiment `config.yaml` | `schema_version` | 1 |
| experiment `run.yaml` | `schema_version` | 1 |
| `data/registry.yaml` | `schema_version` | 1 |
| figure `manifest.yaml` | `schema_version` | 1 |
| `release/APPROVAL.yaml` | `schema_version` | 1 |
| `.sci/scaffold.json` | `schema_version` / `scaffold_version` | 1 / 1 |

`sci migrate` handles `.sci.yaml`; figure/record schemas are validated and will
gain explicit migrations as they change.
