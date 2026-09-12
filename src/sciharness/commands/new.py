"""``sci new``: create questions, explorations, experiments, and decisions.

The CLI allocates IDs deterministically from existing filenames; agents never
pick IDs by hand.
"""
from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any, List, Optional, Tuple

import yaml

from ..project import (
    EVIDENCE_KINDS,
    ID_PREFIX,
    MOTIVATED_BY_KINDS,
    ProjectError,
    config_path,
    existing_ids,
    find_project_root,
    next_id,
    relative_path,
    render_record,
    slugify,
    unique_path,
)

QUESTION_BODY = """# {record_id} — {title}

## Question

<!-- State the question. -->

## Context

<!-- Why this matters now. -->
"""

EXPLORATION_BODY = """# {record_id} — {title}

## Motivation

<!-- What prompted this exploration? -->

## Notes

<!-- Adaptive exploratory work. Promote to an experiment when a claim needs
evidence under a pre-declared rule. -->

## Relevant outputs

Generated artifacts belong under:

`outputs/explorations/{record_id}/`

Only reference scientifically useful outputs here; do not enumerate every
generated file.
"""

EXPERIMENT_BODY = """# {record_id} — {title}

## Competing hypotheses

## Design

## Primary estimand

## Falsification / decision rule

## Results

<!-- Fill in after the experiment is run. -->

## Interpretation

<!-- Evidence-based interpretation. Fill in when available. -->

## Generated outputs

Generated plots, tables, logs, checkpoints and caches belong under:

`outputs/experiments/{record_id}/`

The experiment directory itself stores the scientific specification and
reproducible settings.
"""

DECISION_BODY = """# {record_id} — {title}

## Decision

<!-- What changed in scientific belief, hypothesis status, or direction? -->

## Rationale

## Evidence
"""


def run(args: Any) -> int:
    root = find_project_root(Path(args.path))
    title = (args.title or "").strip()
    if not title:
        raise ProjectError("title must be a non-empty string")

    question = _clean(getattr(args, "question", None))
    exploration = _clean(getattr(args, "exploration", None))
    experiment = _clean(getattr(args, "experiment", None))
    supersedes = _clean(getattr(args, "supersedes", None))
    evidence = _dedupe(getattr(args, "evidence", None) or ())
    motivated_by = _dedupe(getattr(args, "motivated_by", None) or ())

    if question:
        _require(root, "question", question)
    if exploration:
        _require(root, "exploration", exploration)
    if experiment:
        _require(root, "experiment", experiment)
    if supersedes:
        _require(root, "decision", supersedes)
    _require_members(root, evidence, EVIDENCE_KINDS, "evidence")
    _require_members(root, motivated_by, MOTIVATED_BY_KINDS, "motivated-by")

    kind = args.record_kind
    if kind == "question":
        return _new_question(root, title)
    if kind == "exploration":
        return _new_exploration(root, title, question, motivated_by)
    if kind == "experiment":
        return _new_experiment(root, title, question, exploration, motivated_by)
    if kind == "decision":
        # ``--experiment`` is a legacy compatibility input for Decision
        # evidence. Merge it into the canonical ``evidence`` list, keeping the
        # first-seen order and dropping duplicates.
        merged = _dedupe(([experiment] if experiment else []) + evidence)
        return _new_decision(root, title, question, merged, supersedes)
    raise ProjectError("unknown record kind: {}".format(kind))


def _today() -> str:
    return datetime.date.today().isoformat()


