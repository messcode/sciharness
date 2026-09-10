---
name: scientific-research
description: Use when working inside a sciharness scientific project (a repository containing .sci.yaml). Covers reading scientific state, creating questions, explorations, experiments, and decisions, and proposing rather than silently rewriting conclusions.
---

# Scientific research in a sciharness project

A sciharness project stores scientific state in Markdown/YAML files. The `sci`
CLI handles deterministic bookkeeping: scaffolding, ID allocation, status, and
validation. You handle scientific interpretation.

`sci init` deploys this skill into the project at
`.agents/skills/scientific-research/SKILL.md`, the portable project-level Agent
Skills location.

## Orientation

Before acting:

1. Read `docs/CHARTER.md` (purpose, scope, constraints).
2. Read `docs/STATE.md` (current understanding and next actions).
3. Run `sci status` for active questions, explorations, experiments, and
   recent decisions.
4. Run `sci validate` if files may have drifted.

## Bookkeeping rules

- Never invent IDs (Q###, X###, EXP###, D###). Always create records with
  `sci new ...`, which allocates IDs deterministically.
- Link records when the relationship is real, for example
  `sci new experiment "..." --question Q001 --exploration X003`.
- After changing files, run `sci validate` before committing.

## When to create each record

- **Question** (`sci new question`): a crisp unknown the project is trying to
  resolve, not a task or a curiosity.
- **Exploration** (`sci new exploration`): open-ended, adaptive work — looking
  at data, trying ideas, checking feasibility. Cheap and revisable.
- **Experiment** (`sci new experiment`): a claim that needs evidence. Promote
  an exploration when there is a testable prediction and a
  falsification/decision rule declared up front. Fill in competing
  hypotheses, design, primary estimand, and the decision rule before running.
- **Decision** (`sci new decision`): a change in scientific belief, hypothesis
  status, or research direction. Ordinary implementation choices belong in
  commits and code comments, not in decisions. Decisions are append-only; use
  `--supersedes D00x` rather than editing an old decision's meaning.

## Boundaries

- Propose changes to `docs/STATE.md` and `docs/CHARTER.md`; do not silently
  rewrite scientific state. State the change and the evidence behind it.
- Do not upgrade an exploratory observation into a conclusion without an
  evidence-bearing experiment or decision record.
- `sci validate` checks structure, not science. It never judges whether a
  conclusion is correct.
- The harness works without this skill; keep the files as the source of truth.
