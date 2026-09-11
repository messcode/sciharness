---
name: scientific-figures
description: Use when creating, revising, validating, or preparing a manuscript-quality figure for release in a sciharness project. Covers the working/release boundary, explicit human approval, and paired source-data provenance. Do not load this skill for unrelated coding or scientific work.
---

# Manuscript figures in a sciharness project

Use this skill only for manuscript-figure work: creating, revising, validating,
or preparing a figure for release. Do not load it for unrelated coding or
scientific work.

Before producing manuscript-quality plots, read, in order:

1. `docs/guides/FIGURES.md` — project-wide manuscript-figure conventions;
2. the relevant figure's `FIGURE.md` — scientific message, panels, criteria;
3. the relevant figure's `manifest.yaml` — status, declared paths and panels;
4. the project-declared `style.py` (the `style_file` in `manifest.yaml`) — the
   project's plotting style.

If `style_file` is `null`, early figure work may proceed, but do not invent a
project style and do not create or modify `style.py` on your own.

## Boundaries

- `manuscript/figures/<id>/working/` and `previews/` are mutable production
  state and are ignored by Git.
- `manuscript/figures/<id>/release/` is publication-facing state and is Git
  tracked.
- Release requires explicit human approval. Never set `release.approved: true`
  and never change `status` to `released` unless the user explicitly approves.
- Paired source data must be exported from the same finalized panel data used
  to render the released visual. Validation CSVs in `working/validation/` are
  not automatically authoritative source data; regenerate them after a panel
  changes.
- Working, cache, validation, preview and legacy artifacts must never silently
  become release artifacts.
- SciHarness does not render plots or export source data. Project-specific
  scripts produce the final visual and the paired source CSV. Do not invent a
  `sci figure release` step.

## Commands

- `sci figure init <id>` scaffolds a figure directory.
- `sci figure validate <id>` checks structure.
- `sci figure validate <id> --release` checks release readiness; it does not
  mutate status or approval.
