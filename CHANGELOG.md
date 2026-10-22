# Changelog

All notable changes are recorded here. The project is pre-1.0; breaking changes
are called out explicitly.

## Unreleased

Optional human-controlled Research Loop.

- Added the separately installable `sciharness-loop` extension with explicit
  `plan`, `step`, and `status` commands, approval-bound plans/results, and
  Docker-isolated Codex execution.
- Core remains record-only by default and never imports the extension. Loop
  execution provenance lives under the project-local `.sci/loop/` directory.
- Controllers create containers with `docker create` and start them separately,
  so recovery can remove a container before any execution begins. Input
  fingerprints namespace file hashes separately from context metadata, and
  resumed acceptance revalidates unrelated Core context changes.
- Local `.sci/loop/` run state is Git-ignored by default; `policy.yaml` remains
  trackable.

### Loop 0.2.0

- Split harness adapters from the Docker execution runtime. Ship Codex and a
  bundled DeepSeek Chat Completions tool loop; the latter is a direct API adapter,
  not the DSH harness.
- Added `guarded_auto` missions with cumulative runtime budgets, cycle limits,
  one-shot IANA/offset-aware execution windows, pause/recovery/resumption,
  preliminary reports, and scheduler-dispatched due runs.
- Mission approval resolves and records the immutable image ID; dispatch requires
  a new approval if the tag now points elsewhere.
- Dispatch continues past a failed mission and reports its errors.
- Result acceptance reviews already-produced evidence: switching
  `guarded_auto` to `step` does not strand completed results. `record_only`
  remains read-only.
- Hardened mission preparation against crashes, ignored half-prepared mission
  directories, and rejected empty CLI mission IDs rather than dispatching.

## 0.8.0

Web viewer redesign.

- Warmer "research notebook" visual language: compact header, serif decision
  titles, status pills, and reduced chrome.
- Decision chain now shows a hero rationale, evidence/result excerpts, and a
  Research brief sourced from `STATE.md`.
- Detail panel shows body excerpts, copy-link/copy-ID actions, and a focus-graph
  action.
- Added hash deep links (`#/decision/D002`, `#/graph`, `#/timeline`,
  `#/record/EXP001`).
- Improved responsive detail layout and keyboard focus for graph nodes.

## 0.7.0

Web viewer enhancements.

- Figure nodes and their panel evidence links now appear in the provenance
  graph.
- Added kind, status, and question filters plus search to the graph, decision
  list, and timeline.
- Added Graph export as SVG or PNG with styles inlined.
- The viewer remains read-only; mutations stay in the CLI.

## 0.6.0

Read-only web viewer.

- Added `sci web` with a local, dependency-free viewer for the decision chain,
  full provenance graph, and decision timeline.
- The viewer exposes only the embedded UI and a read-only `/api/graph` payload;
  it binds to `127.0.0.1:8765` by default.
- Added `docs/WEB.md` and packaged the UI asset in wheels/sdists.

## 0.5.0

Documentation and maintenance release.

- Split the README into focused documents: `docs/DESIGN.md`, `docs/CLI.md`,
  `docs/SCHEMA.md`, and `docs/FIGURES.md`.
- Added `sci migrate` for explicit, sequential `.sci.yaml` schema migrations.
- Added `CHANGELOG.md`, project URLs, and tag-pinned installation guidance.
- Raised the minimum Python version to 3.10 and reduced the CI matrix to
  3.10–3.13.
- Added `ruff` (F/E9 rules) to the dev extra and CI.
- Included `docs/` and `CHANGELOG.md` in sdists.

## 0.4.0

Scientific provenance.

- `data/registry.yaml` is structurally validated: `DS###` IDs, local paths or
  external URIs, optional SHA-256, dates, and `sci validate --verify-hashes`.
- Experiments link datasets with `datasets: [DS###]` or
  `sci new experiment --dataset DS###`.
- Added optional `run.yaml` validation (command, commit, environment, seeds,
  datasets, outputs manifest, timestamps).
- Added `sci start EXP###`: freezes a pre-registration hash and writes
  `run.yaml`; editing pre-registered design sections afterwards fails
  validation.
- Figure panels accept multiple evidence experiments/explorations/datasets.
- Figure release layout is declared by the manifest; `sci figure init` no
  longer imposes fixed `release/...` subdirectories.

## 0.3.0

Agent interface.

- `--json` output for every project command with a stable envelope and
  structured diagnostics.
- Stable exit codes: `0` success, `1` validation failure, `2` usage, `3`
  project/config error.
- `sci show --related` for forward references and backlinks.
- `sci doctor` for structure, scaffold drift, and unclaimed IDs.
- `sci upgrade` with `.sci/scaffold.json` baselines and `.new` sidecars.
- `sci context` surfaces validation diagnostics and stale `STATE.md`.

## 0.2.1

Invariant hardening.

- Clone-safe scaffold: `.gitkeep` files in required directories; `sci new`
  creates missing record directories lazily.
- Permanent atomic ID claims in `.sci/ids/`; deleted IDs are never reused and
  concurrent `sci new` calls are safe.
- Experiment `config.yaml` no longer duplicates identity/status/provenance.
- Figure approval records hashes in `release/APPROVAL.yaml`; `--release`
  verifies them and accepts `status: released`.
- `sci status` returns non-zero on validation failure.
- Unicode titles keep readable filenames.

## 0.2.0

Figure and filesystem boundary.

- Added `manuscript/figures/` production with `working/`, `previews/`, and
  `release/`.
- Added `sci figure init` and `sci figure validate` with path containment,
  panel roles, release separation, and paired source-data checks.

## 0.1.1

Distribution.

- Standalone wheel/sdist packaging and console script.
- Portable project-level Agent Skill deployment under `.agents/skills/`.

## 0.1.0

Bootstrap.

- Initial scientific object model: questions, explorations, experiments,
  decisions.
- `sci init`, `sci new`, `sci status`, `sci context`, `sci show`,
  `sci validate`.
