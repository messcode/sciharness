"""``sci status``: deterministic project summary from the filesystem."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from ..figures import list_figures
from ..output import (
    EXIT_OK,
    EXIT_VALIDATION,
    diagnostics_from_problems,
    emit,
    envelope,
    project_info,
)
from ..project import (
    Record,
    find_project_root,
    id_number,
    load_config,
    load_records,
    relative_path,
)
from .validate import validate_project

RECENT_DECISIONS = 5


def run(args: Any) -> int:
    root = find_project_root(Path(args.path))
    config = load_config(root)
    project = config.get("project") if isinstance(config.get("project"), dict) else {}
    name = (project or {}).get("name") or root.name

    questions, _ = load_records(root, "question")
    explorations, _ = load_records(root, "exploration")
    experiments, _ = load_records(root, "experiment")
    decisions, _ = load_records(root, "decision")

    active_questions = [r for r in questions if r.status == "open"]
    active_explorations = [r for r in explorations if r.status == "active"]
    active_experiments = [
        r for r in experiments if r.status in ("planned", "running")
    ]
    recent = sorted(
        decisions, key=lambda record: id_number(record.id), reverse=True
    )[:RECENT_DECISIONS]
    figures = list_figures(root)
    problems = validate_project(root)
    diagnostics = diagnostics_from_problems(problems)
    ok = not problems

    if getattr(args, "json", False):
        emit(
            envelope(
                "status",
                project=project_info(root, name),
                ok=ok,
                diagnostics=diagnostics,
                data={
                    "active": {
                        "questions": [
                            _record_data(root, r) for r in active_questions
                        ],
                        "explorations": [
                            _record_data(root, r) for r in active_explorations
                        ],
                        "experiments": [
                            _record_data(root, r) for r in active_experiments
                        ],
                    },
                    "recent_decisions": [
                        _record_data(root, r) for r in recent
                    ],
                    "figures": [
                        {
                            "id": figure_id,
                            "status": status or "unknown",
                            "approved": approved,
                        }
                        for figure_id, status, approved in figures
                    ],
                    "validation": {
                        "ok": ok,
                        "problem_count": len(problems),
                    },
                },
            )
        )
        return EXIT_OK if ok else EXIT_VALIDATION

    print("Project: {}".format(name))

    _section("Active questions", active_questions)
    _section("Active explorations", active_explorations)
    _section("Active experiments", active_experiments)
    _section("Recent decisions", recent)

    if figures:
        print("\nManuscript figures")
        for figure_id, status, approved in figures:
            print(
                "  {:<10} {:<10} {}".format(
                    figure_id,
                    status or "unknown",
                    "approved" if approved else "not approved",
                )
            )

    print("\nValidation")
    if not problems:
        print("  no problems")
        return EXIT_OK
    print("  {} problem(s) — run `sci validate`".format(len(problems)))
    # `sci status` is used by agents and CI as a health check; a broken project
    # must not look successful just because the summary could be printed.
    return EXIT_VALIDATION


def _record_data(root: Path, record: Record) -> Dict[str, Any]:
    return {
        "id": record.id,
        "title": record.title,
        "status": record.status,
        "created": record.created,
        "path": relative_path(root, record.path),
    }


def _section(title: str, records: List[Record]) -> None:
    print("\n{}".format(title))
    if not records:
        print("  (none)")
        return
    for record in records:
        print("  {}  {}".format(record.id, record.title))
