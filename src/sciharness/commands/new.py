"""``sci new``: create questions, explorations, experiments, and decisions.

The CLI allocates IDs deterministically from existing filenames; agents never
pick IDs by hand.
"""
from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any, Optional

import yaml

from ..project import (
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

    if question:
        _require(root, "question", question)
    if exploration:
        _require(root, "exploration", exploration)
    if experiment:
        _require(root, "experiment", experiment)
    if supersedes:
        _require(root, "decision", supersedes)

    kind = args.record_kind
    if kind == "question":
        return _new_question(root, title)
    if kind == "exploration":
        return _new_exploration(root, title, question)
    if kind == "experiment":
        return _new_experiment(root, title, question, exploration)
    if kind == "decision":
        return _new_decision(root, title, question, experiment, supersedes)
    raise ProjectError("unknown record kind: {}".format(kind))


def _today() -> str:
    return datetime.date.today().isoformat()


def _clean(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _require(root: Path, kind: str, record_id: str) -> None:
    if record_id not in existing_ids(root, kind):
        raise ProjectError(
            "{} {} does not exist in this project".format(kind, record_id)
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


def _new_exploration(root: Path, title: str, question: Optional[str]) -> int:
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
    note = folder / "NOTE.md"
    _write(note, front, EXPLORATION_BODY.format(record_id=record_id, title=title))
    _report(root, note, "exploration", record_id)
    return 0


def _new_experiment(
    root: Path, title: str, question: Optional[str], exploration: Optional[str]
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
    return 0


def _new_decision(
    root: Path,
    title: str,
    question: Optional[str],
    experiment: Optional[str],
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
    if experiment:
        front["experiment"] = experiment
    if supersedes:
        front["supersedes"] = supersedes
    body = DECISION_BODY.format(record_id=record_id, title=title)
    _write(path, front, body)
    _report(root, path, "decision", record_id)
    return 0