def _clean(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _dedupe(values: Any) -> List[str]:
    """Normalize repeatable CLI values, dropping blanks and duplicates."""
    result: List[str] = []
    for value in values:
        cleaned = _clean(value)
        if cleaned is not None and cleaned not in result:
            result.append(cleaned)
    return result


def _require(root: Path, kind: str, record_id: str) -> None:
    if record_id not in existing_ids(root, kind):
        raise ProjectError(
            "{} {} does not exist in this project".format(kind, record_id)
        )


def _require_members(
    root: Path, ids: List[str], kinds: Tuple[str, ...], flag: str
) -> None:
    for record_id in ids:
        if not any(record_id in existing_ids(root, kind) for kind in kinds):
            expected = " or ".join("{}###".format(ID_PREFIX[kind]) for kind in kinds)
            raise ProjectError(
                "--{} must reference an existing {} (got {!r})".format(
                    flag, expected, record_id
                )
            )


def _require_directory(root: Path, key: str) -> Path:
    directory = config_path(root, key)
    if not directory.is_dir():
        raise ProjectError(
            "project path {!r} is missing or not a directory: {} "
            "(run `sci validate`)".format(key, directory)
        )
    return directory


def _write(path: Path, front_matter: Any, body: str) -> None:
    path.write_text(render_record(front_matter, body), encoding="utf-8")


def _report(root: Path, path: Path, kind: str, record_id: str) -> None:
    print("Created {} {}".format(kind, record_id))
    print("  {}".format(relative_path(root, path)))


def _create_output_workspace(
    root: Path, group: str, record_id: str, subdirectories: Any
) -> Path:
    """Create the gitignored generated-output workspace for a record.

    The workspace uses the stable ID only (for example ``X001`` / ``EXP001``),
    never the slug.  Outputs are local generated state and are excluded from
    Git; these directories are created eagerly so scripts have a stable home.
    """
    workspace = root / "outputs" / group / record_id
    for name in subdirectories:
        (workspace / name).mkdir(parents=True, exist_ok=True)
    return workspace


def _new_question(root: Path, title: str) -> int:
    record_id = next_id(root, "question")
    directory = _require_directory(root, "questions")
    path = unique_path(directory, "{}-{}".format(record_id, slugify(title)), ".md")
    front = {
        "id": record_id,
        "title": title,
        "status": "open",
        "created": _today(),
    }
    body = QUESTION_BODY.format(record_id=record_id, title=title)
    _write(path, front, body)
    _report(root, path, "question", record_id)
    return 0


def _new_exploration(
    root: Path,
    title: str,
    question: Optional[str],
    motivated_by: List[str],
) -> int:
    record_id = next_id(root, "exploration")
    parent = _require_directory(root, "explorations")
    folder = unique_path(parent, "{}-{}".format(record_id, slugify(title)), "")
    folder.mkdir(parents=True)
    front = {
        "id": record_id,
        "title": title,
        "status": "active",
        "created": _today(),
    }
    if question:
        front["question"] = question
    if motivated_by:
        front["motivated_by"] = motivated_by
    note = folder / "NOTE.md"
    _write(note, front, EXPLORATION_BODY.format(record_id=record_id, title=title))
    workspace = _create_output_workspace(
        root, "explorations", record_id, ("plots", "tables", "logs", "cache")
    )
    _report(root, note, "exploration", record_id)
    print("  {}".format(relative_path(root, workspace)))
    return 0


def _new_experiment(
    root: Path,
    title: str,
    question: Optional[str],
    exploration: Optional[str],
    motivated_by: List[str],
) -> int:
    record_id = next_id(root, "experiment")
    parent = _require_directory(root, "experiments")
    folder = unique_path(parent, "{}-{}".format(record_id, slugify(title)), "")
    folder.mkdir(parents=True)
    front = {
        "id": record_id,
        "title": title,
        "status": "planned",
        "created": _today(),
    }
    if question:
        front["question"] = question
    if exploration:
        front["exploration"] = exploration
    if motivated_by:
        front["motivated_by"] = motivated_by
    readme = folder / "README.md"
    _write(readme, front, EXPERIMENT_BODY.format(record_id=record_id, title=title))
    # The machine-readable experiment config mirrors identity fields so that
    # scripts can load an experiment without parsing Markdown.
    config_path_ = folder / "config.yaml"
    config_path_.write_text(
        yaml.safe_dump(dict(front), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    _report(root, readme, "experiment", record_id)
    print("  {}".format(relative_path(root, config_path_)))
    workspace = _create_output_workspace(
        root,
        "experiments",
        record_id,
        ("plots", "tables", "logs", "checkpoints", "cache"),
    )
    print("  {}".format(relative_path(root, workspace)))
    return 0


def _new_decision(
    root: Path,
    title: str,
    question: Optional[str],
    evidence: List[str],
    supersedes: Optional[str],
) -> int:
    record_id = next_id(root, "decision")
    directory = _require_directory(root, "decisions")
    path = unique_path(directory, "{}-{}".format(record_id, slugify(title)), ".md")
    front = {
        "id": record_id,
        "title": title,
        "status": "active",
        "created": _today(),
    }
    if question:
        front["question"] = question
    if evidence:
        front["evidence"] = evidence
    if supersedes:
        front["supersedes"] = supersedes
    body = DECISION_BODY.format(record_id=record_id, title=title)
    _write(path, front, body)
    _report(root, path, "decision", record_id)
    return 0
