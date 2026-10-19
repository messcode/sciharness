"""``sci new``: create questions, explorations, experiments, and decisions.

The CLI allocates IDs deterministically from existing filenames; agents never
pick IDs by hand.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional, Tuple

import yaml

from ..datasets import dataset_ids
from ..output import EXIT_OK, emit, envelope, project_info
from ..project import (
    EVIDENCE_KINDS,
    ID_PREFIX,
    MOTIVATED_BY_KINDS,
    ProjectError,
    allocate_id,
    config_path,
    existing_ids,
    find_project_root,
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


@dataclass
class CreatedRecord:
    kind: str
    id: str
    path: Path
    outputs: Optional[Path] = None
    config: Optional[Path] = None
    datasets: Optional[List[str]] = None


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
    datasets = _dedupe(getattr(args, "datasets", None) or ())

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
    _require_datasets(root, datasets)

    kind = args.record_kind
    if kind == "question":
        created = _new_question(root, title)
    elif kind == "exploration":
        created = _new_exploration(root, title, question, motivated_by)
    elif kind == "experiment":
        created = _new_experiment(
            root, title, question, exploration, motivated_by, datasets
        )
    elif kind == "decision":
        # ``--experiment`` is a legacy compatibility input for Decision
        # evidence. Merge it into the canonical ``evidence`` list, keeping the
        # first-seen order and dropping duplicates.
        merged = _dedupe(([experiment] if experiment else []) + evidence)
        created = _new_decision(root, title, question, merged, supersedes)
    else:
        raise ProjectError("unknown record kind: {}".format(kind))

    created_data: dict = {
        "kind": created.kind,
        "id": created.id,
        "record": relative_path(root, created.path),
    }
    if created.config is not None:
        created_data["config"] = relative_path(root, created.config)
    if created.outputs is not None:
        created_data["outputs"] = relative_path(root, created.outputs)
    if created.datasets:
        created_data["datasets"] = created.datasets

    if getattr(args, "json", False):
        emit(
            envelope(
                "new.{}".format(created.kind),
                project=project_info(root),
                data=created_data,
            )
        )
        return EXIT_OK

    print("Created {} {}".format(created.kind, created.id))
    print("  {}".format(created_data["record"]))
    if created.config is not None:
        print("  {}".format(created_data["config"]))
    if created.outputs is not None:
        print("  {}".format(created_data["outputs"]))
    return EXIT_OK


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


def _require_datasets(root: Path, ids: List[str]) -> None:
    if not ids:
        return
    declared = dataset_ids(root)
    for record_id in ids:
        if record_id not in declared:
            raise ProjectError(
                "--dataset must reference a dataset declared in "
                "data/registry.yaml (got {!r})".format(record_id)
            )


def _require_directory(root: Path, key: str) -> Path:
    """Return a configured record directory, creating it lazily if needed.

    A project may be cloned without empty directories (or a user may delete an
    empty one).  Creating the parent here keeps `sci new` usable instead of
    producing a deadlock with `sci validate`.
    """
    directory = config_path(root, key)
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ProjectError(
            "project path {!r} is not a usable directory: {} ({})".format(
                key, directory, exc
            )
        ) from exc
    keep = directory / ".gitkeep"
    if not keep.exists():
        keep.write_text("", encoding="utf-8")
    return directory


def _write(path: Path, front_matter: Any, body: str) -> None:
    path.write_text(render_record(front_matter, body), encoding="utf-8")


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


def _new_question(root: Path, title: str) -> CreatedRecord:
    directory = _require_directory(root, "questions")
    record_id = allocate_id(root, "question")
    slug = slugify(title) or record_id
    path = unique_path(directory, "{}-{}".format(record_id, slug), ".md")
    front = {
        "id": record_id,
        "title": title,
        "status": "open",
        "created": _today(),
    }
    body = QUESTION_BODY.format(record_id=record_id, title=title)
    _write(path, front, body)
    return CreatedRecord(kind="question", id=record_id, path=path)


def _new_exploration(
    root: Path,
    title: str,
    question: Optional[str],
    motivated_by: List[str],
) -> CreatedRecord:
    parent = _require_directory(root, "explorations")
    record_id = allocate_id(root, "exploration")
    slug = slugify(title) or record_id
    folder = unique_path(parent, "{}-{}".format(record_id, slug), "")
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
    return CreatedRecord(
        kind="exploration", id=record_id, path=note, outputs=workspace
    )


def _new_experiment(
    root: Path,
    title: str,
    question: Optional[str],
    exploration: Optional[str],
    motivated_by: List[str],
    datasets: List[str],
) -> CreatedRecord:
    parent = _require_directory(root, "experiments")
    record_id = allocate_id(root, "experiment")
    slug = slugify(title) or record_id
    folder = unique_path(parent, "{}-{}".format(record_id, slug), "")
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
    if datasets:
        front["datasets"] = datasets
    readme = folder / "README.md"
    _write(readme, front, EXPERIMENT_BODY.format(record_id=record_id, title=title))
    # The machine-readable config holds computational settings only.  Identity,
    # status, and provenance have a single source of truth: README.md front
    # matter.  Keeping them out of config.yaml prevents the two files drifting.
    config_path_ = folder / "config.yaml"
    config_data = {
        "schema_version": 1,
        "record": record_id,
        "parameters": {},
    }
    config_path_.write_text(
        "# Experiment configuration: computational settings only.\n"
        "# Scientific identity, status, and provenance live in README.md.\n"
        + yaml.safe_dump(config_data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    workspace = _create_output_workspace(
        root,
        "experiments",
        record_id,
        ("plots", "tables", "logs", "checkpoints", "cache"),
    )
    return CreatedRecord(
        kind="experiment",
        id=record_id,
        path=readme,
        outputs=workspace,
        config=config_path_,
        datasets=datasets or None,
    )


def _new_decision(
    root: Path,
    title: str,
    question: Optional[str],
    evidence: List[str],
    supersedes: Optional[str],
) -> CreatedRecord:
    directory = _require_directory(root, "decisions")
    record_id = allocate_id(root, "decision")
    slug = slugify(title) or record_id
    path = unique_path(directory, "{}-{}".format(record_id, slug), ".md")
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
    return CreatedRecord(kind="decision", id=record_id, path=path)
